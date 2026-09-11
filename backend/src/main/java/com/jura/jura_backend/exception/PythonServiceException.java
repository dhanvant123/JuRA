package com.jura.jura_backend.exception;

import lombok.Getter;
import org.springframework.http.HttpStatus;

@Getter
public class PythonServiceException extends RuntimeException {

    private final HttpStatus status;

    public PythonServiceException(String message) {
        super(message);
        this.status = HttpStatus.BAD_GATEWAY;
    }

    public PythonServiceException(String message, HttpStatus status) {
        super(message);
        this.status = status;
    }

    public PythonServiceException(String message, Throwable cause, HttpStatus status) {
        super(message, cause);
        this.status = status;
    }
}
