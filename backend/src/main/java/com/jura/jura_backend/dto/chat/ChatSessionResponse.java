package com.jura.jura_backend.dto.chat;

import com.jura.jura_backend.entity.ChatSession;
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
public class ChatSessionResponse {

    private UUID id;
    private String title;
    private Instant createdAt;

    public static ChatSessionResponse fromEntity(ChatSession session) {
        if (session == null) {
            return null;
        }
        return ChatSessionResponse.builder()
                .id(session.getId())
                .title(session.getTitle())
                .createdAt(session.getCreatedAt())
                .build();
    }
}
