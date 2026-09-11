package com.jura.jura_backend.dto.rag;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class RagCitationDto {

    @JsonProperty("document_title")
    private String documentTitle;

    @JsonProperty("article_or_section")
    private String articleOrSection;

    @JsonProperty("page")
    private Integer page;

    @JsonProperty("source")
    private String source;

    @JsonProperty("source_url")
    private String sourceUrl;
}
