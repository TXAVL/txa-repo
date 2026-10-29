"""Network helpers with guard rails: HTTPS only, public addresses only, manual redirects."""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import socket
import ssl
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlsplit

import requests

from txa.constants import USER_AGENT

REDIRECTS = {301, 302, 303, 307, 308}
DOH_ENDPOINT = "https://dns.google/resolve"


class NetError(Exception):
    pass


class UnsafeURL(NetError):
    pass


class RedirectLoop(NetError):
    pass


def session() -> requests.Session:
    s = requests.Session()
    # identity: installers are hashed byte for byte, and some CDNs (dl.pstmn.io) answer an empty 200 when gzip is offered
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*", "Accept-Encoding": "identity"})
    return s


def _is_public(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_global
    except ValueError:
        return False


def assert_public_https(url: str, allow_private: bool = False) -> None:
    """Reject anything that is not plain HTTPS to a public host (SSRF guard on CI runners).

    ``allow_private`` lets a client reach company servers on the LAN; CI never sets it.
    """
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise UnsafeURL(f"{url}: only https:// is allowed (got {parts.scheme or 'no scheme'})")
    if not parts.hostname:
        raise UnsafeURL(f"{url}: missing host")
    if parts.username or parts.password:
        raise UnsafeURL(f"{url}: credentials inside URLs are not allowed")
    if parts.port not in (None, 443) and not allow_private:
        raise UnsafeURL(f"{url}: non-standard port {parts.port}")
    host = parts.hostname
    if allow_private:
        return
    try:
        ipaddress.ip_address(host)
        raise UnsafeURL(f"{url}: raw IP addresses are not allowed, use a hostname")
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise NetError(f"{host}: DNS lookup failed ({exc})") from None
    addresses = {info[4][0] for info in infos}
    private = sorted(a for a in addresses if not _is_public(a))
    if private:
        raise UnsafeURL(f"{host} resolves to non-public address(es): {', '.join(private)}")


@dataclass
class Hop:
    url: str
    status: int


@dataclass
class Probe:
    url: str
    final_url: str
    status: int
    hops: list[Hop]
    headers: dict[str, str]
    length: int | None  # total payload size when the server tells us
    method: str
    elapsed_ms: int

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";", 1)[0].strip().lower()


def _normalized(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.hostname}{parts.path}".lower()


def walk(s: requests.Session, url: str, method: str = "HEAD", max_hops: int = 8, timeout: float = 30,
         headers: dict | None = None, allow_private: bool = False) -> tuple[requests.Response, list[Hop]]:
    """Follow redirects by hand so every hop is checked; raises on loops or downgrades."""
    hops: list[Hop] = []
    seen: set[str] = set()
    paths: Counter[str] = Counter()
    current = url
    for _ in range(max_hops + 1):
        assert_public_https(current, allow_private)
        if current in seen:
            raise RedirectLoop(" -> ".join(h.url for h in hops) + f" -> {current}")
        seen.add(current)
        paths[_normalized(current)] += 1
        if paths[_normalized(current)] >= 3:
            raise RedirectLoop(f"{_normalized(current)} visited 3 times (query-string loop)")
        response = s.request(method, current, allow_redirects=False, timeout=timeout, stream=True, headers=headers)
        hops.append(Hop(current, response.status_code))
        if response.status_code in REDIRECTS:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise NetError(f"{current}: HTTP {response.status_code} without a Location header")
            current = urljoin(current, location)
            continue
        return response, hops
    raise RedirectLoop(f"more than {max_hops} redirects: " + " -> ".join(h.url for h in hops))


def probe(s: requests.Session, url: str, max_hops: int = 8, timeout: float = 30) -> Probe:
    """HEAD first; fall back to a 1-byte ranged GET for servers that dislike HEAD."""
    started = time.monotonic()
    response, hops = walk(s, url, "HEAD", max_hops, timeout)
    method = "HEAD"
    length = _int(response.headers.get("Content-Length"))
    if response.status_code in (403, 404, 405, 501) or length is None:
        response.close()
        response, hops = walk(s, url, "GET", max_hops, timeout, headers={"Range": "bytes=0-0"})
        method = "GET (range)"
        length = _total_from_range(response.headers.get("Content-Range"))
        if length is None and response.status_code == 200:
            length = _int(response.headers.get("Content-Length"))
    response.close()
    return Probe(
        url=url,
        final_url=hops[-1].url,
        status=response.status_code,
        hops=hops,
        headers={k.lower(): v for k, v in response.headers.items()},
        length=length,
        method=method,
        elapsed_ms=int((time.monotonic() - started) * 1000),
    )


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _total_from_range(value: str | None) -> int | None:
    # "bytes 0-0/12345"
    if not value or "/" not in value:
        return None
    return _int(value.rsplit("/", 1)[1].strip())


def cdn_fingerprint(headers: dict[str, str]) -> str | None:
    server = headers.get("server", "").lower()
    via = headers.get("via", "").lower()
    checks = [
        ("Cloudflare", "cf-ray" in headers or server == "cloudflare"),
        ("Amazon CloudFront", "x-amz-cf-id" in headers or "cloudfront" in via),
        ("Fastly", "x-fastly-request-id" in headers or "x-served-by" in headers and "cache-" in headers.get("x-served-by", "")),
        ("Akamai", "akamai" in server or any(k.startswith("x-akamai") for k in headers)),
        ("GitHub", "x-github-request-id" in headers or "github" in server),
        ("BunnyCDN", "bunnycdn" in server),
        ("Google Cloud", server in ("gws", "uploadserver") or "x-goog-hash" in headers),
        ("SourceForge", "sourceforge" in server),
    ]
    return next((name for name, hit in checks if hit), None)


