"""Shared list pagination helpers for Admin/Customer list APIs."""

from __future__ import annotations

from typing import Tuple


def clamp_pagination(page: int | None, page_size: int | None, *, default_size: int = 25) -> Tuple[int, int, int]:
    """
    Return (page, page_size, offset) with safe bounds.
    page_size max 200 to prevent accidental full-table pulls.
    """
    p = 1 if page is None or page < 1 else int(page)
    size = default_size if page_size is None or page_size < 1 else int(page_size)
    size = min(size, 200)
    offset = (p - 1) * size
    return p, size, offset


def pagination_meta(total: int, page: int, page_size: int) -> dict:
    total = max(0, int(total))
    pages = (total + page_size - 1) // page_size if page_size else 0
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1 and total > 0,
    }
