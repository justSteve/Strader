"""Schwab API client singleton management."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

_client = None
_stream_client = None


def get_schwab_client():
    """Get or create the Schwab REST client."""
    global _client
    if _client is not None:
        return _client

    if not settings.schwab_api_key:
        logger.warning("SCHWAB_API_KEY not set — running in demo mode")
        return None

    try:
        import schwab
        token_path = Path(settings.schwab_token_path)
        if token_path.exists():
            _client = schwab.auth.client_from_token_file(
                settings.schwab_token_path,
                settings.schwab_api_key,
                settings.schwab_app_secret,
            )
            logger.info("Schwab client initialized from token file")
        else:
            logger.warning("No Schwab token file found — run auth flow first")
            return None
    except Exception as e:
        logger.error(f"Failed to init Schwab client: {e}")
        return None

    return _client


async def get_schwab_stream_client():
    """Get or create the Schwab streaming client."""
    global _stream_client
    if _stream_client is not None:
        return _stream_client

    client = get_schwab_client()
    if client is None:
        return None

    try:
        import schwab
        _stream_client = schwab.streaming.StreamClient(client)
        logger.info("Schwab stream client created")
    except Exception as e:
        logger.error(f"Failed to create stream client: {e}")
        return None

    return _stream_client
