"""Content Extractor - Extracts content from crawled pages for AEM migration."""

import logging
import os
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..source_analysis.crawler import CrawledPage
from ..source_analysis.dom_decomposer import DOMSection

logger = logging.getLogger(__name__)


class ContentExtractor:
    """Extracts content (text, images, metadata) from crawled pages.

    Processes each section's HTML to extract clean content suitable
    for populating AEM component properties.
    """

    def __init__(self, config: dict):
        self.config = config.get("content_migration", {}).get("extract", {})
        self.include_assets = self.config.get("include_assets", True)
        self.download_images = self.config.get("download_images", True)
        self.max_image_width = self.config.get("max_image_width", 2048)
        self.assets_dir = None

    def extract_page_content(self, page: CrawledPage, sections: list[DOMSection]) -> dict:
        """Extract all content from a crawled page.

        Args:
            page: The crawled page.
            sections: Decomposed sections of the page.

        Returns:
            Dict with extracted content organized by section.
        """
        content = {
            "url": page.url,
            "title": page.title,
            "meta": page.meta,
            "sections": [],
            "assets": [],
        }

        for section in sections:
            extracted = self._extract_section_content(section, page.url)
            content["sections"].append(extracted)

        # Extract all assets
        if self.include_assets:
            content["assets"] = self._extract_all_assets(page)

        logger.info(f"Extracted content from {page.url}: {len(content['sections'])} sections")
        return content

    def download_assets(self, assets: list[dict], output_dir: str) -> list[dict]:
        """Download assets (images) for inclusion in AEM DAM.

        Args:
            assets: List of asset dicts with 'url' and 'type'.
            output_dir: Directory to save downloaded assets.

        Returns:
            Updated asset list with local paths.
        """
        self.assets_dir = Path(output_dir) / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        downloaded = []

        for asset in assets:
            if asset.get("type") != "image":
                continue

            url = asset.get("url", "")
            if not url:
                continue

            try:
                local_path = self._download_image(url)
                if local_path:
                    asset["local_path"] = str(local_path)
                    asset["dam_path"] = self._url_to_dam_path(url)
                    downloaded.append(asset)
            except Exception as e:
                logger.warning(f"Failed to download {url}: {e}")

        logger.info(f"Downloaded {len(downloaded)} assets")
        return downloaded

    def _extract_section_content(self, section: DOMSection, base_url: str) -> dict:
        """Extract content from a single section."""
        soup = BeautifulSoup(section.html, "lxml")

        extracted = {
            "section_type": section.section_type,
            "content": {},
        }

        # Extract headings
        headings = []
        for tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            for heading in soup.find_all(tag):
                headings.append({
                    "level": tag,
                    "text": heading.get_text(strip=True),
                })
        if headings:
            extracted["content"]["headings"] = headings

        # Extract text content
        paragraphs = []
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if text:
                # Get rich text (inner HTML)
                rich_text = "".join(str(child) for child in p.children)
                paragraphs.append({
                    "text": text,
                    "rich_text": rich_text,
                })
        if paragraphs:
            extracted["content"]["paragraphs"] = paragraphs

        # Extract images
        images = []
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src:
                images.append({
                    "src": urljoin(base_url, src),
                    "alt": img.get("alt", ""),
                    "title": img.get("title", ""),
                    "width": img.get("width", ""),
                    "height": img.get("height", ""),
                })
        if images:
            extracted["content"]["images"] = images

        # Extract links/CTAs
        links = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            if text:
                classes = a.get("class", [])
                is_cta = any(cls in " ".join(classes).lower() for cls in ["btn", "button", "cta"])
                links.append({
                    "text": text,
                    "href": urljoin(base_url, a["href"]),
                    "is_cta": is_cta,
                    "target": a.get("target", ""),
                })
        if links:
            extracted["content"]["links"] = links

        # Extract lists
        lists = []
        for ul in soup.find_all(["ul", "ol"]):
            items = [li.get_text(strip=True) for li in ul.find_all("li")]
            if items:
                lists.append({
                    "type": "ordered" if ul.name == "ol" else "unordered",
                    "items": items,
                })
        if lists:
            extracted["content"]["lists"] = lists

        return extracted

    def _extract_all_assets(self, page: CrawledPage) -> list[dict]:
        """Extract all downloadable assets from a page."""
        assets = []
        seen_urls = set()

        for asset in page.assets:
            url = asset.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                assets.append(asset)

        return assets

    def _download_image(self, url: str) -> Optional[Path]:
        """Download a single image."""
        try:
            response = requests.get(url, timeout=30, stream=True)
            response.raise_for_status()

            # Determine filename
            parsed = urlparse(url)
            filename = os.path.basename(parsed.path)
            if not filename or "." not in filename:
                content_type = response.headers.get("content-type", "")
                ext = ".jpg"
                if "png" in content_type:
                    ext = ".png"
                elif "gif" in content_type:
                    ext = ".gif"
                elif "webp" in content_type:
                    ext = ".webp"
                elif "svg" in content_type:
                    ext = ".svg"
                filename = f"image_{hash(url) % 10000}{ext}"

            # Sanitize filename
            filename = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
            local_path = self.assets_dir / filename

            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            return local_path

        except Exception as e:
            logger.warning(f"Failed to download image {url}: {e}")
            return None

    def _url_to_dam_path(self, url: str) -> str:
        """Convert an image URL to an AEM DAM path."""
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path)
        filename = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
        return f"/content/dam/{self.config.get('app_id', 'modernizedsite')}/{filename}"
