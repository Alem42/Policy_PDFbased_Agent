"""Network safety checks shared by web search and permanent URL import."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse


async def validate_public_url(url: str) -> None:
    """Reject non-HTTP URLs and targets that resolve to a private address."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public HTTP(S) URLs are supported")

    loop = asyncio.get_running_loop()
    addresses = await loop.run_in_executor(
        None,
        lambda: socket.getaddrinfo(
            parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM
        ),
    )
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError(f"Blocked non-public target address: {ip}")
