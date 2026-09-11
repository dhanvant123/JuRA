package com.jura.jura_backend.service;

import com.jura.jura_backend.dto.legalitem.LegalItemResponse;
import com.jura.jura_backend.dto.legalitem.PageResponse;
import com.jura.jura_backend.entity.LegalItem;
import com.jura.jura_backend.exception.ResourceNotFoundException;
import com.jura.jura_backend.repository.LegalItemRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.domain.Specification;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class LegalItemServiceTest {

    @Mock
    private LegalItemRepository legalItemRepository;

    @InjectMocks
    private LegalItemService legalItemService;

    private LegalItem sampleItem;
    private UUID itemId;

    @BeforeEach
    void setUp() {
        itemId = UUID.randomUUID();
        sampleItem = LegalItem.builder()
                .id(itemId)
                .type("CONSTITUTION")
                .title("Article 21")
                .question("Protection of life and personal liberty")
                .year(1950)
                .source("Legislative Dept")
                .createdAt(Instant.now())
                .updatedAt(Instant.now())
                .build();
    }

    @Test
    void shouldFindLegalItemById() {
        when(legalItemRepository.findById(itemId)).thenReturn(Optional.of(sampleItem));

        LegalItemResponse response = legalItemService.getLegalItemById(itemId);

        assertNotNull(response);
        assertEquals(itemId, response.getId());
        assertEquals("Article 21", response.getTitle());
    }

    @Test
    void shouldThrowExceptionWhenLegalItemNotFound() {
        when(legalItemRepository.findById(itemId)).thenReturn(Optional.empty());

        assertThrows(ResourceNotFoundException.class, () -> legalItemService.getLegalItemById(itemId));
    }

    @Test
    @SuppressWarnings("unchecked")
    void shouldReturnPaginatedLegalItems() {
        Page<LegalItem> page = new PageImpl<>(List.of(sampleItem), PageRequest.of(0, 10), 1);
        when(legalItemRepository.findAll(any(Specification.class), any(Pageable.class))).thenReturn(page);

        PageResponse<LegalItemResponse> response = legalItemService.getLegalItems(
                "CONSTITUTION", 1950, "Legislative", "liberty", PageRequest.of(0, 10));

        assertNotNull(response);
        assertEquals(1, response.getContent().size());
        assertEquals("Article 21", response.getContent().get(0).getTitle());
    }
}
