package com.jura.jura_backend.dto.legalitem;

import com.fasterxml.jackson.databind.JsonNode;
import com.jura.jura_backend.entity.LegalItem;
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
public class LegalItemResponse {

    private UUID id;
    private String type;
    private String title;
    private JsonNode citation;
    private String question;
    private Integer year;
    private String source;
    private Instant createdAt;
    private Instant updatedAt;

    public static LegalItemResponse fromEntity(LegalItem entity) {
        if (entity == null) {
            return null;
        }
        return LegalItemResponse.builder()
                .id(entity.getId())
                .type(entity.getType())
                .title(entity.getTitle())
                .citation(entity.getCitation())
                .question(entity.getQuestion())
                .year(entity.getYear())
                .source(entity.getSource())
                .createdAt(entity.getCreatedAt())
                .updatedAt(entity.getUpdatedAt())
                .build();
    }
}
