import asyncio
import fnmatch
import ipaddress
import re
import socket
from urllib.parse import urlparse

from app.schemas.source import SourceRead


async def validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public HTTP(S) URLs are supported")

    loop = asyncio.get_running_loop()
    addresses = await loop.run_in_executor(
        None,
        lambda: socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM),
    )
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError(f"Blocked non-public target address: {ip}")


def is_url_allowed(url: str, source: SourceRead) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    source_host = source.start_url.host
    allowed_domains = source.allowed_domains or ([source_host] if source_host else [])
    hostname = parsed.hostname.lower()
    domain_allowed = any(
        hostname == domain.lower() or hostname.endswith(f".{domain.lower()}")
        for domain in allowed_domains
    )
    if not domain_allowed:
        return False
    return matches_source_patterns(url, source)


def matches_source_patterns(url: str, source: SourceRead) -> bool:
    path = urlparse(url).path
    included = not source.include_patterns or any(
        _matches(path, pattern) for pattern in source.include_patterns
    )
    if not included:
        return False
    return not any(_matches(path, pattern) for pattern in source.exclude_patterns)


def _matches(value: str, pattern: str) -> bool:
    try:
        return re.search(pattern, value) is not None
    except re.error:
        return fnmatch.fnmatch(value, pattern)
