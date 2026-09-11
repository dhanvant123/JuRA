package com.jura.jura_backend.controller;

import com.jura.jura_backend.dto.chat.ChatMessageResponse;
import com.jura.jura_backend.dto.chat.ChatResponse;
import com.jura.jura_backend.dto.chat.ChatSessionResponse;
import com.jura.jura_backend.dto.chat.CreateSessionRequest;
import com.jura.jura_backend.dto.chat.SendMessageRequest;
import com.jura.jura_backend.service.ChatService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/chat")
@RequiredArgsConstructor
@Tag(name = "Chat", description = "Endpoints for AI chat sessions and message queries")
@SecurityRequirement(name = "BearerAuth")
public class ChatController {

    private final ChatService chatService;

    @PostMapping("/sessions")
    @Operation(summary = "Create a new chat session", description = "Creates a new chat session for the authenticated user")
    public ResponseEntity<ChatSessionResponse> createSession(
            @AuthenticationPrincipal UserDetails userDetails,
            @RequestBody(required = false) CreateSessionRequest request
    ) {
        String title = request != null ? request.getTitle() : null;
        ChatSessionResponse response = chatService.createSession(userDetails.getUsername(), title);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/sessions")
    @Operation(summary = "Get user chat sessions", description = "Lists all chat sessions belonging to the authenticated user")
    public ResponseEntity<List<ChatSessionResponse>> getUserSessions(
            @AuthenticationPrincipal UserDetails userDetails
    ) {
        List<ChatSessionResponse> sessions = chatService.getUserSessions(userDetails.getUsername());
        return ResponseEntity.ok(sessions);
    }

    @GetMapping("/sessions/{sessionId}/messages")
    @Operation(summary = "Get session message history", description = "Retrieves all messages for a session after verifying user ownership")
    public ResponseEntity<List<ChatMessageResponse>> getSessionMessages(
            @AuthenticationPrincipal UserDetails userDetails,
            @PathVariable("sessionId") UUID sessionId
    ) {
        List<ChatMessageResponse> messages = chatService.getSessionMessages(userDetails.getUsername(), sessionId);
        return ResponseEntity.ok(messages);
    }

    @PostMapping("/sessions/{sessionId}/messages")
    @Operation(summary = "Send message and receive AI response", description = "Saves user message, invokes internal Python RAG engine, and saves and returns AI response with structured citations")
    public ResponseEntity<ChatResponse> sendMessage(
            @AuthenticationPrincipal UserDetails userDetails,
            @PathVariable("sessionId") UUID sessionId,
            @Valid @RequestBody SendMessageRequest request
    ) {
        ChatResponse response = chatService.sendMessage(userDetails.getUsername(), sessionId, request);
        return ResponseEntity.ok(response);
    }
}
