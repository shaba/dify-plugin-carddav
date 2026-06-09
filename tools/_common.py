"""Shared error formatting for CardDAV tools."""

from __future__ import annotations

from carddav_client.errors import redact_credentials


def error_message(exc: object) -> str:
    """User/LLM-facing error text with any embedded URL credentials stripped."""
    return f"CardDAV error: {redact_credentials(exc)}"
