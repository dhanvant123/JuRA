package com.jura.jura_backend.repository;

import com.jura.jura_backend.entity.Bookmark;
import com.jura.jura_backend.entity.BookmarkId;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface BookmarkRepository extends JpaRepository<Bookmark, BookmarkId> {

    @Query("SELECT b FROM Bookmark b JOIN FETCH b.legalItem WHERE b.id.email = :email ORDER BY b.createdAt DESC")
    List<Bookmark> findAllByUserEmailWithLegalItem(@Param("email") String email);

    Optional<Bookmark> findByIdEmailAndIdLegalItemId(String email, UUID legalItemId);

    boolean existsByIdEmailAndIdLegalItemId(String email, UUID legalItemId);

    void deleteByIdEmailAndIdLegalItemId(String email, UUID legalItemId);
}
