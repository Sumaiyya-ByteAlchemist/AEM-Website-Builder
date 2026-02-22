"""Figma-to-AEM Mapper - Maps parsed Figma components to AEM component definitions."""

import logging
from dataclasses import dataclass, field
from typing import Optional

from ..utils.aem_utils import AEMUtils
from ..utils.llm_client import LLMClient
from .design_parser import ParsedDesignComponent

logger = logging.getLogger(__name__)


@dataclass
class AEMComponentSpec:
    """Complete specification for generating an AEM component."""

    name: str
    title: str
    # Classification
    component_type: str  # core_component, core_extension, custom_component
    core_component_name: Optional[str] = None
    resource_type: str = ""
    super_type: Optional[str] = None  # For extensions
    component_group: str = "Content"
    # Properties for the dialog
    properties: list = field(default_factory=list)
    # Design tokens / CSS
    design_tokens: dict = field(default_factory=dict)
    css_classes: list = field(default_factory=list)
    # Content structure
    content_slots: list = field(default_factory=list)
    # Variants (Style System)
    style_system_styles: list = field(default_factory=list)
    # Layout info
    is_container: bool = False
    allowed_children: list = field(default_factory=list)
    # Responsive
    responsive_config: dict = field(default_factory=dict)
    # Source reference
    figma_id: str = ""
    source_html: str = ""


