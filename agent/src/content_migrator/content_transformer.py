"""Content Transformer - Transforms extracted content into AEM JCR node structures."""

import logging
from typing import Optional

from ..figma_pipeline.aem_mapper import AEMComponentSpec
from ..source_analysis.component_classifier import ComponentClassification
from ..utils.aem_utils import AEMUtils
from ..utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


class ContentTransformer:
    """Transforms extracted content into AEM-compatible JCR node structures.

    Maps content from source sections to AEM component properties,
    creating the node tree that will be packaged for deployment.
    """

    def __init__(self, config: dict):
        self.config = config
        self.aem_utils = AEMUtils(config)
        self.llm_client = LLMClient(config)

    def transform_page(
        self,
        page_content: dict,
        classifications: list[ComponentClassification],
        component_specs: list[AEMComponentSpec],
    ) -> dict:
        """Transform a page's extracted content into AEM JCR structure.

        Args:
            page_content: Extracted page content from ContentExtractor.
            classifications: Component classifications from classifier.
            component_specs: Generated component specs.

        Returns:
            JCR node structure dict for the page.
        """
        jcr_structure = {
            "jcr:primaryType": "cq:Page",
            "jcr:content": {
                "jcr:primaryType": "cq:PageContent",
                "jcr:title": page_content.get("title", ""),
                "sling:resourceType": f"{self.aem_utils.app_id}/components/page",
                "root": {
                    "jcr:primaryType": "nt:unstructured",
                    "sling:resourceType": "wcm/foundation/components/responsivegrid",
                },
            },
        }

        root = jcr_structure["jcr:content"]["root"]
        sections = page_content.get("sections", [])

        for i, (section, classification) in enumerate(
            zip(sections, classifications)
        ):
            node_name = f"component_{i}"
            component_node = self._transform_section(section, classification, component_specs)
            if component_node:
                root[node_name] = component_node

        # Add metadata
        meta = page_content.get("meta", {})
        if meta.get("description"):
            jcr_structure["jcr:content"]["jcr:description"] = meta["description"]
        if meta.get("og:image"):
            jcr_structure["jcr:content"]["socialMediaImage"] = meta["og:image"]

        return jcr_structure

    def _transform_section(
        self,
        section: dict,
        classification: ComponentClassification,
        component_specs: list[AEMComponentSpec],
    ) -> Optional[dict]:
        """Transform a single section into a JCR component node."""
        content = section.get("content", {})
        section_type = section.get("section_type", "")

        if classification.component_type in ("core_component", "core_extension"):
            return self._transform_to_core_component(content, classification)
        elif classification.component_type == "custom_component":
            return self._transform_to_custom_component(content, classification, component_specs)
        elif classification.component_type == "container":
            return self._transform_to_container(content, classification)

        return None

    def _transform_to_core_component(
        self, content: dict, classification: ComponentClassification
    ) -> dict:
        """Transform content to a core component node."""
        node = {
            "jcr:primaryType": "nt:unstructured",
            "sling:resourceType": classification.resource_type,
        }

        core_name = classification.core_component_name

        if core_name == "title":
            headings = content.get("headings", [])
            if headings:
                node["jcr:title"] = headings[0].get("text", "")
                node["type"] = headings[0].get("level", "h2")

        elif core_name == "text":
            paragraphs = content.get("paragraphs", [])
            if paragraphs:
                rich_text = "\n".join(
                    f"<p>{p.get('rich_text', p.get('text', ''))}</p>"
                    for p in paragraphs
                )
                node["text"] = rich_text
                node["textIsRich"] = True

        elif core_name == "image":
            images = content.get("images", [])
            if images:
                img = images[0]
                node["fileReference"] = img.get("dam_path", img.get("src", ""))
                node["alt"] = img.get("alt", "")
                if img.get("title"):
                    node["jcr:title"] = img["title"]

        elif core_name == "button":
            links = content.get("links", [])
            cta_links = [l for l in links if l.get("is_cta")]
            if cta_links:
                node["text"] = cta_links[0].get("text", "")
                node["link"] = cta_links[0].get("href", "")

        elif core_name == "teaser":
            headings = content.get("headings", [])
            paragraphs = content.get("paragraphs", [])
            images = content.get("images", [])
            links = content.get("links", [])

            if headings:
                node["jcr:title"] = headings[0].get("text", "")
            if paragraphs:
                node["jcr:description"] = paragraphs[0].get("text", "")
            if images:
                node["fileReference"] = images[0].get("dam_path", images[0].get("src", ""))
            cta_links = [l for l in links if l.get("is_cta")]
            if cta_links:
                node["actionsEnabled"] = True
                node["actions"] = {
                    "jcr:primaryType": "nt:unstructured",
                    "item0": {
                        "jcr:primaryType": "nt:unstructured",
                        "text": cta_links[0].get("text", ""),
                        "link": cta_links[0].get("href", ""),
                    },
                }

        elif core_name == "list":
            # Configure as static list
            items = content.get("lists", [])
            if items:
                node["listFrom"] = "static"
                for i, item_list in enumerate(items):
                    for j, item_text in enumerate(item_list.get("items", [])):
                        node[f"item_{i}_{j}"] = {
                            "jcr:primaryType": "nt:unstructured",
                            "jcr:title": item_text,
                        }

        elif core_name in ("navigation", "breadcrumb"):
            # These are configured via policies, not content
            pass

        return node

    def _transform_to_custom_component(
        self,
        content: dict,
        classification: ComponentClassification,
        component_specs: list[AEMComponentSpec],
    ) -> dict:
        """Transform content to a custom component node."""
        node = {
            "jcr:primaryType": "nt:unstructured",
            "sling:resourceType": classification.resource_type
            or self.aem_utils.get_component_resource_type(
                classification.suggested_name or "custom"
            ),
        }

        # Map content to properties based on classification
        for prop in classification.properties or []:
            prop_name = prop.get("name", "")
            prop_value = prop.get("value")

            if prop_value:
                node[prop_name] = prop_value

        # Fall back to generic content mapping
        headings = content.get("headings", [])
        paragraphs = content.get("paragraphs", [])
        images = content.get("images", [])
        links = content.get("links", [])

        if headings and "title" not in node and "jcr:title" not in node:
            node["jcr:title"] = headings[0].get("text", "")
        if paragraphs and "text" not in node:
            node["text"] = paragraphs[0].get("rich_text", paragraphs[0].get("text", ""))
        if images and "fileReference" not in node:
            node["fileReference"] = images[0].get("src", "")
        if links:
            cta = next((l for l in links if l.get("is_cta")), None)
            if cta and "ctaLink" not in node:
                node["ctaText"] = cta.get("text", "")
                node["ctaLink"] = cta.get("href", "")

        return node

    def _transform_to_container(
        self, content: dict, classification: ComponentClassification
    ) -> dict:
        """Transform content to a container/layout component node."""
        return {
            "jcr:primaryType": "nt:unstructured",
            "sling:resourceType": "wcm/foundation/components/responsivegrid",
        }
