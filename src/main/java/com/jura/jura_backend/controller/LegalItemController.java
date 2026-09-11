package com.jura.jura_backend.controller;

import com.jura.jura_backend.dto.legalitem.LegalItemResponse;
import com.jura.jura_backend.dto.legalitem.PageResponse;
import com.jura.jura_backend.service.LegalItemService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api/legal-items")
@RequiredArgsConstructor
@Tag(name = "Legal Items", description = "Endpoints for exploring shared Indian legal reference data (Constitution, Acts, Judgments)")
@SecurityRequirement(name = "BearerAuth")
public class LegalItemController {

    private final LegalItemService legalItemService;

    @GetMapping
    @Operation(summary = "Get paginated legal items", description = "Retrieves paginated legal reference items with optional filtering by type, year, source, and search query")
    public ResponseEntity<PageResponse<LegalItemResponse>> getLegalItems(
            @Parameter(description = "Filter by document type (e.g. CONSTITUTION, ACT, JUDGMENT)")
            @RequestParam(name = "type", required = false) String type,

            @Parameter(description = "Filter by year")
            @RequestParam(name = "year", required = false) Integer year,

            @Parameter(description = "Filter by source (e.g. 'India Code')")
            @RequestParam(name = "source", required = false) String source,

            @Parameter(description = "Search keyword in title or question text")
            @RequestParam(name = "query", required = false) String query,

            @Parameter(description = "Page number (0-indexed)")
            @RequestParam(name = "page", defaultValue = "0") int page,

            @Parameter(description = "Page size (number of items per page)")
            @RequestParam(name = "size", defaultValue = "10") int size,

            @Parameter(description = "Sort property (e.g. 'year', 'createdAt', 'title')")
            @RequestParam(name = "sortBy", defaultValue = "createdAt") String sortBy,

            @Parameter(description = "Sort direction ('asc' or 'desc')")
            @RequestParam(name = "direction", defaultValue = "desc") String direction
    ) {
        Sort.Direction sortDirection = "asc".equalsIgnoreCase(direction) ? Sort.Direction.ASC : Sort.Direction.DESC;
        Pageable pageable = PageRequest.of(page, size, Sort.by(sortDirection, sortBy));

        PageResponse<LegalItemResponse> response = legalItemService.getLegalItems(type, year, source, query, pageable);
        return ResponseEntity.ok(response);
    }

    @GetMapping("/{id}")
    @Operation(summary = "Get legal item by ID", description = "Retrieves detailed legal item by its UUID")
    public ResponseEntity<LegalItemResponse> getLegalItemById(
            @Parameter(description = "UUID of the legal item")
            @PathVariable("id") UUID id
    ) {
        LegalItemResponse response = legalItemService.getLegalItemById(id);
        return ResponseEntity.ok(response);
    }
}
