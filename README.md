# ⚖️ JuRA - Juristic Retrieval-Augmented Intelligence (Backend)

> **AI-Powered Legal Research & Chat Assistant for Indian Law**

JuRA is a production-grade legal research and chat platform tailored to Indian Law (Constitution of India, Bharatiya Nyaya Sanhita, Bharatiya Nagarik Suraksha Sanhita, and Supreme Court Judicial Precedents).

---

## 🏗 System Architecture

```text
┌──────────────┐          HTTP / JWT          ┌───────────────────────┐
│              │ ───────────────────────────> │                       │
│    React     │                              │  Spring Boot Backend  │
│   Frontend   │ <─────────────────────────── │      (Port 8080)      │
│              │        Clean JSON DTOs       └───────────┬───────────┘
└──────────────┘                                          │
                                                          │ 1. Saves User Msg
                                                          │ 2. Queries RAG
                                                          │ 3. Saves AI Msg + Citations
                                                          ▼
                                              ┌───────────────────────┐
                                              │   PostgreSQL (5432)   │
                                              │ (Users, Sessions,     │
                                              │  Messages, Bookmarks, │
                                              │  Legal Items JSONB)   │
                                              └───────────────────────┘
                                                          ▲
                                                          │ Internal Server-to-Server
                                                          │ HTTP (RestClient)
                                                          ▼
                                              ┌───────────────────────┐
                                              │ Python FastAPI Engine │
                                              │      (Port 8000)      │
                                              │  (Qdrant Vector DB +  │
                                              │   Embeddings + LLM)   │
                                              └───────────────────────┘
```

- **Spring Boot Backend**: Exposes all client-facing REST APIs, handles stateless JWT authentication/authorization, enforces strict resource ownership, manages PostgreSQL persistence, and translates responses into camelCase client DTOs.
- **Python FastAPI AI Engine**: Internal-only service running RAG pipeline over Indian legal statutes. It is never exposed directly to frontend clients.
- **PostgreSQL Database**: Relational database with Flyway schema migrations, storing users, chat sessions, chat messages with JSONB citation metadata, legal items, and bookmarks.

---

## 🛠 Tech Stack

- **Language**: Java 21 (LTS)
- **Framework**: Spring Boot 3.4.3
- **Security**: Spring Security 6 with Stateless JWT (`io.jsonwebtoken:jjwt:0.12.6`)
- **Database & Persistence**: PostgreSQL, Spring Data JPA, Hibernate 6 (`@JdbcTypeCode(SqlTypes.JSON)`)
- **Migrations**: Flyway (`flyway-core`, `flyway-database-postgresql`)
- **Validation**: Jakarta Bean Validation (`jakarta.validation`)
- **API Documentation**: OpenAPI 3.0 / Swagger UI (`springdoc-openapi-starter-webmvc-ui`)
- **HTTP Client**: Spring 6 `RestClient`
- **Build Tool**: Apache Maven 3.9+

---

## 📋 Database Schema

```text
users (email PK, name, password_hash, role, created_at, ph_no UNIQUE)
  │
  ├── 1:N ──> chat_sessions (id UUID PK, email FK, title, created_at)
  │                 │
  │                 └── 1:N ──> chat_messages (id UUID PK, chat_session_id FK, role, citation JSONB, content TEXT, created_at, updated_at)
  │
  └── 1:N ──> bookmarks (email FK, legal_item_id FK, note TEXT, created_at) [PK: (email, legal_item_id)]
                    │
                    └── N:1 ──> legal_items (id UUID PK, type, title, citation JSONB, question TEXT, year INT, source, created_at, updated_at)
```

---

## 🚀 Getting Started

### 1. Prerequisites

- **Java 21 JDK** installed (`java -version`)
- **Maven 3.9+** installed (`mvn -version`)
- **PostgreSQL 14+** running locally or in cloud
- **Python 3.10+** (for running the Python AI engine)

### 2. Database Setup

Create the PostgreSQL database before starting the application:

```sql
CREATE DATABASE jura_db;
```

Flyway automatically creates all tables and seeds Indian legal reference data on the first application launch.

### 3. Environment Variables & Configuration

Configure via environment variables or edit `src/main/resources/application.yml`:

