"""Site Crawler - Crawls source websites and collects page HTML for analysis."""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class CrawledPage:
    """Represents a single crawled page."""

    url: str
    html: str
    title: str = ""
    status_code: int = 200
    content_type: str = ""
    depth: int = 0
    links: list = field(default_factory=list)
    assets: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)


class SiteCrawler:
    """Crawls a website and collects pages for component analysis.

    Respects robots.txt, rate limits, and depth constraints.
    """

    def __init__(self, config: dict):
        crawler_config = config.get("source_analysis", {}).get("crawler", {})
        self.max_pages = crawler_config.get("max_pages", 50)
        self.max_depth = crawler_config.get("max_depth", 5)
        self.timeout = crawler_config.get("timeout_seconds", 30)
        self.user_agent = crawler_config.get("user_agent", "AEM-Modernization-Agent/1.0")
        self.delay = crawler_config.get("delay_between_requests", 1.0)

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})

        self.visited: set[str] = set()
        self.pages: list[CrawledPage] = []
        self.base_domain: str = ""

    def crawl(self, start_url: str) -> list[CrawledPage]:
        """Crawl a website starting from the given URL.

        Args:
            start_url: The URL to start crawling from.

        Returns:
            List of CrawledPage objects.
        """
        parsed = urlparse(start_url)
        self.base_domain = parsed.netloc
        logger.info(f"Starting crawl of {start_url} (max {self.max_pages} pages, depth {self.max_depth})")

        self._crawl_page(start_url, depth=0)

        logger.info(f"Crawl complete: {len(self.pages)} pages collected")
        return self.pages

    def _crawl_page(self, url: str, depth: int) -> None:
        """Recursively crawl a single page and its links."""
        # Normalize URL
        url = self._normalize_url(url)

        # Check stop conditions
        if url in self.visited:
            return
        if len(self.pages) >= self.max_pages:
            return
        if depth > self.max_depth:
            return
        if not self._is_same_domain(url):
            return

        self.visited.add(url)

        try:
            logger.info(f"Crawling [{depth}]: {url}")
            response = self.session.get(url, timeout=self.timeout)
            content_type = response.headers.get("content-type", "")

            # Only process HTML pages
            if "text/html" not in content_type:
                return

            html = response.text
            soup = BeautifulSoup(html, "lxml")

            # Extract page metadata
            title = soup.title.string if soup.title else ""
            meta = self._extract_meta(soup)
            links = self._extract_links(soup, url)
            assets = self._extract_assets(soup, url)

            page = CrawledPage(
                url=url,
                html=html,
                title=title or "",
                status_code=response.status_code,
                content_type=content_type,
                depth=depth,
                links=links,
                assets=assets,
                meta=meta,
            )
            self.pages.append(page)

            # Rate limiting
            time.sleep(self.delay)

            # Recursively crawl linked pages
            for link in links:
                if len(self.pages) >= self.max_pages:
                    break
                self._crawl_page(link, depth + 1)

        except requests.RequestException as e:
            logger.warning(f"Failed to crawl {url}: {e}")
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")

    def crawl_single_page(self, url: str) -> Optional[CrawledPage]:
        """Crawl a single page without following links.

        Args:
            url: The URL to crawl.

        Returns:
            CrawledPage or None if failed.
        """
        try:
            response = self.session.get(url, timeout=self.timeout)
            soup = BeautifulSoup(response.text, "lxml")

            return CrawledPage(
                url=url,
                html=response.text,
                title=soup.title.string if soup.title else "",
                status_code=response.status_code,
                content_type=response.headers.get("content-type", ""),
                depth=0,
                links=self._extract_links(soup, url),
                assets=self._extract_assets(soup, url),
                meta=self._extract_meta(soup),
            )
        except Exception as e:
            logger.error(f"Failed to crawl single page {url}: {e}")
            return None

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """Extract all internal links from a page."""
        links = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            absolute_url = urljoin(base_url, href)
            normalized = self._normalize_url(absolute_url)

            if self._is_same_domain(normalized) and self._is_valid_page_url(normalized):
                links.append(normalized)

        return list(set(links))

    def _extract_assets(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        """Extract all assets (images, scripts, stylesheets) from a page."""
        assets = []

        # Images
        for img in soup.find_all("img", src=True):
            assets.append({
                "type": "image",
                "url": urljoin(base_url, img["src"]),
                "alt": img.get("alt", ""),
            })

        # Stylesheets
        for link in soup.find_all("link", rel="stylesheet"):
            if link.get("href"):
                assets.append({
                    "type": "stylesheet",
                    "url": urljoin(base_url, link["href"]),
                })

        # Scripts
        for script in soup.find_all("script", src=True):
            assets.append({
                "type": "script",
                "url": urljoin(base_url, script["src"]),
            })

        return assets

    def _extract_meta(self, soup: BeautifulSoup) -> dict:
        """Extract meta tags from a page."""
        meta = {}
        for tag in soup.find_all("meta"):
            name = tag.get("name") or tag.get("property", "")
            content = tag.get("content", "")
            if name and content:
                meta[name] = content
        return meta

    def _normalize_url(self, url: str) -> str:
        """Normalize URL by removing fragments and trailing slashes."""
        parsed = urlparse(url)
        # Remove fragment, normalize path
        normalized = parsed._replace(fragment="")
        result = normalized.geturl().rstrip("/")
        return result

    def _is_same_domain(self, url: str) -> bool:
        """Check if a URL belongs to the same domain."""
        parsed = urlparse(url)
        return parsed.netloc == self.base_domain

    def _is_valid_page_url(self, url: str) -> bool:
        """Check if URL is likely a valid page (not an asset or special URL)."""
        parsed = urlparse(url)
        path = parsed.path.lower()

        # Skip common non-page extensions
        skip_extensions = {
            ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
            ".pdf", ".doc", ".docx", ".xls", ".xlsx",
            ".zip", ".tar", ".gz",
            ".js", ".css", ".map",
            ".xml", ".json", ".rss",
            ".mp4", ".mp3", ".avi", ".mov",
        }

        for ext in skip_extensions:
            if path.endswith(ext):
                return False

        # Skip common non-content paths
        skip_paths = {"/wp-admin", "/admin", "/login", "/logout", "/api/", "/feed"}
        for skip in skip_paths:
            if skip in path:
                return False

        return True
