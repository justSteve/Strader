"""Schwab API client wrapper using schwab-py."""

import logging
from pathlib import Path

import httpx
import schwab
from schwab.streaming import StreamClient

from ..core.config import settings

logger = logging.getLogger(__name__)

_client: schwab.Client | None = None
_stream_client: StreamClient | None = None


def get_schwab_client() -> schwab.Client | None:
    """Get or create the Schwab API client."""
    global _client
    if _client is not None:
        return _client

    token_path = Path(settings.schwab_token_path)
    if not token_path.exists():
        logger.warning("Schwab token file not found at %s", token_path)
        return None

    if not settings.schwab_app_key or not settings.schwab_app_secret:
        logger.warning("Schwab API credentials not configured")
        return None

    try:
        _client = schwab.auth.client_from_token_file(
            str(token_path),
            api_key=settings.schwab_app_key,
            app_secret=settings.schwab_app_secret,
        )
        logger.info("Schwab client initialized")
        return _client
    except Exception:
        logger.exception("Failed to initialize Schwab client")
        return None


async def get_stream_client() -> StreamClient | None:
    """Get or create the Schwab streaming client."""
    global _stream_client
    if _stream_client is not None:
        return _stream_client

    client = get_schwab_client()
    if client is None:
        return None

    try:
        _stream_client = StreamClient(client)
        logger.info("Schwab stream client initialized")
        return _stream_client
    except Exception:
        logger.exception("Failed to initialize stream client")
        return None
