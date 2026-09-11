package com.jura.jura_backend.dto.legalitem;

import com.jura.jura_backend.entity.LegalItem;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class LegalItemSummaryResponse {

    private UUID id;
    private String type;
    private String title;
    private Integer year;
    private String source;

    public static LegalItemSummaryResponse fromEntity(LegalItem entity) {
        if (entity == null) {
            return null;
        }
        return LegalItemSummaryResponse.builder()
                .id(entity.getId())
                .type(entity.getType())
                .title(entity.getTitle())
                .year(entity.getYear())
                .source(entity.getSource())
                .build();
    }
}
