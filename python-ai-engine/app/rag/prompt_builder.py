"""
app/rag/prompt_builder.py

Step 9 of the pipeline: turn a user's question + a list of retrieved
Chunks into the actual PROMPT TEXT sent to the LLM.

This file deliberately knows NOTHING about which LLM API is used
(Claude, OpenAI, or otherwise -- that choice hasn't been made yet, and
this file doesn't need it to be). It only builds plain strings. The one
file allowed to actually call an LLM is rag_service.py, per the
finalized decision from session one -- prompt_builder.py just prepares
what that call will send.

THE CENTRAL DESIGN PROBLEM THIS SOLVES: per the finalized decision,
citations must come from real chunk metadata, NEVER from the LLM
inventing them. But an LLM naturally wants to write prose like "under
Section 103 of the BNS..." -- and if it does that freely, there's no
reliable way to programmatically verify afterward that "Section 103" is
one of the chunks it was actually given, versus something it
hallucinated from training data. The fix: every chunk is presented to
the model as a NUMBERED reference ([1], [2], ...), the model is
instructed to cite ONLY using those bracket numbers, and rag_service.py
(not yet built) can then map each [N] the model used straight back to
chunks[N-1] to build a real Citation object -- never trusting free-text
the model wrote about what it cited.
"""

from app.models.chunk import Chunk


SYSTEM_PROMPT = """You are JuRA, a legal research assistant for Indian law \
(the Constitution, BNS, BNSS, BSA, CrPC, and IPC).

You will be given a question and a numbered list of REFERENCE passages \
retrieved from these documents. Follow these rules exactly:

1. Answer using ONLY the information in the numbered references below. \
Do not use any outside knowledge, even if you are confident it is correct.
2. Every factual claim in your answer MUST be followed by the bracket \
number(s) of the reference(s) it came from, e.g. "...is punishable with \
life imprisonment [2]." If a claim draws on multiple references, cite all \
of them: [2][4].
3. Never write a bracket number for a reference that isn't in the list \
below. Never invent a Section, Article, or Act name that doesn't appear \
in the references.
4. If the references do not contain enough information to answer the \
question, say so plainly instead of guessing or filling the gap from \
general knowledge.
5. If references disagree (e.g. a repealed IPC section and its BNS \
replacement), point out the discrepancy rather than silently picking one.
"""


def _reference_label(chunk: Chunk) -> str:
    """The human-readable heading shown above each numbered reference,
    e.g. "Bharatiya Nyaya Sanhita, 2023, Section 103 (Punishment for
    murder)" or "Constitution of India, Article 21 (Protection of life
    and personal liberty)". Built the same way _build_context_header()
    in chunker.py builds a chunk's in-text header, but as a single line
    suited to a reference list rather than multiple stacked lines."""
    md = chunk.metadata
    parts = [md.document_title]

    if md.article:
        unit = f"Article {md.article}"
        if md.article_title:
            unit += f" ({md.article_title})"
        parts.append(unit)
    elif md.section:
        unit = f"Section {md.section}"
        if md.section_title:
            unit += f" ({md.section_title})"
        parts.append(unit)

    return ", ".join(parts)


def build_references_block(chunks: list[Chunk]) -> str:
    """Render every retrieved chunk as one numbered reference block.
    This numbering is the SAME order rag_service.py will later use to
    map a [N] the model cites back to chunks[N-1] -- so this function's
    output order must never be silently reordered relative to the input
    list it was given.
    """
    blocks = []
    for i, chunk in enumerate(chunks, start=1):
        label = _reference_label(chunk)
        blocks.append(f"[{i}] {label}\n{chunk.text}")
    return "\n\n".join(blocks)


def build_prompt(query: str, chunks: list[Chunk]) -> str:
    """Build the full user-turn prompt text: the references block, then
    the question. Returns a plain string -- pairing this with
    SYSTEM_PROMPT (as the system message) is rag_service.py's job, since
    how a system prompt is passed differs between LLM APIs.

    Deliberately raises rather than silently building a prompt with zero
    references: an empty references block would let the model answer
    from pure training-data guesswork while LOOKING like it followed the
    citation rules (since there's nothing stopping it from citing "[1]"
    even if reference [1] doesn't exist). Retrieval returning nothing is
    a real, distinct failure mode from "found chunks but they don't
    answer the question" -- rag_service.py should tell those two apart,
    not have this function paper over the first one.
    """
    if not chunks:
        raise ValueError(
            "build_prompt() called with zero chunks -- retrieval found "
            "nothing to answer from. Handle this as a distinct case in "
            "rag_service.py (e.g. return a RagResponse saying no relevant "
            "law was found) rather than sending the LLM an empty "
            "references block."
        )

    references_block = build_references_block(chunks)

    return (
        f"REFERENCES:\n\n{references_block}\n\n"
        f"QUESTION:\n{query}\n\n"
        f"Answer the question using ONLY the references above, citing "
        f"each claim with its bracket number(s)."
    )