| Variable | Description | Default (Local Dev) |
|---|---|---|
| `DATABASE_URL` | PostgreSQL JDBC Connection URL | `jdbc:postgresql://localhost:5432/jura_db` |
| `DATABASE_USERNAME` | PostgreSQL User | `postgres` |
| `DATABASE_PASSWORD` | PostgreSQL Password | `postgres` |
| `JWT_SECRET` | Base64-encoded 256-bit Secret Key | `404E635266556A586E3272357538782F413F4428472B4B6250645367566B5970` |
| `JWT_EXPIRATION` | JWT Token Validity (ms) | `86400000` (24 Hours) |
| `PYTHON_AI_BASE_URL`| Base URL for Python AI Engine | `http://localhost:8000` |

### 4. Running the Spring Boot Backend

Using Maven:

```bash
# Clean and run unit tests
mvn clean test

# Run application
mvn spring-boot:run
```

The server will start on `http://localhost:8080`.

### 5. Running the Python AI Engine

In a separate terminal:

```bash
cd python-ai-engine
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 📖 API Documentation & Swagger UI

Once running, explore and test the interactive OpenAPI documentation:

- **Swagger UI**: [http://localhost:8080/swagger-ui.html](http://localhost:8080/swagger-ui.html)
- **OpenAPI JSON**: [http://localhost:8080/v3/api-docs](http://localhost:8080/v3/api-docs)

To test secured endpoints in Swagger UI:
1. Register (`POST /api/auth/register`) or login (`POST /api/auth/login`).
2. Copy the `token` from the response.
3. Click the **Authorize** button at the top of Swagger UI and enter `Bearer <your-token>`.

---

## 📡 REST API Overview

### 1. Authentication
- `POST /api/auth/register` — Register a new user with BCrypt password hashing.
- `POST /api/auth/login` — Authenticate and receive a JWT Bearer token.

### 2. User Profile
- `GET /api/users/me` — Retrieve current authenticated user's profile.

### 3. Chat & AI Assistant
- `POST /api/chat/sessions` — Create a new chat session.
- `GET /api/chat/sessions` — List all chat sessions for the authenticated user.
- `GET /api/chat/sessions/{sessionId}/messages` — Fetch message history for a session (with ownership verification).
- `POST /api/chat/sessions/{sessionId}/messages` — Send a query, invoke Python RAG engine, persist assistant response and structured JSONB citations.

**Sample Send Message Request:**
```json
{
  "content": "What is the punishment for murder under Indian law?",
  "limit": 5,
  "documentType": null,
  "legalStatus": "CURRENT"
}
```

**Sample AI Response:**
```json
{
  "message": {
    "id": "c62f2378-4309-482a-a92c-632b71f92e73",
    "role": "ASSISTANT",
    "content": "Under Section 103 of the Bharatiya Nyaya Sanhita, 2023, whoever commits murder shall be punished with death or imprisonment for life, and shall also be liable to fine [1].",
    "citation": [
      {
        "document_title": "Bharatiya Nyaya Sanhita, 2023",
        "article_or_section": "Section 103",
        "page": 42,
        "source": "India Code",
        "source_url": "https://www.indiacode.nic.in/"
      }
    ],
    "createdAt": "2026-09-11T05:30:00Z"
  },
  "citations": [
    {
      "documentTitle": "Bharatiya Nyaya Sanhita, 2023",
      "articleOrSection": "Section 103",
      "page": 42,
      "source": "India Code",
      "sourceUrl": "https://www.indiacode.nic.in/"
    }
  ]
}
```

### 4. Bookmarks
- `GET /api/bookmarks` — List all bookmarks for the authenticated user.
- `POST /api/bookmarks` — Bookmark a legal item with an optional note.
- `PATCH /api/bookmarks/{legalItemId}` — Update note on a bookmarked item.
- `DELETE /api/bookmarks/{legalItemId}` — Remove a bookmark.

### 5. Legal Reference Items
- `GET /api/legal-items` — Paginated list of legal items with query filters (`type`, `year`, `source`, `query`, `page`, `size`, `sortBy`, `direction`).
- `GET /api/legal-items/{id}` — Retrieve a legal item by its UUID.

### 6. Health Check
- `GET /api/health` — Spring Boot health endpoint reporting service and subsystem status.

---

## 🛡 Security & Error Handling

- **Stateless JWT**: Requests are authenticated via standard `Authorization: Bearer <token>` headers.
- **Resource Ownership Enforcement**: Chat sessions, messages, and bookmarks strictly enforce user ownership checks matching the authenticated JWT email.
- **Safe Error Responses**: Global exception handling (`@RestControllerAdvice`) sanitizes all error responses (400, 401, 403, 404, 409, 500, 502/503), preventing leakage of stack traces, SQL queries, or internal keys.

---

## 📄 License

This project is licensed under the MIT License.
