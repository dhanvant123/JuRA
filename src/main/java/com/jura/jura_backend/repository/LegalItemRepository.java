package com.jura.jura_backend.repository;

import com.jura.jura_backend.entity.LegalItem;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.stereotype.Repository;

import java.util.UUID;

@Repository
public interface LegalItemRepository extends JpaRepository<LegalItem, UUID>, JpaSpecificationExecutor<LegalItem> {
}
