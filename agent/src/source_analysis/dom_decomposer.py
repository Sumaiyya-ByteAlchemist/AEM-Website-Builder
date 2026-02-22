"""DOM Decomposer - Breaks down page HTML into semantic sections and component candidates."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


@dataclass
class DOMSection:
    """Represents a semantic section of a page."""

    section_type: str  # header, navigation, hero, content, sidebar, footer, etc.
    html: str  # Raw HTML of this section
    tag: str  # The HTML tag
    classes: list = field(default_factory=list)
    id: Optional[str] = None
    text_content: str = ""
    children_count: int = 0
    depth: int = 0
    attributes: dict = field(default_factory=dict)
    parent_section: Optional[str] = None
    # Extracted sub-components
    sub_components: list = field(default_factory=list)


@dataclass
class PageStructure:
    """Represents the full decomposed structure of a page."""

    url: str
    title: str
    sections: list[DOMSection] = field(default_factory=list)
    template_regions: list[str] = field(default_factory=list)
    component_candidates: list[dict] = field(default_factory=list)


class DOMDecomposer:
    """Decomposes page HTML into semantic sections for component mapping.

    Uses a combination of semantic HTML5 tags, common CSS class patterns,
    and structural heuristics to identify page regions and component candidates.
    """

    # Semantic section detection patterns
    SECTION_PATTERNS = {
        "header": {
            "tags": ["header"],
            "class_patterns": [
                r"header", r"site-header", r"page-header", r"top-bar",
                r"masthead", r"banner",
            ],
            "id_patterns": [r"header", r"site-header", r"masthead"],
        },
        "navigation": {
            "tags": ["nav"],
            "class_patterns": [
                r"nav", r"navigation", r"navbar", r"menu",
                r"main-nav", r"site-nav", r"primary-nav",
            ],
            "id_patterns": [r"nav", r"navigation", r"main-nav"],
        },
        "hero": {
            "tags": [],
            "class_patterns": [
                r"hero", r"hero-banner", r"jumbotron", r"banner",
                r"splash", r"masthead", r"hero-section",
            ],
            "id_patterns": [r"hero", r"hero-banner"],
        },
        "content": {
            "tags": ["main", "article"],
            "class_patterns": [
                r"content", r"main-content", r"page-content",
                r"article", r"post-content", r"entry-content",
            ],
            "id_patterns": [r"content", r"main-content", r"main"],
        },
        "sidebar": {
            "tags": ["aside"],
            "class_patterns": [
                r"sidebar", r"aside", r"side-bar", r"widget-area",
                r"secondary", r"rail",
            ],
            "id_patterns": [r"sidebar", r"aside"],
        },
        "footer": {
            "tags": ["footer"],
            "class_patterns": [
                r"footer", r"site-footer", r"page-footer",
                r"bottom-bar", r"colophon",
            ],
            "id_patterns": [r"footer", r"site-footer"],
        },
        "form": {
            "tags": ["form"],
            "class_patterns": [
                r"form", r"contact-form", r"search-form",
                r"newsletter", r"signup",
            ],
            "id_patterns": [r"form", r"contact-form"],
        },
        "carousel": {
            "tags": [],
            "class_patterns": [
                r"carousel", r"slider", r"slideshow", r"swiper",
                r"slick", r"owl-carousel", r"glide",
            ],
            "id_patterns": [r"carousel", r"slider"],
        },
        "accordion": {
            "tags": [],
            "class_patterns": [
                r"accordion", r"collapse", r"expandable",
                r"faq", r"toggle-panel",
            ],
            "id_patterns": [r"accordion", r"faq"],
        },
        "tabs": {
            "tags": [],
            "class_patterns": [
                r"tabs", r"tab-container", r"tabbed",
                r"tab-panel", r"tab-content",
            ],
            "id_patterns": [r"tabs"],
        },
        "card": {
            "tags": [],
            "class_patterns": [
                r"card", r"teaser", r"feature", r"promo",
                r"tile", r"content-card",
            ],
            "id_patterns": [],
        },
        "breadcrumb": {
            "tags": [],
            "class_patterns": [r"breadcrumb", r"breadcrumbs", r"crumbs"],
            "id_patterns": [r"breadcrumb"],
        },
    }

    # Sub-component patterns within sections
    SUB_COMPONENT_PATTERNS = {
        "image": {"tags": ["img", "picture", "figure"], "class_patterns": [r"image", r"media", r"photo"]},
        "heading": {"tags": ["h1", "h2", "h3", "h4", "h5", "h6"], "class_patterns": [r"title", r"heading"]},
        "text": {"tags": ["p"], "class_patterns": [r"text", r"description", r"body"]},
        "button": {"tags": ["button"], "class_patterns": [r"btn", r"button", r"cta"]},
        "link": {"tags": ["a"], "class_patterns": [r"link", r"action"]},
        "list": {"tags": ["ul", "ol"], "class_patterns": [r"list", r"items"]},
        "video": {"tags": ["video", "iframe"], "class_patterns": [r"video", r"player"]},
    }

    def __init__(self, config: dict):
        self.config = config.get("source_analysis", {}).get("dom_decomposition", {})
        self.target_sections = self.config.get("semantic_sections", list(self.SECTION_PATTERNS.keys()))

    def decompose(self, url: str, html: str, title: str = "") -> PageStructure:
        """Decompose a page's HTML into semantic sections.

        Args:
            url: The page URL.
            html: Raw HTML content.
            title: Page title.

        Returns:
            PageStructure with identified sections.
        """
        soup = BeautifulSoup(html, "lxml")
        body = soup.find("body")
        if not body:
            logger.warning(f"No <body> tag found for {url}")
            return PageStructure(url=url, title=title)

        # Remove script and style tags for cleaner analysis
        for tag in body.find_all(["script", "style", "noscript"]):
            tag.decompose()

        sections = []
        template_regions = []

        # Phase 1: Identify top-level semantic sections
        sections = self._identify_sections(body, depth=0)

        # Phase 2: Extract sub-components within each section
        for section in sections:
            section.sub_components = self._extract_sub_components(section.html)

        # Phase 3: Identify template regions
        template_regions = self._identify_template_regions(sections)

        # Phase 4: Generate component candidates
        component_candidates = self._generate_component_candidates(sections)

        structure = PageStructure(
            url=url,
            title=title,
            sections=sections,
            template_regions=template_regions,
            component_candidates=component_candidates,
        )

        logger.info(
            f"Decomposed {url}: {len(sections)} sections, "
            f"{len(template_regions)} template regions, "
            f"{len(component_candidates)} component candidates"
        )
        return structure

    def _identify_sections(self, element: Tag, depth: int = 0) -> list[DOMSection]:
        """Identify semantic sections within an element."""
        sections = []

        if not isinstance(element, Tag):
            return sections

        for child in element.children:
            if not isinstance(child, Tag):
                continue

            section_type = self._classify_element(child)

            if section_type:
                section = DOMSection(
                    section_type=section_type,
                    html=str(child),
                    tag=child.name,
                    classes=child.get("class", []),
                    id=child.get("id"),
                    text_content=child.get_text(strip=True)[:500],
                    children_count=len(list(child.children)),
                    depth=depth,
                    attributes={k: v for k, v in child.attrs.items() if k not in ("class", "id")},
                )
                sections.append(section)
            else:
                # Check if this is a generic container that wraps semantic sections
                if child.name in ("div", "section") and len(list(child.children)) > 0:
                    inner_sections = self._identify_sections(child, depth + 1)
                    if inner_sections:
                        sections.extend(inner_sections)
                    elif self._is_significant_element(child):
                        # Treat as a generic content section
                        section = DOMSection(
                            section_type="content",
                            html=str(child),
                            tag=child.name,
                            classes=child.get("class", []),
                            id=child.get("id"),
                            text_content=child.get_text(strip=True)[:500],
                            children_count=len(list(child.children)),
                            depth=depth,
                        )
                        sections.append(section)

        return sections

    def _classify_element(self, element: Tag) -> Optional[str]:
        """Classify an HTML element as a semantic section type."""
        tag_name = element.name
        classes = " ".join(element.get("class", []))
        element_id = element.get("id", "")

        for section_type, patterns in self.SECTION_PATTERNS.items():
            if section_type not in self.target_sections:
                continue

            # Check tag match
            if tag_name in patterns["tags"]:
                return section_type

            # Check class patterns
            for pattern in patterns["class_patterns"]:
                if re.search(pattern, classes, re.IGNORECASE):
                    return section_type

            # Check ID patterns
            for pattern in patterns["id_patterns"]:
                if re.search(pattern, element_id, re.IGNORECASE):
                    return section_type

        return None

    def _extract_sub_components(self, html: str) -> list[dict]:
        """Extract sub-component candidates from a section's HTML."""
        soup = BeautifulSoup(html, "lxml")
        sub_components = []

        for comp_type, patterns in self.SUB_COMPONENT_PATTERNS.items():
            # Check by tag
            for tag in patterns["tags"]:
                for element in soup.find_all(tag):
                    sub_components.append({
                        "type": comp_type,
                        "tag": tag,
                        "html": str(element)[:500],
                        "attributes": dict(element.attrs) if hasattr(element, "attrs") else {},
                    })

            # Check by class patterns
            for pattern in patterns["class_patterns"]:
                for element in soup.find_all(class_=re.compile(pattern, re.IGNORECASE)):
                    if element.name not in patterns["tags"]:  # Avoid duplicates
                        sub_components.append({
                            "type": comp_type,
                            "tag": element.name,
                            "html": str(element)[:500],
                            "classes": element.get("class", []),
                        })

        return sub_components

    def _identify_template_regions(self, sections: list[DOMSection]) -> list[str]:
        """Identify which sections represent template-level regions.

        Template regions are structural areas that define the page layout:
        header, footer, navigation, and main content area.
        """
        template_regions = []
        region_types = {"header", "navigation", "footer", "sidebar", "content"}

        for section in sections:
            if section.section_type in region_types:
                template_regions.append(section.section_type)

        return list(dict.fromkeys(template_regions))  # Preserve order, remove duplicates

    def _generate_component_candidates(self, sections: list[DOMSection]) -> list[dict]:
        """Generate component candidates from decomposed sections."""
        candidates = []

        for section in sections:
            candidate = {
                "section_type": section.section_type,
                "tag": section.tag,
                "classes": section.classes,
                "id": section.id,
                "html_preview": section.html[:1000],
                "sub_components": section.sub_components,
                "children_count": section.children_count,
                "has_images": any(sc["type"] == "image" for sc in section.sub_components),
                "has_text": any(sc["type"] == "text" for sc in section.sub_components),
                "has_headings": any(sc["type"] == "heading" for sc in section.sub_components),
                "has_buttons": any(sc["type"] == "button" for sc in section.sub_components),
                "has_links": any(sc["type"] == "link" for sc in section.sub_components),
            }
            candidates.append(candidate)

        return candidates

    def _is_significant_element(self, element: Tag) -> bool:
        """Determine if an element is significant enough to be a section."""
        text = element.get_text(strip=True)
        children = list(element.children)
        tag_children = [c for c in children if isinstance(c, Tag)]

        # Must have some content
        if len(text) < 20 and len(tag_children) < 2:
            return False

        # Must not be too deeply nested trivial wrapper
        if len(tag_children) == 1 and tag_children[0].name == "div":
            return False

        return True
