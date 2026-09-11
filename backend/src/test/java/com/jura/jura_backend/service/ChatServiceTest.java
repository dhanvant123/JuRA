package com.jura.jura_backend.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.jura.jura_backend.client.PythonRagClient;
import com.jura.jura_backend.dto.chat.ChatMessageResponse;
import com.jura.jura_backend.dto.chat.ChatResponse;
import com.jura.jura_backend.dto.chat.ChatSessionResponse;
import com.jura.jura_backend.dto.chat.SendMessageRequest;
import com.jura.jura_backend.dto.rag.RagCitationDto;
import com.jura.jura_backend.dto.rag.RagResponseDto;
import com.jura.jura_backend.entity.ChatMessage;
import com.jura.jura_backend.entity.ChatSession;
import com.jura.jura_backend.entity.User;
import com.jura.jura_backend.exception.ForbiddenOperationException;
import com.jura.jura_backend.repository.ChatMessageRepository;
import com.jura.jura_backend.repository.ChatSessionRepository;
import com.jura.jura_backend.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.Spy;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ChatServiceTest {

    @Mock
    private ChatSessionRepository chatSessionRepository;

    @Mock
    private ChatMessageRepository chatMessageRepository;

    @Mock
    private UserRepository userRepository;

    @Mock
    private PythonRagClient pythonRagClient;

    @Spy
    private ObjectMapper objectMapper = new ObjectMapper();

    @InjectMocks
    private ChatService chatService;

    private User sampleUser;
    private ChatSession sampleSession;
    private UUID sessionId;

    @BeforeEach
    void setUp() {
        sessionId = UUID.randomUUID();
        sampleUser = User.builder()
                .email("advocate@jura.law")
                .name("Adv. Sharma")
                .passwordHash("pass")
                .role("USER")
                .createdAt(Instant.now())
                .build();

        sampleSession = ChatSession.builder()
                .id(sessionId)
                .user(sampleUser)
                .title("New Chat")
                .createdAt(Instant.now())
                .build();
    }

    @Test
    void shouldCreateChatSessionSuccessfully() {
        when(userRepository.findByEmail("advocate@jura.law")).thenReturn(Optional.of(sampleUser));
        when(chatSessionRepository.save(any(ChatSession.class))).thenReturn(sampleSession);

        ChatSessionResponse response = chatService.createSession("advocate@jura.law", "Property Law Query");

        assertNotNull(response);
        assertEquals(sessionId, response.getId());
    }

    @Test
    void shouldPreventUnauthorizedUserFromReadingSessionMessages() {
        when(chatSessionRepository.findById(sessionId)).thenReturn(Optional.of(sampleSession));

        assertThrows(ForbiddenOperationException.class,
                () -> chatService.getSessionMessages("stranger@jura.law", sessionId));
    }

    @Test
    void shouldSendMessageAndPersistBothUserAndAssistantMessages() {
        SendMessageRequest request = SendMessageRequest.builder()
                .content("What is punishment for murder?")
                .limit(5)
                .build();

        RagCitationDto citationDto = RagCitationDto.builder()
                .documentTitle("Bharatiya Nyaya Sanhita, 2023")
                .articleOrSection("Section 103")
                .page(42)
                .source("India Code")
                .sourceUrl("https://www.indiacode.nic.in/")
                .build();

        RagResponseDto ragResponse = RagResponseDto.builder()
                .query(request.getContent())
                .answer("Under Section 103 of BNS 2023, punishment is death or life imprisonment [1].")
                .citations(List.of(citationDto))
                .build();

        ChatMessage assistantMsg = ChatMessage.builder()
                .id(UUID.randomUUID())
                .chatSession(sampleSession)
                .role("ASSISTANT")
                .content(ragResponse.getAnswer())
                .createdAt(Instant.now())
                .build();

        when(chatSessionRepository.findById(sessionId)).thenReturn(Optional.of(sampleSession));
        when(pythonRagClient.query(any())).thenReturn(ragResponse);
        when(chatMessageRepository.save(any(ChatMessage.class))).thenReturn(assistantMsg);

        ChatResponse response = chatService.sendMessage("advocate@jura.law", sessionId, request);

        assertNotNull(response);
        assertEquals("ASSISTANT", response.getMessage().getRole());
        assertEquals(1, response.getCitations().size());
        assertEquals("Bharatiya Nyaya Sanhita, 2023", response.getCitations().get(0).getDocumentTitle());
        assertEquals("Section 103", response.getCitations().get(0).getArticleOrSection());

        // Verify two messages were persisted (1 user message, 1 assistant message)
        verify(chatMessageRepository, times(2)).save(any(ChatMessage.class));
    }
}
