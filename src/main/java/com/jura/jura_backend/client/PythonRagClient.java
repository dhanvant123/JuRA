package com.jura.jura_backend.client;

import com.jura.jura_backend.dto.rag.RagQueryRequest;
import com.jura.jura_backend.dto.rag.RagResponseDto;
import com.jura.jura_backend.exception.PythonServiceException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

import java.time.Duration;
import java.util.Map;

@Slf4j
@Component
public class PythonRagClient {

    private final RestClient restClient;

    public PythonRagClient(
            @Value("${app.ai.python-base-url:http://localhost:8000}") String baseUrl,
            @Value("${app.ai.connect-timeout-ms:5000}") int connectTimeout,
            @Value("${app.ai.read-timeout-ms:60000}") int readTimeout
    ) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofMillis(connectTimeout));
        factory.setReadTimeout(Duration.ofMillis(readTimeout));

        this.restClient = RestClient.builder()
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }

    public boolean isHealthy() {
        try {
            Map<?, ?> response = restClient.get()
                    .uri("/health")
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(Map.class);
            return response != null && "ok".equalsIgnoreCase(String.valueOf(response.get("status")));
        } catch (Exception ex) {
            log.warn("Python AI Engine health check failed: {}", ex.getMessage());
            return false;
        }
    }

    public RagResponseDto query(RagQueryRequest request) {
        log.info("Sending query to Python AI engine: query='{}', limit={}, documentType={}, legalStatus={}",
                request.getQuery(), request.getLimit(), request.getDocumentType(), request.getLegalStatus());

        try {
            RagResponseDto response = restClient.post()
                    .uri("/query")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .body(request)
                    .retrieve()
                    .body(RagResponseDto.class);

            if (response == null || response.getAnswer() == null) {
                log.error("Received null or empty answer from Python AI engine");
                throw new PythonServiceException("Invalid response received from AI engine", HttpStatus.BAD_GATEWAY);
            }

            log.info("Received answer from Python AI engine with {} citation(s)",
                    response.getCitations() != null ? response.getCitations().size() : 0);

            return response;
        } catch (HttpClientErrorException ex) {
            log.error("Python AI engine returned 4xx client error: {} - {}", ex.getStatusCode(), ex.getResponseBodyAsString());
            throw new PythonServiceException("AI engine rejected request: " + ex.getStatusText(), HttpStatus.BAD_REQUEST);
        } catch (HttpServerErrorException ex) {
            log.error("Python AI engine returned 5xx server error: {} - {}", ex.getStatusCode(), ex.getResponseBodyAsString());
            throw new PythonServiceException("AI engine internal error occurred", HttpStatus.BAD_GATEWAY);
        } catch (ResourceAccessException ex) {
            log.error("Failed to connect to Python AI engine: {}", ex.getMessage());
            throw new PythonServiceException("Python AI engine is unreachable or timed out", HttpStatus.SERVICE_UNAVAILABLE);
        } catch (PythonServiceException ex) {
            throw ex;
        } catch (Exception ex) {
            log.error("Unexpected error communicating with Python AI engine: {}", ex.getMessage(), ex);
            throw new PythonServiceException("Unexpected error during AI generation", HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
}
