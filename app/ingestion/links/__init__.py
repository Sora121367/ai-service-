"""Fetch a user-supplied link safely (spec Section 9, Link ingestion safety).

Fetched bytes are data, never instructions: this package only downloads them.
"""

from app.ingestion.links.fetcher import (
    FetchedLink,
    LinkFetchError,
    LinkTimeoutError,
    fetch_link,
)

__all__ = ["FetchedLink", "LinkFetchError", "LinkTimeoutError", "fetch_link"]
