package com.jura.jura_backend.service;

import com.jura.jura_backend.dto.bookmark.BookmarkResponse;
import com.jura.jura_backend.dto.bookmark.CreateBookmarkRequest;
import com.jura.jura_backend.dto.bookmark.UpdateBookmarkRequest;
import com.jura.jura_backend.entity.Bookmark;
import com.jura.jura_backend.entity.BookmarkId;
import com.jura.jura_backend.entity.LegalItem;
import com.jura.jura_backend.entity.User;
import com.jura.jura_backend.exception.DuplicateResourceException;
import com.jura.jura_backend.exception.ResourceNotFoundException;
import com.jura.jura_backend.repository.BookmarkRepository;
import com.jura.jura_backend.repository.LegalItemRepository;
import com.jura.jura_backend.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class BookmarkService {

    private final BookmarkRepository bookmarkRepository;
    private final UserRepository userRepository;
    private final LegalItemRepository legalItemRepository;

    @Transactional(readOnly = true)
    public List<BookmarkResponse> getUserBookmarks(String email) {
        return bookmarkRepository.findAllByUserEmailWithLegalItem(email)
                .stream()
                .map(BookmarkResponse::fromEntity)
                .collect(Collectors.toList());
    }

    @Transactional
    public BookmarkResponse createBookmark(String email, CreateBookmarkRequest request) {
        BookmarkId bookmarkId = new BookmarkId(email, request.getLegalItemId());

        if (bookmarkRepository.existsById(bookmarkId)) {
            throw new DuplicateResourceException("You have already bookmarked this legal item");
        }

        User user = userRepository.findByEmail(email)
                .orElseThrow(() -> new ResourceNotFoundException("User not found with email: " + email));

        LegalItem legalItem = legalItemRepository.findById(request.getLegalItemId())
                .orElseThrow(() -> new ResourceNotFoundException("Legal item not found with ID: " + request.getLegalItemId()));

        Bookmark bookmark = Bookmark.builder()
                .id(bookmarkId)
                .user(user)
                .legalItem(legalItem)
                .note(request.getNote() != null ? request.getNote().trim() : null)
                .createdAt(Instant.now())
                .build();

        Bookmark savedBookmark = bookmarkRepository.save(bookmark);
        log.info("Created bookmark for user {} on legal item {}", email, request.getLegalItemId());

        return BookmarkResponse.fromEntity(savedBookmark);
    }

    @Transactional
    public BookmarkResponse updateBookmarkNote(String email, UUID legalItemId, UpdateBookmarkRequest request) {
        BookmarkId bookmarkId = new BookmarkId(email, legalItemId);

        Bookmark bookmark = bookmarkRepository.findById(bookmarkId)
                .orElseThrow(() -> new ResourceNotFoundException("Bookmark not found for legal item: " + legalItemId));

        bookmark.setNote(request.getNote() != null ? request.getNote().trim() : null);
        Bookmark updatedBookmark = bookmarkRepository.save(bookmark);
        log.info("Updated bookmark note for user {} on legal item {}", email, legalItemId);

        return BookmarkResponse.fromEntity(updatedBookmark);
    }

    @Transactional
    public void deleteBookmark(String email, UUID legalItemId) {
        BookmarkId bookmarkId = new BookmarkId(email, legalItemId);

        if (!bookmarkRepository.existsById(bookmarkId)) {
            throw new ResourceNotFoundException("Bookmark not found for legal item: " + legalItemId);
        }

        bookmarkRepository.deleteById(bookmarkId);
        log.info("Deleted bookmark for user {} on legal item {}", email, legalItemId);
    }
}
