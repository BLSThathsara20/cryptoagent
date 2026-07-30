"""Simple page/limit helpers for list APIs."""

from __future__ import annotations

import math


def paginate_params(page: int, page_size: int) -> tuple[int, int]:
    """Return (offset, page_size) with safe bounds."""
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 20), 100))
    offset = (page - 1) * page_size
    return offset, page_size


def page_meta(total: int, page: int, page_size: int) -> dict:
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 20), 100))
    pages = max(1, math.ceil(total / page_size)) if total else 1
    return {
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1,
    }


def paginated(items: list, total: int, page: int, page_size: int, key: str = "items") -> dict:
    meta = page_meta(total, page, page_size)
    return {key: items, **meta}