# --------------------------------------------------------------------------- download


@dataclass
class Download:
    path: Path
    final_url: str
    bytes: int
    expected: int | None
    sha256: str
    attempts: int
    resumed: bool = False
    headers: dict[str, str] = field(default_factory=dict)


def download(s: requests.Session, url: str, dest_dir: Path, max_bytes: int, max_hops: int = 8,
             timeout: float = 60, attempts: int = 3,
             on_progress: Callable[[int, int | None], None] | None = None,
             allow_private: bool = False, headers: dict | None = None) -> Download:
    """Stream to disk, hashing on the fly; resume with Range when the stream breaks."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    response, hops = walk(s, url, "GET", max_hops, timeout, headers, allow_private)
    if response.status_code != 200:
        response.close()
        raise NetError(f"{hops[-1].url}: HTTP {response.status_code}")
    final_url = hops[-1].url
    headers = {k.lower(): v for k, v in response.headers.items()}
    expected = _int(headers.get("content-length")) if "content-encoding" not in headers else None
    if expected is not None and expected > max_bytes:
        response.close()
        raise NetError(f"payload is {expected} bytes, above the {max_bytes} byte limit")
    name = _safe_name(final_url, headers.get("content-disposition"))
    target = dest_dir / name
    digest = hashlib.sha256()
    written = 0
    resumed = False
    attempt = 1
    with target.open("wb") as out:
        while True:
            try:
                for chunk in response.iter_content(chunk_size=256 * 1024):
                    if not chunk:
                        continue
                    written += len(chunk)
                    if written > max_bytes:
                        raise NetError(f"stream exceeded the {max_bytes} byte limit")
                    out.write(chunk)
                    digest.update(chunk)
                    if on_progress:
                        on_progress(written, expected)
                response.close()
                if expected is None or written == expected:
                    break
                raise requests.ConnectionError(f"stream ended at {written}/{expected} bytes")
            except (requests.ConnectionError, requests.Timeout, http.client.IncompleteRead) as exc:
                response.close()
                if attempt >= attempts:
                    raise NetError(f"download interrupted after {attempt} attempts: {exc}") from None
                attempt += 1
                accepts_ranges = headers.get("accept-ranges", "").lower() == "bytes"
                if accepts_ranges and written:
                    response, _ = walk(s, url, "GET", max_hops, timeout, {**(headers or {}), "Range": f"bytes={written}-"}, allow_private)
                    if response.status_code == 206:
                        resumed = True
                        continue
                    response.close()
                # no resume support: start over
                out.seek(0)
                out.truncate()
                digest = hashlib.sha256()
                written = 0
                response, _ = walk(s, url, "GET", max_hops, timeout, headers, allow_private)
    return Download(target, final_url, written, expected, digest.hexdigest().upper(), attempt, resumed, headers)


def _safe_name(url: str, disposition: str | None) -> str:
    name = ""
    if disposition and "filename=" in disposition:
        name = disposition.split("filename=", 1)[1].split(";", 1)[0].strip().strip('"')
    if not name:
        name = urlsplit(url).path.rsplit("/", 1)[-1]
    cleaned = "".join(c for c in name if c.isalnum() or c in "._-+")[:120].lstrip(".")
    return cleaned or "payload.bin"


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest().upper()


# --------------------------------------------------------------------------- geo probing


def doh_resolve(s: requests.Session, name: str, client_subnet: str | None = None, timeout: float = 10) -> list[str]:
    """A records as seen by a resolver near `client_subnet` (EDNS Client Subnet)."""
    params = {"name": name, "type": "A"}
    if client_subnet:
        params["edns_client_subnet"] = client_subnet
    response = s.get(DOH_ENDPOINT, params=params, timeout=timeout, headers={"Accept": "application/dns-json"})
    response.raise_for_status()
    answers = response.json().get("Answer") or []
    return [a["data"] for a in answers if a.get("type") == 1]


class _PinnedHTTPS(http.client.HTTPSConnection):
    """HTTPS to a chosen edge IP while still verifying the certificate for the real host."""

    def __init__(self, host: str, address: str, timeout: float):
        super().__init__(host, 443, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self) -> None:
        sock = socket.create_connection((self._address, 443), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


@dataclass
class EdgeResult:
    region: str
    address: str | None
    status: int | None
    elapsed_ms: int | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is not None and self.status < 400


def edge_probe(url: str, address: str, region: str, timeout: float = 15) -> EdgeResult:
    if not _is_public(address):
        return EdgeResult(region, address, None, None, "non-public edge address")
    parts = urlsplit(url)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    started = time.monotonic()
    status = None
    try:
        # Signed CDN links often reject HEAD; a 1-byte ranged GET is the reliable fallback.
        for method, extra in (("HEAD", {}), ("GET", {"Range": "bytes=0-0"})):
            conn = _PinnedHTTPS(parts.hostname, address, timeout)
            try:
                conn.request(method, path, headers={"User-Agent": USER_AGENT, "Host": parts.hostname, **extra})
                status = conn.getresponse().status
            finally:
                conn.close()
            if status not in (403, 405, 501):
                break
        return EdgeResult(region, address, status, int((time.monotonic() - started) * 1000))
    except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
        return EdgeResult(region, address, None, None, f"{type(exc).__name__}: {exc}")
