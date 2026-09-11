package com.jura.jura_backend.dto.chat;

import com.jura.jura_backend.dto.rag.CitationResponse;
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
public class ChatResponse {

    private ChatMessageResponse message;

    @Builder.Default
    private List<CitationResponse> citations = new ArrayList<>();
}
