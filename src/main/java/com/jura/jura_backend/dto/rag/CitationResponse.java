package com.jura.jura_backend.dto.rag;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CitationResponse {

    private String documentTitle;
    private String articleOrSection;
    private Integer page;
    private String source;
    private String sourceUrl;

    public static CitationResponse fromRagCitation(RagCitationDto dto) {
        if (dto == null) {
            return null;
        }
        return CitationResponse.builder()
                .documentTitle(dto.getDocumentTitle())
                .articleOrSection(dto.getArticleOrSection())
                .page(dto.getPage())
                .source(dto.getSource())
                .sourceUrl(dto.getSourceUrl())
                .build();
    }
}
