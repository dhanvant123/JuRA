package com.jura.jura_backend.dto.error;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ValidationErrorItem {

    private String field;
    private Object rejectedValue;
    private String message;
}
