"""Design Parser - Extracts design tokens and component structure from Figma data."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from .figma_mcp_client import FigmaComponent, FigmaDesignTokens

logger = logging.getLogger(__name__)


@dataclass
class ParsedDesignComponent:
    """A Figma component parsed into an intermediate representation for AEM mapping."""

    name: str
    figma_id: str
    # Structural classification
    structure_type: str = ""  # layout, content, interactive, decorative
    # Layout info
    layout: dict = field(default_factory=dict)
    # Content slots identified
    content_slots: list = field(default_factory=list)
    # Interactive elements
    interactive_elements: list = field(default_factory=list)
    # Design tokens used
    design_tokens: dict = field(default_factory=dict)
    # Variants
    variants: list = field(default_factory=list)
    # Responsive breakpoints
    responsive_config: dict = field(default_factory=dict)
    # Suggested AEM properties
    suggested_properties: list = field(default_factory=list)


class DesignParser:
    """Parses Figma components into an intermediate representation for AEM mapping.

    Analyzes layout structure, identifies content slots, extracts design tokens,
    and suggests responsive behavior.
    """

    def __init__(self, config: dict):
        self.config = config.get("figma", {}).get("design_tokens", {})
        self.extract_colors = self.config.get("extract_colors", True)
        self.extract_typography = self.config.get("extract_typography", True)
        self.extract_spacing = self.config.get("extract_spacing", True)

    def parse_component(self, component: FigmaComponent) -> ParsedDesignComponent:
        """Parse a Figma component into an AEM-ready representation.

        Args:
            component: FigmaComponent from the MCP client.

        Returns:
            ParsedDesignComponent with extracted information.
        """
        parsed = ParsedDesignComponent(
            name=self._sanitize_name(component.name),
            figma_id=component.id,
        )

        # Classify structure type
        parsed.structure_type = self._classify_structure(component)

        # Extract layout information
        parsed.layout = self._extract_layout(component)

        # Identify content slots
        parsed.content_slots = self._identify_content_slots(component)

        # Find interactive elements
        parsed.interactive_elements = self._find_interactive_elements(component)

        # Extract design tokens
        parsed.design_tokens = self._extract_component_tokens(component)

        # Identify variants
        parsed.variants = self._identify_variants(component)

        # Suggest AEM properties
        parsed.suggested_properties = self._suggest_properties(parsed)

        logger.info(f"Parsed Figma component '{component.name}': {parsed.structure_type}, "
                     f"{len(parsed.content_slots)} slots, {len(parsed.variants)} variants")
        return parsed

    def parse_design_tokens(self, tokens: FigmaDesignTokens) -> dict:
        """Convert Figma design tokens to CSS custom properties.

        Args:
            tokens: Design tokens from Figma.

        Returns:
            Dict with CSS custom properties organized by category.
        """
        css_tokens = {
            "colors": {},
            "typography": {},
            "spacing": {},
            "shadows": {},
        }

        # Process colors
        if self.extract_colors:
            for name, color_data in tokens.colors.items():
                css_var = self._to_css_variable(name, "color")
                css_tokens["colors"][css_var] = color_data

        # Process typography
        if self.extract_typography:
            for name, typo_data in tokens.typography.items():
                css_var = self._to_css_variable(name, "font")
                css_tokens["typography"][css_var] = typo_data

        # Process spacing
        if self.extract_spacing:
            for name, space_data in tokens.spacing.items():
                css_var = self._to_css_variable(name, "space")
                css_tokens["spacing"][css_var] = space_data

        # Process shadows
        for name, shadow_data in tokens.shadows.items():
            css_var = self._to_css_variable(name, "shadow")
            css_tokens["shadows"][css_var] = shadow_data

        return css_tokens

    def generate_css_variables(self, tokens: dict) -> str:
        """Generate a CSS :root block with design token variables.

        Args:
            tokens: Parsed design tokens dict.

        Returns:
            CSS string with :root custom properties.
        """
        lines = [":root {"]

        for category, variables in tokens.items():
            if variables:
                lines.append(f"  /* {category.title()} */")
                for var_name, _value in variables.items():
                    # Placeholder values - actual values come from Figma node resolution
                    lines.append(f"  {var_name}: /* resolve from Figma */;")
                lines.append("")

        lines.append("}")
        return "\n".join(lines)

    def _classify_structure(self, component: FigmaComponent) -> str:
        """Classify the component's structural purpose."""
        name_lower = component.name.lower()

        # Layout components
        layout_keywords = ["container", "grid", "row", "column", "layout", "wrapper", "section"]
        if any(kw in name_lower for kw in layout_keywords):
            return "layout"

        # Interactive components
        interactive_keywords = ["button", "input", "form", "dropdown", "toggle", "checkbox", "radio", "tab"]
        if any(kw in name_lower for kw in interactive_keywords):
            return "interactive"

        # Decorative components
        decorative_keywords = ["icon", "divider", "separator", "decoration", "ornament"]
        if any(kw in name_lower for kw in decorative_keywords):
            return "decorative"

        # Default to content
        return "content"

    def _extract_layout(self, component: FigmaComponent) -> dict:
        """Extract layout information from a component."""
        layout = {
            "width": component.width,
            "height": component.height,
            "direction": "horizontal" if component.layout_mode == "HORIZONTAL" else "vertical",
            "padding": component.padding,
            "gap": component.spacing,
            "children_count": len(component.children),
        }

        # Determine if this uses auto-layout (flexbox equivalent)
        layout["auto_layout"] = component.layout_mode in ("HORIZONTAL", "VERTICAL")

        # Determine column structure if applicable
        if component.layout_mode == "HORIZONTAL" and len(component.children) > 1:
            layout["suggested_columns"] = len(component.children)

        return layout

    def _identify_content_slots(self, component: FigmaComponent) -> list[dict]:
        """Identify content slots (authorable areas) in the component."""
        slots = []

        for child in component.children:
            slot = self._classify_child_as_slot(child)
            if slot:
                slots.append(slot)

            # Recurse into children
            for grandchild in child.children:
                slot = self._classify_child_as_slot(grandchild)
                if slot:
                    slots.append(slot)

        return slots

    def _classify_child_as_slot(self, child: FigmaComponent) -> Optional[dict]:
        """Classify a child node as a content slot."""
        name_lower = child.name.lower()

        if child.component_type == "TEXT":
            # Determine text type based on typography
            font_size = child.typography.get("font_size", 16)
            if font_size >= 24:
                slot_type = "title"
            elif font_size >= 18:
                slot_type = "subtitle"
            else:
                slot_type = "text"

            return {
                "name": self._sanitize_name(child.name),
                "type": slot_type,
                "figma_type": "TEXT",
                "typography": child.typography,
            }

        elif child.component_type in ("RECTANGLE", "FRAME") and any(
            kw in name_lower for kw in ["image", "photo", "media", "thumbnail", "picture"]
        ):
            return {
                "name": self._sanitize_name(child.name),
                "type": "image",
                "figma_type": child.component_type,
                "dimensions": {"width": child.width, "height": child.height},
            }

        elif any(kw in name_lower for kw in ["button", "cta", "action"]):
            return {
                "name": self._sanitize_name(child.name),
                "type": "button",
                "figma_type": child.component_type,
            }

        return None

    def _find_interactive_elements(self, component: FigmaComponent) -> list[dict]:
        """Find interactive elements in the component tree."""
        interactive = []

        def walk(node: FigmaComponent):
            name_lower = node.name.lower()
            if any(kw in name_lower for kw in ["button", "link", "input", "toggle", "dropdown"]):
                interactive.append({
                    "name": node.name,
                    "type": "button" if "button" in name_lower else "interactive",
                    "figma_id": node.id,
                })
            for child in node.children:
                walk(child)

        walk(component)
        return interactive

    def _extract_component_tokens(self, component: FigmaComponent) -> dict:
        """Extract design tokens used by this specific component."""
        tokens = {
            "fills": [],
            "typography": {},
            "spacing": {
                "padding": component.padding,
                "gap": component.spacing,
            },
            "border_radius": {},
            "effects": [],
        }

        # Extract fills (colors)
        for fill in component.fills:
            if fill.get("type") == "SOLID" and fill.get("visible", True):
                color = fill.get("color", {})
                tokens["fills"].append({
                    "r": color.get("r", 0),
                    "g": color.get("g", 0),
                    "b": color.get("b", 0),
                    "a": color.get("a", 1),
                })

        # Extract effects (shadows, blurs)
        for effect in component.effects:
            tokens["effects"].append({
                "type": effect.get("type", ""),
                "visible": effect.get("visible", True),
            })

        # Extract typography from text children
        if component.typography:
            tokens["typography"] = component.typography

        return tokens

    def _identify_variants(self, component: FigmaComponent) -> list[dict]:
        """Identify design variants of the component."""
        variants = []

        if component.component_type == "COMPONENT_SET":
            for child in component.children:
                variant_props = self._parse_variant_name(child.name)
                variants.append({
                    "name": child.name,
                    "figma_id": child.id,
                    "properties": variant_props,
                })

        return variants

    def _parse_variant_name(self, name: str) -> dict:
        """Parse a Figma variant name like 'Size=Large, State=Hover' into props."""
        props = {}
        parts = name.split(",")
        for part in parts:
            if "=" in part:
                key, value = part.split("=", 1)
                props[key.strip()] = value.strip()
        return props

    def _suggest_properties(self, parsed: ParsedDesignComponent) -> list[dict]:
        """Suggest AEM component properties based on parsed design data."""
        properties = []

        for slot in parsed.content_slots:
            if slot["type"] == "title":
                properties.append({
                    "name": "jcr:title",
                    "type": "String",
                    "widget": "textfield",
                    "label": "Title",
                })
            elif slot["type"] == "text":
                properties.append({
                    "name": "text",
                    "type": "String",
                    "widget": "richtext",
                    "label": "Text",
                })
            elif slot["type"] == "image":
                properties.append({
                    "name": "fileReference",
                    "type": "String",
                    "widget": "pathbrowser",
                    "label": "Image",
                })
            elif slot["type"] == "button":
                properties.extend([
                    {
                        "name": "ctaText",
                        "type": "String",
                        "widget": "textfield",
                        "label": "Button Text",
                    },
                    {
                        "name": "ctaLink",
                        "type": "String",
                        "widget": "pathbrowser",
                        "label": "Button Link",
                    },
                ])

        # Add variant-based properties
        for variant in parsed.variants:
            for prop_name, prop_value in variant.get("properties", {}).items():
                if not any(p["name"] == prop_name.lower() for p in properties):
                    properties.append({
                        "name": prop_name.lower(),
                        "type": "String",
                        "widget": "select",
                        "label": prop_name,
                        "options": [],  # Will be populated from all variants
                    })

        return properties

    def _sanitize_name(self, name: str) -> str:
        """Sanitize Figma component name for use in AEM."""
        name = re.sub(r"[^a-zA-Z0-9\s_-]", "", name)
        name = re.sub(r"[\s_]+", "-", name)
        return name.lower().strip("-")

    def _to_css_variable(self, name: str, prefix: str) -> str:
        """Convert a token name to a CSS custom property name."""
        sanitized = re.sub(r"[^a-zA-Z0-9]", "-", name.lower())
        sanitized = re.sub(r"-+", "-", sanitized).strip("-")
        return f"--{prefix}-{sanitized}"
