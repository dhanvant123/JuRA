package com.jura.jura_backend.dto.chat;

import com.fasterxml.jackson.databind.JsonNode;
import com.jura.jura_backend.entity.ChatMessage;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ChatMessageResponse {

    private UUID id;
    private String role;
    private String content;
    private JsonNode citation;
    private Instant createdAt;
    private Instant updatedAt;

    public static ChatMessageResponse fromEntity(ChatMessage message) {
        if (message == null) {
            return null;
        }
        return ChatMessageResponse.builder()
                .id(message.getId())
                .role(message.getRole())
                .content(message.getContent())
                .citation(message.getCitation())
                .createdAt(message.getCreatedAt())
                .updatedAt(message.getUpdatedAt())
                .build();
    }
}
