package com.jura.jura_backend.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.jura.jura_backend.client.PythonRagClient;
import com.jura.jura_backend.dto.chat.ChatMessageResponse;
import com.jura.jura_backend.dto.chat.ChatResponse;
import com.jura.jura_backend.dto.chat.ChatSessionResponse;
import com.jura.jura_backend.dto.chat.SendMessageRequest;
import com.jura.jura_backend.dto.rag.CitationResponse;
import com.jura.jura_backend.dto.rag.RagQueryRequest;
import com.jura.jura_backend.dto.rag.RagResponseDto;
import com.jura.jura_backend.entity.ChatMessage;
import com.jura.jura_backend.entity.ChatSession;
import com.jura.jura_backend.entity.User;
import com.jura.jura_backend.exception.ForbiddenOperationException;
import com.jura.jura_backend.exception.ResourceNotFoundException;
import com.jura.jura_backend.repository.ChatMessageRepository;
import com.jura.jura_backend.repository.ChatSessionRepository;
import com.jura.jura_backend.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class ChatService {

    private final ChatSessionRepository chatSessionRepository;
    private final ChatMessageRepository chatMessageRepository;
    private final UserRepository userRepository;
    private final PythonRagClient pythonRagClient;
    private final ObjectMapper objectMapper;

    @Transactional
    public ChatSessionResponse createSession(String email, String title) {
        User user = userRepository.findByEmail(email)
                .orElseThrow(() -> new ResourceNotFoundException("User not found with email: " + email));

        String sessionTitle = (title != null && !title.isBlank()) ? title.trim() : "New Chat";

        ChatSession session = ChatSession.builder()
                .id(UUID.randomUUID())
                .user(user)
                .title(sessionTitle)
                .createdAt(Instant.now())
                .build();

        ChatSession savedSession = chatSessionRepository.save(session);
        log.info("Created chat session {} for user {}", savedSession.getId(), email);

        return ChatSessionResponse.fromEntity(savedSession);
    }

    @Transactional(readOnly = true)
    public List<ChatSessionResponse> getUserSessions(String email) {
        return chatSessionRepository.findAllByUserEmailOrderByCreatedAtDesc(email)
                .stream()
                .map(ChatSessionResponse::fromEntity)
                .collect(Collectors.toList());
    }

    @Transactional(readOnly = true)
    public List<ChatMessageResponse> getSessionMessages(String email, UUID sessionId) {
        ChatSession session = chatSessionRepository.findById(sessionId)
                .orElseThrow(() -> new ResourceNotFoundException("Chat session not found with ID: " + sessionId));

        if (!session.getUser().getEmail().equalsIgnoreCase(email)) {
            log.warn("Unauthorized access attempt to session {} by user {}", sessionId, email);
            throw new ForbiddenOperationException("You do not have access to this chat session");
        }

        return chatMessageRepository.findAllByChatSessionIdOrderByCreatedAtAsc(sessionId)
                .stream()
                .map(ChatMessageResponse::fromEntity)
                .collect(Collectors.toList());
    }

    @Transactional
    public ChatResponse sendMessage(String email, UUID sessionId, SendMessageRequest request) {
        ChatSession session = chatSessionRepository.findById(sessionId)
                .orElseThrow(() -> new ResourceNotFoundException("Chat session not found with ID: " + sessionId));

        if (!session.getUser().getEmail().equalsIgnoreCase(email)) {
            log.warn("Unauthorized message post attempt to session {} by user {}", sessionId, email);
            throw new ForbiddenOperationException("You do not have access to this chat session");
        }

        // 1. Persist user message
        ChatMessage userMessage = ChatMessage.builder()
                .id(UUID.randomUUID())
                .chatSession(session)
                .role("USER")
                .citation(null)
                .content(request.getContent().trim())
                .createdAt(Instant.now())
                .build();

        chatMessageRepository.save(userMessage);

        // 2. If session title is default "New Chat", generate title from user query
        if ("New Chat".equalsIgnoreCase(session.getTitle())) {
            String newTitle = request.getContent().trim();
            if (newTitle.length() > 60) {
                newTitle = newTitle.substring(0, 57) + "...";
            }
            session.setTitle(newTitle);
            chatSessionRepository.save(session);
        }

        // 3. Build Python RAG request
        RagQueryRequest ragRequest = RagQueryRequest.builder()
                .query(request.getContent().trim())
                .limit(request.getLimit() != null ? request.getLimit() : 5)
                .documentType(request.getDocumentType())
                .legalStatus(request.getLegalStatus())
                .build();

        // 4. Query Python AI engine
        RagResponseDto ragResponse = pythonRagClient.query(ragRequest);

        // 5. Convert Python citations to JsonNode for JSONB persistence
        List<CitationResponse> clientCitations = new ArrayList<>();
        JsonNode citationJsonNode = null;

        if (ragResponse.getCitations() != null && !ragResponse.getCitations().isEmpty()) {
            clientCitations = ragResponse.getCitations().stream()
                    .map(CitationResponse::fromRagCitation)
                    .collect(Collectors.toList());

            citationJsonNode = objectMapper.valueToTree(ragResponse.getCitations());
        }

        // 6. Persist assistant message
        ChatMessage assistantMessage = ChatMessage.builder()
                .id(UUID.randomUUID())
                .chatSession(session)
                .role("ASSISTANT")
                .citation(citationJsonNode)
                .content(ragResponse.getAnswer())
                .createdAt(Instant.now())
                .build();

        ChatMessage savedAssistantMessage = chatMessageRepository.save(assistantMessage);

        log.info("Saved AI response message {} for session {}", savedAssistantMessage.getId(), sessionId);

        return ChatResponse.builder()
                .message(ChatMessageResponse.fromEntity(savedAssistantMessage))
                .citations(clientCitations)
                .build();
    }
}
