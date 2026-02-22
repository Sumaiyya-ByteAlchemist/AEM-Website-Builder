"""Component Classifier - Uses LLM and heuristics to classify DOM sections as AEM components."""

import logging
import re
from dataclasses import dataclass
from typing import Optional

import yaml

from ..utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class ComponentClassification:
    """Result of classifying a DOM section as an AEM component."""

    # Classification category
    component_type: str  # core_component, core_extension, custom_component, container, template_region
    # Core component name if applicable
    core_component_name: Optional[str] = None
    # sling:resourceType
    resource_type: str = ""
    # Confidence score 0-1
    confidence: float = 0.0
    # Explanation
    rationale: str = ""
    # Suggested custom component name
    suggested_name: str = ""
    # Extracted properties
    properties: list = None
    # Suggested child components
    children: list = None

    def __post_init__(self):
        if self.properties is None:
            self.properties = []
        if self.children is None:
            self.children = []


class ComponentClassifier:
    """Classifies DOM sections as AEM component types.

    Uses a multi-pass approach:
    1. Rule-based heuristic matching against known patterns
    2. LLM-based classification for uncertain cases
    """

    def __init__(self, config: dict, mappings: dict):
        """Initialize the classifier.

        Args:
            config: Agent configuration.
            mappings: Component mappings from component_mappings.yaml.
        """
        self.config = config.get("source_analysis", {}).get("classification", {})
        self.min_confidence = self.config.get("min_confidence", 0.7)
        self.fallback_category = self.config.get("fallback_category", "custom_component")
        self.mappings = mappings
        self.core_components = mappings.get("core_components", {})
        self.llm_client = LLMClient(config)

    def classify(self, candidate: dict, page_context: str = "") -> ComponentClassification:
        """Classify a component candidate.

        Args:
            candidate: Component candidate dict from DOM decomposer.
            page_context: Additional context about the page.

        Returns:
            ComponentClassification result.
        """
        # Phase 1: Try rule-based classification
        heuristic_result = self._heuristic_classify(candidate)

        if heuristic_result and heuristic_result.confidence >= self.min_confidence:
            logger.info(
                f"Heuristic classification: {heuristic_result.core_component_name} "
                f"(confidence: {heuristic_result.confidence:.2f})"
            )
            return heuristic_result

        # Phase 2: Use LLM for uncertain cases
        llm_result = self._llm_classify(candidate, page_context)
        logger.info(
            f"LLM classification: {llm_result.component_type}/{llm_result.core_component_name} "
            f"(confidence: {llm_result.confidence:.2f})"
        )
        return llm_result

    def classify_batch(self, candidates: list[dict], page_context: str = "") -> list[ComponentClassification]:
        """Classify multiple candidates.

        Args:
            candidates: List of component candidate dicts.
            page_context: Page-level context.

        Returns:
            List of classifications.
        """
        results = []
        for candidate in candidates:
            result = self.classify(candidate, page_context)
            results.append(result)
        return results

    def _heuristic_classify(self, candidate: dict) -> Optional[ComponentClassification]:
        """Apply rule-based heuristics for classification."""
        section_type = candidate.get("section_type", "")
        tag = candidate.get("tag", "")
        classes = candidate.get("classes", [])
        classes_str = " ".join(classes).lower()
        html_preview = candidate.get("html_preview", "")

        best_match = None
        best_confidence = 0.0

        for comp_name, comp_def in self.core_components.items():
            confidence = self._calculate_match_confidence(
                comp_name, comp_def, section_type, tag, classes_str, html_preview, candidate
            )

            if confidence > best_confidence:
                best_confidence = confidence
                best_match = comp_name

        if best_match and best_confidence >= 0.5:
            comp_def = self.core_components[best_match]
            resource_type = comp_def.get("resource_type", "")

            # Determine if this is a direct core component match or needs extension
            component_type = "core_component"
            if self._needs_extension(candidate, comp_def):
                component_type = "core_extension"

            return ComponentClassification(
                component_type=component_type,
                core_component_name=best_match,
                resource_type=resource_type,
                confidence=best_confidence,
                rationale=f"Heuristic match to Core Component '{best_match}'",
                properties=self._extract_initial_properties(candidate, comp_def),
            )

        return None

    def _calculate_match_confidence(
        self,
        comp_name: str,
        comp_def: dict,
        section_type: str,
        tag: str,
        classes_str: str,
        html_preview: str,
        candidate: dict,
    ) -> float:
        """Calculate confidence score for a component match."""
        score = 0.0
        max_score = 0.0

        patterns = comp_def.get("patterns", [])

        for pattern in patterns:
            if isinstance(pattern, dict):
                # Tag matching
                if "tag" in pattern:
                    max_score += 0.3
                    pattern_tags = pattern["tag"].split(",")
                    if tag in pattern_tags:
                        score += 0.3

                # Class pattern matching
                if "class_patterns" in pattern:
                    max_score += 0.4
                    for cls_pattern in pattern["class_patterns"]:
                        if re.search(cls_pattern, classes_str, re.IGNORECASE):
                            score += 0.4
                            break

                # Context matching
                if "context" in pattern:
                    max_score += 0.2
                    context = pattern["context"].lower()
                    if section_type and section_type.lower() in context:
                        score += 0.2

        # Section type direct match bonus
        if section_type == comp_name:
            score += 0.3
            max_score += 0.3

        # Sub-component structure matching
        sub_comps = candidate.get("sub_components", [])
        if comp_name == "teaser" and candidate.get("has_images") and candidate.get("has_headings"):
            score += 0.2
            max_score += 0.2
        elif comp_name == "navigation" and section_type == "navigation":
            score += 0.3
            max_score += 0.3

        return score / max_score if max_score > 0 else 0.0

    def _needs_extension(self, candidate: dict, comp_def: dict) -> bool:
        """Determine if a candidate needs a Core Component extension."""
        sub_components = candidate.get("sub_components", [])
        defined_properties = {p["name"] for p in comp_def.get("properties", [])}
        sub_types = {sc["type"] for sc in sub_components}

        # If there are many sub-component types not covered by the core properties
        extra_types = sub_types - {"text", "heading", "image", "button", "link"}
        if len(extra_types) > 2:
            return True

        # If HTML is complex with many children
        if candidate.get("children_count", 0) > 10:
            return True

        return False

    def _extract_initial_properties(self, candidate: dict, comp_def: dict) -> list:
        """Extract initial property values from the candidate HTML."""
        properties = []
        for prop in comp_def.get("properties", []):
            properties.append({
                "name": prop["name"],
                "type": prop.get("type", "String"),
                "value": None,  # Will be filled during content extraction
            })
        return properties

    def _llm_classify(self, candidate: dict, page_context: str) -> ComponentClassification:
        """Use LLM to classify a component candidate."""
        html_snippet = candidate.get("html_preview", "")
        context = (
            f"Section type: {candidate.get('section_type', 'unknown')}\n"
            f"Tag: {candidate.get('tag', '')}\n"
            f"Classes: {', '.join(candidate.get('classes', []))}\n"
            f"Page context: {page_context}\n"
            f"Has images: {candidate.get('has_images', False)}\n"
            f"Has headings: {candidate.get('has_headings', False)}\n"
            f"Has buttons: {candidate.get('has_buttons', False)}\n"
            f"Children count: {candidate.get('children_count', 0)}"
        )

        try:
            result = self.llm_client.classify_component(html_snippet, context, self.mappings)

            if result.get("parse_error"):
                return ComponentClassification(
                    component_type=self.fallback_category,
                    confidence=0.3,
                    rationale="LLM classification failed to parse",
                    suggested_name=candidate.get("section_type", "unknown-component"),
                )

            return ComponentClassification(
                component_type=result.get("component_type", self.fallback_category),
                core_component_name=result.get("core_component_name"),
                resource_type=result.get("resource_type", ""),
                confidence=result.get("confidence", 0.5),
                rationale=result.get("rationale", ""),
                suggested_name=result.get("suggested_name", ""),
                properties=result.get("properties", []),
                children=result.get("children", []),
            )
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return ComponentClassification(
                component_type=self.fallback_category,
                confidence=0.3,
                rationale=f"LLM classification error: {e}",
                suggested_name=candidate.get("section_type", "unknown-component"),
            )
