-- Seed data for legal items (Indian Law reference data)

INSERT INTO legal_items (id, type, title, citation, question, year, source, created_at, updated_at)
VALUES
(
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
    'CONSTITUTION',
    'Constitution of India - Article 21 (Protection of Life and Personal Liberty)',
    '[{"document_title": "Constitution of India", "article_or_section": "Article 21", "page": 12, "source": "Legislative Department", "source_url": "https://legislative.gov.in/constitution-of-india/"}]'::jsonb,
    'No person shall be deprived of his life or personal liberty except according to procedure established by law.',
    1950,
    'Legislative Department, Ministry of Law and Justice',
    NOW(),
    NOW()
),
(
    'b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22',
    'CONSTITUTION',
    'Constitution of India - Article 19 (Protection of Certain Rights Regarding Freedom of Speech, etc.)',
    '[{"document_title": "Constitution of India", "article_or_section": "Article 19", "page": 10, "source": "Legislative Department", "source_url": "https://legislative.gov.in/constitution-of-india/"}]'::jsonb,
    'All citizens shall have the right to freedom of speech and expression, to assemble peaceably and without arms, and to form associations or unions.',
    1950,
    'Legislative Department, Ministry of Law and Justice',
    NOW(),
    NOW()
),
(
    'c2eebc99-9c0b-4ef8-bb6d-6bb9bd380a33',
    'ACT',
    'Bharatiya Nyaya Sanhita, 2023 - Section 103 (Punishment for Murder)',
    '[{"document_title": "Bharatiya Nyaya Sanhita, 2023", "article_or_section": "Section 103", "page": 42, "source": "India Code", "source_url": "https://www.indiacode.nic.in/"}]'::jsonb,
    'Whoever commits murder shall be punished with death or imprisonment for life, and shall also be liable to fine.',
    2023,
    'India Code, Ministry of Law and Justice',
    NOW(),
    NOW()
),
(
    'd3eebc99-9c0b-4ef8-bb6d-6bb9bd380a44',
    'ACT',
    'Bharatiya Nagarik Suraksha Sanhita, 2023 - Section 35 (When police may arrest without warrant)',
    '[{"document_title": "Bharatiya Nagarik Suraksha Sanhita, 2023", "article_or_section": "Section 35", "page": 15, "source": "India Code", "source_url": "https://www.indiacode.nic.in/"}]'::jsonb,
    'Any police officer may without an order from a Magistrate and without a warrant, arrest any person who commits, in the presence of a police officer, a cognizable offence.',
    2023,
    'India Code, Ministry of Law and Justice',
    NOW(),
    NOW()
),
(
    'e4eebc99-9c0b-4ef8-bb6d-6bb9bd380a55',
    'JUDGMENT',
    'Kesavananda Bharati v. State of Kerala (Basic Structure Doctrine)',
    '[{"document_title": "Kesavananda Bharati Sripadagalvaru and Ors. v. State of Kerala", "article_or_section": "AIR 1973 SC 1461", "page": 1, "source": "Supreme Court of India", "source_url": "https://main.sci.gov.in/"}]'::jsonb,
    'Parliament has the power to amend the Constitution under Article 368, but this power does not extend to altering or destroying the Basic Structure of the Constitution.',
    1973,
    'Supreme Court of India Reports',
    NOW(),
    NOW()
)
ON CONFLICT (id) DO NOTHING;
