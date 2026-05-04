"""Shared utility functions used across service and graph modules."""

from typing import Optional


def dedupe_notes(notes: list[str], cap: int = 16) -> list[str]:
    """Deduplicate and trim quality evaluation notes."""
    seen: set[str] = set()
    out: list[str] = []
    for n in notes:
        n = n.strip()
        if n and n not in seen:
            seen.add(n)
            out.append(n)
        if len(out) >= cap:
            break
    return out
