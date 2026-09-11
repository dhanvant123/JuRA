package com.jura.jura_backend.dto.bookmark;

import com.jura.jura_backend.dto.legalitem.LegalItemSummaryResponse;
import com.jura.jura_backend.entity.Bookmark;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class BookmarkResponse {

    private UUID legalItemId;
    private String note;
    private Instant createdAt;
    private LegalItemSummaryResponse legalItem;

    public static BookmarkResponse fromEntity(Bookmark bookmark) {
        if (bookmark == null) {
            return null;
        }
        return BookmarkResponse.builder()
                .legalItemId(bookmark.getId().getLegalItemId())
                .note(bookmark.getNote())
                .createdAt(bookmark.getCreatedAt())
                .legalItem(bookmark.getLegalItem() != null ? LegalItemSummaryResponse.fromEntity(bookmark.getLegalItem()) : null)
                .build();
    }
}