class FigmaToAEMMapper:
    """Maps Figma design components to AEM component specifications.

    Combines design analysis with AEM component knowledge to produce
    complete component specs ready for code generation.
    """

    # Mapping of design patterns to AEM Core Components
    DESIGN_TO_CORE = {
        "hero": {"core": "teaser", "group": "Content"},
        "card": {"core": "teaser", "group": "Content"},
        "teaser": {"core": "teaser", "group": "Content"},
        "banner": {"core": "teaser", "group": "Content"},
        "navigation": {"core": "navigation", "group": "Structure"},
        "header": {"core": "experiencefragment", "group": "Structure"},
        "footer": {"core": "experiencefragment", "group": "Structure"},
        "breadcrumb": {"core": "breadcrumb", "group": "Structure"},
        "accordion": {"core": "accordion", "group": "Content"},
        "tabs": {"core": "tabs", "group": "Content"},
        "carousel": {"core": "carousel", "group": "Content"},
        "slider": {"core": "carousel", "group": "Content"},
        "list": {"core": "list", "group": "Content"},
        "image": {"core": "image", "group": "Content"},
        "text": {"core": "text", "group": "Content"},
        "title": {"core": "title", "group": "Content"},
        "button": {"core": "button", "group": "Content"},
        "separator": {"core": "separator", "group": "Content"},
        "embed": {"core": "embed", "group": "Content"},
        "search": {"core": "search", "group": "Content"},
        "container": {"core": "container", "group": "Structure"},
        "section": {"core": "container", "group": "Structure"},
        "grid": {"core": "container", "group": "Structure"},
    }

    def __init__(self, config: dict):
        self.config = config
        self.aem_utils = AEMUtils(config)
        self.llm_client = LLMClient(config)
        self.confidence_threshold = config.get("figma", {}).get(
            "component_mapping", {}
        ).get("confidence_threshold", 0.75)

    def map_component(self, parsed: ParsedDesignComponent) -> AEMComponentSpec:
        """Map a parsed Figma component to an AEM component specification.

        Args:
            parsed: Parsed design component from DesignParser.

        Returns:
            AEMComponentSpec ready for code generation.
        """
        logger.info(f"Mapping Figma component '{parsed.name}' to AEM")

        # Try heuristic mapping first
        spec = self._heuristic_map(parsed)

        # Use LLM for uncertain mappings
        if not spec:
            spec = self._llm_map(parsed)

        # Enrich with design tokens
        spec.design_tokens = parsed.design_tokens

        # Map content slots to AEM properties
        spec.content_slots = parsed.content_slots

        # Map variants to Style System
        spec.style_system_styles = self._map_variants_to_styles(parsed)

        # Set responsive config
        spec.responsive_config = parsed.responsive_config

        # Set source reference
        spec.figma_id = parsed.figma_id

        logger.info(f"Mapped '{parsed.name}' -> {spec.component_type}: {spec.resource_type}")
        return spec

    def map_components_batch(self, parsed_list: list[ParsedDesignComponent]) -> list[AEMComponentSpec]:
        """Map multiple components.

        Args:
            parsed_list: List of parsed design components.

        Returns:
            List of AEM component specs.
        """
        return [self.map_component(p) for p in parsed_list]

    def _heuristic_map(self, parsed: ParsedDesignComponent) -> Optional[AEMComponentSpec]:
        """Try to map using heuristic rules."""
        name_lower = parsed.name.lower()

        # Direct name matching
        for pattern, mapping in self.DESIGN_TO_CORE.items():
            if pattern in name_lower:
                core_name = mapping["core"]
                core_type = AEMUtils.CORE_COMPONENT_TYPES.get(core_name, "")

                # Determine if it's a direct match or extension
                needs_extension = self._needs_extension(parsed, core_name)
                component_type = "core_extension" if needs_extension else "core_component"

                resource_type = (
                    self.aem_utils.get_component_resource_type(parsed.name)
                    if needs_extension
                    else core_type
                )

                return AEMComponentSpec(
                    name=parsed.name,
                    title=self._to_title(parsed.name),
                    component_type=component_type,
                    core_component_name=core_name,
                    resource_type=resource_type,
                    super_type=core_type if needs_extension else None,
                    component_group=mapping["group"],
                    properties=parsed.suggested_properties,
                    is_container=parsed.structure_type == "layout",
                )

        # No heuristic match
        return None

    def _llm_map(self, parsed: ParsedDesignComponent) -> AEMComponentSpec:
        """Use LLM to determine the best AEM mapping."""
        design_data = {
            "name": parsed.name,
            "structure_type": parsed.structure_type,
            "layout": parsed.layout,
            "content_slots": parsed.content_slots,
            "interactive_elements": parsed.interactive_elements,
            "variants_count": len(parsed.variants),
        }

        try:
            result = self.llm_client.analyze_figma_component(design_data)

            aem_mapping = result.get("aem_mapping", {})
            comp_type = aem_mapping.get("type", "custom_component")
            core_name = aem_mapping.get("core_component")
            core_type = AEMUtils.CORE_COMPONENT_TYPES.get(core_name, "") if core_name else ""

            return AEMComponentSpec(
                name=parsed.name,
                title=self._to_title(parsed.name),
                component_type=comp_type,
                core_component_name=core_name,
                resource_type=aem_mapping.get("resource_type", self.aem_utils.get_component_resource_type(parsed.name)),
                super_type=core_type if comp_type == "core_extension" else None,
                component_group="Content",
                properties=result.get("properties", parsed.suggested_properties),
                is_container=parsed.structure_type == "layout",
            )
        except Exception as e:
            logger.error(f"LLM mapping failed: {e}")
            # Fallback to custom component
            return AEMComponentSpec(
                name=parsed.name,
                title=self._to_title(parsed.name),
                component_type="custom_component",
                resource_type=self.aem_utils.get_component_resource_type(parsed.name),
                component_group="Content",
                properties=parsed.suggested_properties,
                is_container=parsed.structure_type == "layout",
            )

    def _needs_extension(self, parsed: ParsedDesignComponent, core_name: str) -> bool:
        """Determine if the design needs a Core Component extension vs direct use."""
        # If it has many custom properties beyond what the core provides
        if len(parsed.suggested_properties) > 5:
            return True

        # If it has complex layout not handled by the core
        if parsed.layout.get("children_count", 0) > 5 and core_name not in ("container", "accordion", "tabs"):
            return True

        # If it has multiple variants that suggest Style System isn't enough
        if len(parsed.variants) > 5:
            return True

        return False

    def _map_variants_to_styles(self, parsed: ParsedDesignComponent) -> list[dict]:
        """Map Figma variants to AEM Style System styles."""
        styles = []

        for variant in parsed.variants:
            props = variant.get("properties", {})

            # Create a style for each variant combination
            css_class = self._variant_to_css_class(parsed.name, props)
            label = " / ".join(f"{k}: {v}" for k, v in props.items())

            styles.append({
                "label": label,
                "css_class": css_class,
                "variant_props": props,
            })

        return styles

    def _variant_to_css_class(self, component_name: str, props: dict) -> str:
        """Convert variant properties to a BEM-style CSS class."""
        modifiers = []
        for key, value in props.items():
            modifier = f"{key.lower()}-{value.lower()}"
            modifier = modifier.replace(" ", "-")
            modifiers.append(modifier)

        base_class = f"cmp-{component_name}"
        if modifiers:
            return f"{base_class}--{'--'.join(modifiers)}"
        return base_class

    def _to_title(self, name: str) -> str:
        """Convert a component name to a human-readable title."""
        return " ".join(word.capitalize() for word in name.replace("-", " ").replace("_", " ").split())
