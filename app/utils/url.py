"""URL normalisation — the first line of defence against duplicate news.

Two URLs that point at the same story but differ in tracking params, scheme,
``www`` prefix or trailing slash must normalise to the same string so the
``UNIQUE`` constraint on ``news_items.normalized_url`` catches the duplicate.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Query parameters that never identify content — strip them entirely.
_TRACKING_PREFIXES = ("utm_", "ref_", "mc_")
_TRACKING_KEYS = {
    "ref",
    "source",
    "src",
    "fbclid",
    "gclid",
    "igshid",
    "spm",
    "cmpid",
    "_hsenc",
    "_hsmi",
}


def normalize_url(url: str) -> str:
    """Return a canonical form of *url* suitable for equality comparison."""
    url = (url or "").strip()
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url

    parsed = urlparse(url)

    scheme = "https"
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    netloc = netloc.removesuffix(":80").removesuffix(":443")

    path = parsed.path.rstrip("/") or "/"

    keep = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        if key.lower() not in _TRACKING_KEYS and not key.lower().startswith(_TRACKING_PREFIXES)
    ]
    query = urlencode(sorted(keep))

    # Fragments never identify distinct content for our sources.
    return urlunparse((scheme, netloc, path, "", query, ""))


def domain_of(url: str) -> str:
    """Return the bare registrable-ish domain of *url* (best effort)."""
    netloc = urlparse(normalize_url(url)).netloc
    return netloc or url
