package com.jura.jura_backend.dto.rag;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.ArrayList;
import java.util.List;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonIgnoreProperties(ignoreUnknown = true)
public class RagResponseDto {

    @JsonProperty("query")
    private String query;

    @JsonProperty("answer")
    private String answer;

    @JsonProperty("citations")
    @Builder.Default
    private List<RagCitationDto> citations = new ArrayList<>();
}
