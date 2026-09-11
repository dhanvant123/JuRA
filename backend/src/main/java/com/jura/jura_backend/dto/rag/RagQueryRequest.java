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
public class RagQueryRequest {

    @JsonProperty("query")
    private String query;

    @JsonProperty("limit")
    @Builder.Default
    private Integer limit = 5;

    @JsonProperty("document_type")
    private String documentType;

    @JsonProperty("legal_status")
    private String legalStatus;
}
