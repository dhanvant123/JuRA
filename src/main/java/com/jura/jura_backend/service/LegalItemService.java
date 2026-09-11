package com.jura.jura_backend.service;

import com.jura.jura_backend.dto.legalitem.LegalItemResponse;
import com.jura.jura_backend.dto.legalitem.PageResponse;
import com.jura.jura_backend.entity.LegalItem;
import com.jura.jura_backend.exception.ResourceNotFoundException;
import com.jura.jura_backend.repository.LegalItemRepository;
import jakarta.persistence.criteria.Predicate;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class LegalItemService {

    private final LegalItemRepository legalItemRepository;

    @Transactional(readOnly = true)
    public PageResponse<LegalItemResponse> getLegalItems(
            String type,
            Integer year,
            String source,
            String query,
            Pageable pageable
    ) {
        Specification<LegalItem> spec = (root, cq, cb) -> {
            List<Predicate> predicates = new ArrayList<>();

            if (type != null && !type.isBlank()) {
                predicates.add(cb.equal(cb.upper(root.get("type")), type.trim().toUpperCase()));
            }

            if (year != null) {
                predicates.add(cb.equal(root.get("year"), year));
            }

            if (source != null && !source.isBlank()) {
                predicates.add(cb.like(cb.lower(root.get("source")), "%" + source.trim().toLowerCase() + "%"));
            }

            if (query != null && !query.isBlank()) {
                String pattern = "%" + query.trim().toLowerCase() + "%";
                Predicate titleMatch = cb.like(cb.lower(root.get("title")), pattern);
                Predicate questionMatch = cb.like(cb.lower(root.get("question")), pattern);
                predicates.add(cb.or(titleMatch, questionMatch));
            }

            return cb.and(predicates.toArray(new Predicate[0]));
        };

        Page<LegalItem> page = legalItemRepository.findAll(spec, pageable);
        Page<LegalItemResponse> responsePage = page.map(LegalItemResponse::fromEntity);

        return PageResponse.of(responsePage);
    }

    @Transactional(readOnly = true)
    public LegalItemResponse getLegalItemById(UUID id) {
        LegalItem legalItem = legalItemRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Legal item not found with ID: " + id));

        return LegalItemResponse.fromEntity(legalItem);
    }
}
