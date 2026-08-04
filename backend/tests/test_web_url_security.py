import socket

import pytest

from app.modules.web_search import url_security


@pytest.mark.asyncio
async def test_public_url_validator_allows_public_addresses(monkeypatch):
    monkeypatch.setattr(
        url_security.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))
        ],
    )
    await url_security.validate_public_url("https://policy.example/document")


@pytest.mark.asyncio
async def test_public_url_validator_blocks_private_addresses(monkeypatch):
    monkeypatch.setattr(
        url_security.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
        ],
    )
    with pytest.raises(ValueError, match="Blocked non-public"):
        await url_security.validate_public_url("https://localhost/document")
