"""Figma MCP Client - Interfaces with Figma's Model Context Protocol server.

Enables AI agents to semantically understand design elements and retrieve
structured component data from Figma files.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class FigmaComponent:
    """Represents a Figma component with its design data."""

    id: str
    name: str
    component_type: str  # COMPONENT, COMPONENT_SET, FRAME, etc.
    description: str = ""
    # Design properties
    width: float = 0
    height: float = 0
    # Layout properties
    layout_mode: str = ""  # HORIZONTAL, VERTICAL, NONE
    padding: dict = field(default_factory=dict)
    spacing: float = 0
    # Style properties
    fills: list = field(default_factory=list)
    strokes: list = field(default_factory=list)
    effects: list = field(default_factory=list)
    # Typography (if text node)
    typography: dict = field(default_factory=dict)
    # Children components
    children: list = field(default_factory=list)
    # Variants (if component set)
    variants: list = field(default_factory=list)
    # Raw Figma data
    raw_data: dict = field(default_factory=dict)


@dataclass
class FigmaDesignTokens:
    """Design tokens extracted from a Figma file."""

    colors: dict = field(default_factory=dict)
    typography: dict = field(default_factory=dict)
    spacing: dict = field(default_factory=dict)
    border_radius: dict = field(default_factory=dict)
    shadows: dict = field(default_factory=dict)
    breakpoints: dict = field(default_factory=dict)


class FigmaMCPClient:
    """Client for Figma's Model Context Protocol (MCP) server.

    The MCP server provides semantic access to Figma design data, enabling
    AI agents to understand and convert design components to code.
    """

    def __init__(self, config: dict):
        figma_config = config.get("figma", {}).get("mcp_server", {})
        self.server_url = figma_config.get("url", "http://localhost:3845")
        self.timeout = figma_config.get("timeout_seconds", 30)
        self.client = httpx.Client(timeout=self.timeout)

        # Figma REST API fallback
        self.figma_api_base = "https://api.figma.com/v1"
        self.figma_token = None

    def set_figma_token(self, token: str) -> None:
        """Set the Figma access token for direct API calls."""
        self.figma_token = token

    def get_file_components(self, file_key: str) -> list[FigmaComponent]:
        """Retrieve all components from a Figma file via MCP.

        Args:
            file_key: The Figma file key (from the URL).

        Returns:
            List of FigmaComponent objects.
        """
        logger.info(f"Fetching components from Figma file: {file_key}")

        try:
            # Try MCP server first
            response = self._mcp_request("get_file_components", {
                "file_key": file_key,
            })
            return self._parse_components(response)
        except Exception as e:
            logger.warning(f"MCP request failed, falling back to REST API: {e}")
            return self._fetch_components_rest(file_key)

    def get_component_details(self, file_key: str, node_id: str) -> FigmaComponent:
        """Get detailed data for a specific component.

        Args:
            file_key: The Figma file key.
            node_id: The node ID of the component.

        Returns:
            FigmaComponent with full details.
        """
        try:
            response = self._mcp_request("get_node_details", {
                "file_key": file_key,
                "node_id": node_id,
            })
            components = self._parse_components(response)
            return components[0] if components else FigmaComponent(id=node_id, name="unknown", component_type="UNKNOWN")
        except Exception as e:
            logger.warning(f"MCP request failed for node details: {e}")
            return self._fetch_node_rest(file_key, node_id)

    def get_component_styles(self, file_key: str) -> FigmaDesignTokens:
        """Extract design tokens from a Figma file.

        Args:
            file_key: The Figma file key.

        Returns:
            FigmaDesignTokens with colors, typography, spacing, etc.
        """
        try:
            response = self._mcp_request("get_file_styles", {
                "file_key": file_key,
            })
            return self._parse_design_tokens(response)
        except Exception as e:
            logger.warning(f"MCP request failed for styles: {e}")
            return self._fetch_styles_rest(file_key)

    def get_component_images(self, file_key: str, node_ids: list[str], format: str = "png", scale: int = 2) -> dict:
        """Export component images from Figma.

        Args:
            file_key: The Figma file key.
            node_ids: List of node IDs to export.
            format: Image format (png, jpg, svg, pdf).
            scale: Export scale factor.

        Returns:
            Dict mapping node IDs to image URLs.
        """
        try:
            response = self._mcp_request("export_images", {
                "file_key": file_key,
                "node_ids": node_ids,
                "format": format,
                "scale": scale,
            })
            return response.get("images", {})
        except Exception as e:
            logger.warning(f"MCP image export failed: {e}")
            return self._export_images_rest(file_key, node_ids, format, scale)

    # --- MCP Protocol Methods ---

    def _mcp_request(self, method: str, params: dict) -> dict:
        """Send a request to the Figma MCP server.

        Args:
            method: The MCP method name.
            params: Method parameters.

        Returns:
            Response data dict.
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }

        response = self.client.post(
            f"{self.server_url}/mcp",
            json=payload,
        )
        response.raise_for_status()
        result = response.json()

        if "error" in result:
            raise RuntimeError(f"MCP error: {result['error']}")

        return result.get("result", {})

    # --- Figma REST API Fallback ---

    def _get_figma_headers(self) -> dict:
        """Get headers for Figma REST API requests."""
        if not self.figma_token:
            raise ValueError("Figma access token not set. Call set_figma_token() first.")
        return {"X-Figma-Token": self.figma_token}

    def _fetch_components_rest(self, file_key: str) -> list[FigmaComponent]:
        """Fetch components via Figma REST API."""
        response = self.client.get(
            f"{self.figma_api_base}/files/{file_key}/components",
            headers=self._get_figma_headers(),
        )
        response.raise_for_status()
        data = response.json()

        components = []
        for meta in data.get("meta", {}).get("components", []):
            comp = FigmaComponent(
                id=meta.get("node_id", ""),
                name=meta.get("name", ""),
                component_type="COMPONENT",
                description=meta.get("description", ""),
                raw_data=meta,
            )
            components.append(comp)

        return components

    def _fetch_node_rest(self, file_key: str, node_id: str) -> FigmaComponent:
        """Fetch a single node via Figma REST API."""
        response = self.client.get(
            f"{self.figma_api_base}/files/{file_key}/nodes",
            params={"ids": node_id},
            headers=self._get_figma_headers(),
        )
        response.raise_for_status()
        data = response.json()

        nodes = data.get("nodes", {})
        node_data = nodes.get(node_id, {}).get("document", {})
        return self._node_to_component(node_data)

    def _fetch_styles_rest(self, file_key: str) -> FigmaDesignTokens:
        """Fetch styles via Figma REST API."""
        response = self.client.get(
            f"{self.figma_api_base}/files/{file_key}/styles",
            headers=self._get_figma_headers(),
        )
        response.raise_for_status()
        data = response.json()
        return self._parse_design_tokens(data)

    def _export_images_rest(
        self, file_key: str, node_ids: list[str], format: str, scale: int
    ) -> dict:
        """Export images via Figma REST API."""
        response = self.client.get(
            f"{self.figma_api_base}/images/{file_key}",
            params={
                "ids": ",".join(node_ids),
                "format": format,
                "scale": scale,
            },
            headers=self._get_figma_headers(),
        )
        response.raise_for_status()
        data = response.json()
        return data.get("images", {})

    # --- Data Parsing ---

    def _parse_components(self, data: dict) -> list[FigmaComponent]:
        """Parse MCP response into FigmaComponent list."""
        components = []
        raw_components = data.get("components", data.get("nodes", []))

        if isinstance(raw_components, dict):
            raw_components = list(raw_components.values())

        for raw in raw_components:
            comp = self._node_to_component(raw)
            components.append(comp)

        return components

    def _node_to_component(self, node: dict) -> FigmaComponent:
        """Convert a Figma node dict to FigmaComponent."""
        abs_bbox = node.get("absoluteBoundingBox", {})

        # Extract layout properties
        layout_mode = node.get("layoutMode", "NONE")
        padding = {
            "top": node.get("paddingTop", 0),
            "right": node.get("paddingRight", 0),
            "bottom": node.get("paddingBottom", 0),
            "left": node.get("paddingLeft", 0),
        }

        # Extract typography for text nodes
        typography = {}
        if node.get("type") == "TEXT":
            style = node.get("style", {})
            typography = {
                "font_family": style.get("fontFamily", ""),
                "font_size": style.get("fontSize", 0),
                "font_weight": style.get("fontWeight", 400),
                "line_height": style.get("lineHeightPx", 0),
                "letter_spacing": style.get("letterSpacing", 0),
                "text_align": style.get("textAlignHorizontal", "LEFT"),
            }

        # Parse children
        children = []
        for child in node.get("children", []):
            children.append(self._node_to_component(child))

        return FigmaComponent(
            id=node.get("id", ""),
            name=node.get("name", ""),
            component_type=node.get("type", "UNKNOWN"),
            description=node.get("description", ""),
            width=abs_bbox.get("width", 0),
            height=abs_bbox.get("height", 0),
            layout_mode=layout_mode,
            padding=padding,
            spacing=node.get("itemSpacing", 0),
            fills=node.get("fills", []),
            strokes=node.get("strokes", []),
            effects=node.get("effects", []),
            typography=typography,
            children=children,
            raw_data=node,
        )

    def _parse_design_tokens(self, data: dict) -> FigmaDesignTokens:
        """Parse design tokens from Figma data."""
        tokens = FigmaDesignTokens()

        styles = data.get("meta", {}).get("styles", data.get("styles", []))
        if isinstance(styles, dict):
            styles = list(styles.values())

        for style in styles:
            style_type = style.get("style_type", style.get("styleType", ""))
            name = style.get("name", "")
            description = style.get("description", "")

            if style_type == "FILL":
                tokens.colors[name] = {
                    "description": description,
                    "node_id": style.get("node_id", ""),
                }
            elif style_type == "TEXT":
                tokens.typography[name] = {
                    "description": description,
                    "node_id": style.get("node_id", ""),
                }
            elif style_type == "EFFECT":
                tokens.shadows[name] = {
                    "description": description,
                    "node_id": style.get("node_id", ""),
                }
            elif style_type == "GRID":
                tokens.spacing[name] = {
                    "description": description,
                    "node_id": style.get("node_id", ""),
                }

        return tokens
