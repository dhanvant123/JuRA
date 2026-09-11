package com.jura.jura_backend.controller;

import com.jura.jura_backend.dto.bookmark.BookmarkResponse;
import com.jura.jura_backend.dto.bookmark.CreateBookmarkRequest;
import com.jura.jura_backend.dto.bookmark.UpdateBookmarkRequest;
import com.jura.jura_backend.service.BookmarkService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/bookmarks")
@RequiredArgsConstructor
@Tag(name = "Bookmarks", description = "Endpoints for managing user bookmarks on legal items")
@SecurityRequirement(name = "BearerAuth")
public class BookmarkController {

    private final BookmarkService bookmarkService;

    @GetMapping
    @Operation(summary = "Get user bookmarks", description = "Retrieves all legal item bookmarks created by the authenticated user")
    public ResponseEntity<List<BookmarkResponse>> getUserBookmarks(
            @AuthenticationPrincipal UserDetails userDetails
    ) {
        List<BookmarkResponse> bookmarks = bookmarkService.getUserBookmarks(userDetails.getUsername());
        return ResponseEntity.ok(bookmarks);
    }

    @PostMapping
    @Operation(summary = "Create a bookmark", description = "Bookmarks a legal item with an optional note for the authenticated user")
    public ResponseEntity<BookmarkResponse> createBookmark(
            @AuthenticationPrincipal UserDetails userDetails,
            @Valid @RequestBody CreateBookmarkRequest request
    ) {
        BookmarkResponse response = bookmarkService.createBookmark(userDetails.getUsername(), request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @PatchMapping("/{legalItemId}")
    @Operation(summary = "Update bookmark note", description = "Updates note for an existing bookmark owned by the authenticated user")
    public ResponseEntity<BookmarkResponse> updateBookmark(
            @AuthenticationPrincipal UserDetails userDetails,
            @PathVariable("legalItemId") UUID legalItemId,
            @RequestBody UpdateBookmarkRequest request
    ) {
        BookmarkResponse response = bookmarkService.updateBookmarkNote(userDetails.getUsername(), legalItemId, request);
        return ResponseEntity.ok(response);
    }

    @DeleteMapping("/{legalItemId}")
    @Operation(summary = "Delete bookmark", description = "Deletes a bookmark owned by the authenticated user")
    public ResponseEntity<Void> deleteBookmark(
            @AuthenticationPrincipal UserDetails userDetails,
            @PathVariable("legalItemId") UUID legalItemId
    ) {
        bookmarkService.deleteBookmark(userDetails.getUsername(), legalItemId);
        return ResponseEntity.noContent().build();
    }
}
