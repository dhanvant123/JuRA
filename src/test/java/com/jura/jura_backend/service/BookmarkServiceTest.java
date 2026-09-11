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
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class BookmarkServiceTest {

    @Mock
    private BookmarkRepository bookmarkRepository;

    @Mock
    private UserRepository userRepository;

    @Mock
    private LegalItemRepository legalItemRepository;

    @InjectMocks
    private BookmarkService bookmarkService;

    private User sampleUser;
    private LegalItem sampleLegalItem;
    private UUID legalItemId;
    private Bookmark sampleBookmark;

    @BeforeEach
    void setUp() {
        legalItemId = UUID.randomUUID();
        sampleUser = User.builder()
                .email("advocate@jura.law")
                .name("Adv. Sharma")
                .passwordHash("pass")
                .role("USER")
                .createdAt(Instant.now())
                .build();

        sampleLegalItem = LegalItem.builder()
                .id(legalItemId)
                .type("CONSTITUTION")
                .title("Article 21")
                .question("Protection of life and personal liberty")
                .year(1950)
                .source("Legislative Dept")
                .createdAt(Instant.now())
                .updatedAt(Instant.now())
                .build();

        sampleBookmark = Bookmark.builder()
                .id(new BookmarkId(sampleUser.getEmail(), legalItemId))
                .user(sampleUser)
                .legalItem(sampleLegalItem)
                .note("Important for fundamental rights case")
                .createdAt(Instant.now())
                .build();
    }

    @Test
    void shouldCreateBookmarkSuccessfully() {
        CreateBookmarkRequest request = CreateBookmarkRequest.builder()
                .legalItemId(legalItemId)
                .note("Important note")
                .build();

        when(bookmarkRepository.existsById(any(BookmarkId.class))).thenReturn(false);
        when(userRepository.findByEmail("advocate@jura.law")).thenReturn(Optional.of(sampleUser));
        when(legalItemRepository.findById(legalItemId)).thenReturn(Optional.of(sampleLegalItem));
        when(bookmarkRepository.save(any(Bookmark.class))).thenReturn(sampleBookmark);

        BookmarkResponse response = bookmarkService.createBookmark("advocate@jura.law", request);

        assertNotNull(response);
        assertEquals(legalItemId, response.getLegalItemId());
        verify(bookmarkRepository).save(any(Bookmark.class));
    }

    @Test
    void shouldThrowDuplicateExceptionIfAlreadyBookmarked() {
        CreateBookmarkRequest request = CreateBookmarkRequest.builder()
                .legalItemId(legalItemId)
                .build();

        when(bookmarkRepository.existsById(any(BookmarkId.class))).thenReturn(true);

        assertThrows(DuplicateResourceException.class,
                () -> bookmarkService.createBookmark("advocate@jura.law", request));
    }

    @Test
    void shouldUpdateBookmarkNote() {
        UpdateBookmarkRequest request = UpdateBookmarkRequest.builder()
                .note("Updated note text")
                .build();

        when(bookmarkRepository.findById(any(BookmarkId.class))).thenReturn(Optional.of(sampleBookmark));
        when(bookmarkRepository.save(any(Bookmark.class))).thenReturn(sampleBookmark);

        BookmarkResponse response = bookmarkService.updateBookmarkNote("advocate@jura.law", legalItemId, request);

        assertNotNull(response);
        assertEquals(legalItemId, response.getLegalItemId());
    }

    @Test
    void shouldDeleteBookmark() {
        when(bookmarkRepository.existsById(any(BookmarkId.class))).thenReturn(true);

        bookmarkService.deleteBookmark("advocate@jura.law", legalItemId);

        verify(bookmarkRepository).deleteById(any(BookmarkId.class));
    }
}
