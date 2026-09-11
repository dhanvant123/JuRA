package com.jura.jura_backend.dto.chat;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SendMessageRequest {

    @NotBlank(message = "Message content is required")
    private String content;

    @Min(value = 1, message = "Limit must be at least 1")
    @Max(value = 20, message = "Limit must not exceed 20")
    @Builder.Default
    private Integer limit = 5;

    private String documentType;

    private String legalStatus;
}
