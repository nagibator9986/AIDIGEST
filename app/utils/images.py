"""Preview-image extraction — pull an ``og:image`` from a web page.

Used lazily at digest-build time for the handful of items actually selected,
so a digest can be delivered as photos instead of a wall of text.
"""

from __future__ import annotations

from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.logging import get_logger

log = get_logger(__name__)

# Meta tags that carry a page's preview image, best first.
_IMAGE_META = ("og:image", "og:image:url", "og:image:secure_url", "twitter:image")
# Telegram fetches the photo by URL; keep these to formats it accepts.
_GOOD_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")


async def extract_image_url(client: httpx.AsyncClient, page_url: str) -> str | None:
    """Return the preview-image URL of *page_url*, or ``None`` if not found."""
    try:
        response = await client.get(page_url, headers={"Accept": "text/html"})
        response.raise_for_status()
    except httpx.HTTPError as exc:
        log.debug("image.fetch_failed", url=page_url, error=str(exc))
        return None
    if "html" not in response.headers.get("content-type", ""):
        return None

    try:
        soup = BeautifulSoup(response.text, "lxml")
    except Exception:
        return None

    for key in _IMAGE_META:
        tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        content = tag.get("content") if tag else None
        if not content:
            continue
        url = urljoin(page_url, str(content).strip())
        if url.startswith(("http://", "https://")):
            return url
    return None


def looks_like_image(url: str | None) -> bool:
    """Heuristic: a URL worth handing to Telegram as a photo."""
    if not url or not url.startswith(("http://", "https://")):
        return False
    path = url.split("?", 1)[0].lower()
    # Accept known image suffixes, or extension-less CDN URLs (common for OG).
    return path.endswith(_GOOD_SUFFIXES) or "." not in path.rsplit("/", 1)[-1]
