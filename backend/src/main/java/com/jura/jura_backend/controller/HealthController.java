package com.jura.jura_backend.controller;

import com.jura.jura_backend.client.PythonRagClient;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.HashMap;
import java.util.Map;

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
@Tag(name = "Health", description = "Backend system health check endpoint")
public class HealthController {

    private final PythonRagClient pythonRagClient;

    @GetMapping("/health")
    @Operation(summary = "Backend health status", description = "Returns health status of the Spring Boot application and AI engine connectivity")
    public ResponseEntity<Map<String, Object>> getHealth() {
        Map<String, Object> health = new HashMap<>();
        health.put("status", "UP");
        health.put("service", "jura-backend");
        health.put("timestamp", Instant.now().toString());

        boolean pythonHealthy = pythonRagClient.isHealthy();
        Map<String, Object> components = new HashMap<>();
        components.put("database", "UP");
        components.put("pythonAiEngine", pythonHealthy ? "UP" : "DOWN");
        health.put("components", components);

        return ResponseEntity.ok(health);
    }
}
