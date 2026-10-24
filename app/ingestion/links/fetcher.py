import ipaddress
import socket
import time
import urllib.robotparser
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

import httpx

from app.ingestion.parsing.errors import ParseError

USER_AGENT = "InsightHubBot/0.1"
DEFAULT_MAX_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_REDIRECTS = 5
DEFAULT_TIMEOUT_SECONDS = 20.0

_ROBOTS_MAX_BYTES = 512 * 1024
_DEFAULT_PORTS = {"http": 80, "https": 443}
_REDIRECTS = {301, 302, 303, 307, 308}
# Tunnels that reach internal IPv4 hosts. Python's is_global misses some of these.
_BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(n) for n in ("64:ff9b::/96", "64:ff9b:1::/48", "2002::/16", "2001::/32")
)

Resolver = Callable[[str, int], list[str]]
HopCheck = Callable[[str, str, int], None]  # (url, host, port), called before each request


class LinkFetchError(ParseError):
    """The link can't be fetched. The message is safe to show as job status: it never includes
    resolved addresses or response content."""


class LinkTimeoutError(LinkFetchError):
    """The deadline ran out, or the site answered too slowly."""


@dataclass(frozen=True)
class FetchedLink:
    url: str  # after redirects
    status_code: int
    content_type: str | None  # as sent, e.g. "text/html; charset=utf-8"
    body: bytes
    fetched_at: datetime  # UTC; the snapshot date for web pages


def _resolve(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise LinkFetchError("The link's address could not be found.") from e
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])  # drop an IPv6 zone id
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if any(ip in net for net in _BLOCKED_NETWORKS if net.version == ip.version):
        return False
    return ip.is_global and not ip.is_multicast


def _check_url(url: str) -> tuple[str, str, int]:
    """(scheme, host, port) of a fetchable URL, or LinkFetchError."""
    parts = urlsplit(url.strip())
    if parts.scheme not in _DEFAULT_PORTS:
        raise LinkFetchError("Only http and https links can be fetched.")
    if not parts.hostname:
        raise LinkFetchError("The link has no host name.")
    if parts.username is not None or parts.password is not None:
        raise LinkFetchError("Links with a user name or password can't be fetched.")
    try:
        port = parts.port or _DEFAULT_PORTS[parts.scheme]
    except ValueError as e:
        raise LinkFetchError("The link has an invalid port.") from e
    if port not in _DEFAULT_PORTS.values():
        raise LinkFetchError("Only the standard web ports (80 and 443) are allowed.")
    return parts.scheme, parts.hostname, port


def _public_address(host: str, port: int, resolver: Resolver) -> str:
    """One address to connect to. Every address the name resolves to must be public."""
    addresses = resolver(host, port)
    if not addresses:
        raise LinkFetchError("The link's address could not be found.")
    if not all(_is_public(a) for a in addresses):
        raise LinkFetchError("This link points to a private or internal address.")
    return addresses[0]


def _read(response: httpx.Response, max_bytes: int, deadline: float) -> bytes:
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > max_bytes:
        raise LinkFetchError("The linked file is too large.")
    body = bytearray()
    for chunk in response.iter_bytes():  # decoded bytes, so a compression bomb counts in full
        body += chunk
        if len(body) > max_bytes:
            raise LinkFetchError("The linked file is too large.")
        if time.monotonic() >= deadline:
            raise LinkTimeoutError("The link took too long to download.")
    return bytes(body)


def _get(
    client: httpx.Client,
    url: str,
    *,
    resolver: Resolver,
    max_bytes: int,
    max_redirects: int,
    deadline: float,
    on_hop: HopCheck | None = None,
) -> FetchedLink:
    """GET with manual redirects. Each hop is validated, resolved and then connected to by
    address, so DNS can't change between the check and the connection (rebinding)."""
    for _ in range(max_redirects + 1):
        scheme, host, port = _check_url(url)
        address = _public_address(host, port, resolver)
        if on_hop is not None:
            on_hop(url, host, port)
        if time.monotonic() >= deadline:
            raise LinkTimeoutError("The link took too long to download.")

        netloc = host if port == _DEFAULT_PORTS[scheme] else f"{host}:{port}"
        pinned = httpx.URL(url).copy_with(host=address)
        headers = {"Host": netloc, "User-Agent": USER_AGENT, "Accept": "*/*"}
        try:
            with client.stream(
                "GET", pinned, headers=headers, extensions={"sni_hostname": host}
            ) as response:
                if response.status_code in _REDIRECTS:
                    location = response.headers.get("location")
                    if not location:
                        raise LinkFetchError("The link redirects to nowhere.")
                    url = urljoin(url, location)
                    continue
                if not response.is_success:
                    raise LinkFetchError(f"The link returned HTTP {response.status_code}.")
                return FetchedLink(
                    url=url,
                    status_code=response.status_code,
                    content_type=response.headers.get("content-type"),
                    body=_read(response, max_bytes, deadline),
                    fetched_at=datetime.now(UTC),
                )
        except httpx.TimeoutException as e:
            raise LinkTimeoutError("The link took too long to respond.") from e
        except httpx.HTTPError as e:
            raise LinkFetchError("The link could not be reached.") from e
    raise LinkFetchError("The link redirects too many times.")


def _check_robots(
    client: httpx.Client, url: str, host: str, port: int, *, resolver: Resolver, deadline: float
) -> None:
    """RFC 9309: a missing robots.txt (4xx) allows everything; an unreachable one (5xx, errors)
    allows nothing."""
    scheme = urlsplit(url).scheme
    netloc = host if port == _DEFAULT_PORTS[scheme] else f"{host}:{port}"
    try:
        robots = _get(
            client,
            f"{scheme}://{netloc}/robots.txt",
            resolver=resolver,
            max_bytes=_ROBOTS_MAX_BYTES,
            max_redirects=DEFAULT_MAX_REDIRECTS,
            deadline=deadline,
        )
    except LinkTimeoutError:
        raise
    except LinkFetchError as e:
        if str(e).startswith("The link returned HTTP 4"):
            return  # no robots.txt
        raise LinkFetchError("The site's robots.txt could not be checked.") from e
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(robots.body.decode("utf-8", errors="replace").splitlines())
    if not parser.can_fetch(USER_AGENT, url):
        raise LinkFetchError("The site's robots.txt does not allow fetching this link.")


def fetch_link(
    url: str,
    *,
    resolver: Resolver = _resolve,
    transport: httpx.BaseTransport | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    respect_robots: bool = True,
) -> FetchedLink:
    """Download a link. Only http/https on ports 80 and 443; private, loopback, link-local and
    other non-public addresses are refused (SSRF), including after redirects. Size, redirects and
    total time are limited, and robots.txt is honored. Raises LinkFetchError."""
    deadline = time.monotonic() + timeout_seconds
    timeout = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
    # trust_env=False: proxy variables must not route around the address check.
    with httpx.Client(transport=transport, timeout=timeout, trust_env=False) as client:

        def check_robots(hop_url: str, host: str, port: int) -> None:
            _check_robots(client, hop_url, host, port, resolver=resolver, deadline=deadline)

        return _get(
            client,
            url,
            resolver=resolver,
            max_bytes=max_bytes,
            max_redirects=max_redirects,
            deadline=deadline,
            on_hop=check_robots if respect_robots else None,
        )
