"""Downloads with a cache, and a clear error when a host is blocked or missing.

Every fetcher goes through `download()`. A file already in the cache is never
fetched again unless `force`. Failures raise `FetchError` with the host, so the
caller can record "blocked by policy at <host>" in meta.json instead of failing
the whole run.
"""
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "metro-transit-inputs/1.0 (+https://github.com/dgoodenough/dfw-transit)"


class FetchError(Exception):
    """A download failed. kind: 'blocked' (proxy/policy refused the host),
    'not_found' (HTTP 404/403 from the origin), 'http' (other status), 'network'."""

    def __init__(self, url, kind, detail):
        self.url, self.kind, self.detail = url, kind, detail
        self.host = urllib.parse.urlsplit(url).hostname
        super().__init__(f"{kind}: {url} ({detail})")

    def as_meta(self):
        return {"status": "blocked" if self.kind == "blocked" else "failed", "host": self.host,
                "url": self.url, "error": f"{self.kind}: {self.detail}"}


def _context():
    ca = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    return ssl.create_default_context(cafile=ca) if ca and os.path.exists(ca) else ssl.create_default_context()


def open_url(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        return urllib.request.urlopen(req, timeout=timeout, context=_context())
    except urllib.error.HTTPError as e:
        raise FetchError(url, "not_found" if e.code in (403, 404, 410) else "http", f"HTTP {e.code}") from None
    except (urllib.error.URLError, OSError) as e:
        msg = str(getattr(e, "reason", e))
        # A CONNECT refused by the egress proxy surfaces as "Tunnel connection failed: 403 ..."
        kind = "blocked" if ("Tunnel connection failed" in msg or "403" in msg or "407" in msg) else "network"
        raise FetchError(url, kind, msg) from None


def download(url, dest, force=False, timeout=120, quiet=False):
    """Fetch `url` to `dest` (atomically, via dest.part) unless it is cached. Returns dest."""
    if os.path.exists(dest) and os.path.getsize(dest) > 0 and not force:
        return dest
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    t0 = time.time()
    part = dest + ".part"
    with open_url(url, timeout) as r, open(part, "wb") as f:
        n = 0
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
            n += len(b)
    os.replace(part, dest)
    if not quiet:
        print(f"  downloaded {url} ({n / 1e6:.1f} MB, {time.time() - t0:.0f}s)")
    return dest


def first_available(urls, dest_for, force=False):
    """Try each URL in turn (e.g. newest LODES year first). A 404 moves on to the next;
    a blocked host stops at once (every URL on it will be blocked). Returns (url, path)."""
    if not force:
        for u in urls:
            p = dest_for(u)
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return u, p
    last = None
    for u in urls:
        try:
            return u, download(u, dest_for(u), force=force)
        except FetchError as e:
            if e.kind == "blocked":
                raise
            last = e
    raise last or FetchError(urls[0] if urls else "", "not_found", "no candidate URLs")
