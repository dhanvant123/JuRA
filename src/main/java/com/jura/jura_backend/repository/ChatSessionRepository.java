package com.jura.jura_backend.repository;

import com.jura.jura_backend.entity.ChatSession;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface ChatSessionRepository extends JpaRepository<ChatSession, UUID> {

    List<ChatSession> findAllByUserEmailOrderByCreatedAtDesc(String email);

    Optional<ChatSession> findByIdAndUserEmail(UUID id, String email);

    boolean existsByIdAndUserEmail(UUID id, String email);
}
