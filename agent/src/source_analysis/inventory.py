"""Component Inventory - Builds and manages the discovered component inventory."""

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .component_classifier import ComponentClassification
from .dom_decomposer import PageStructure

logger = logging.getLogger(__name__)


@dataclass
class InventoryItem:
    """A single item in the component inventory."""

    name: str
    component_type: str  # core_component, core_extension, custom_component
    core_component_name: Optional[str] = None
    resource_type: str = ""
    confidence: float = 0.0
    # How many times this component appears across pages
    occurrence_count: int = 0
    # Pages where this component was found
    page_urls: list = field(default_factory=list)
    # Representative HTML samples
    html_samples: list = field(default_factory=list)
    # Properties
    properties: list = field(default_factory=list)
    # Design notes
    rationale: str = ""
    # Priority for implementation (higher = more important)
    priority: int = 0


@dataclass
class ComponentInventory:
    """Complete inventory of components discovered during site analysis."""

    items: list[InventoryItem] = field(default_factory=list)
    template_regions: list[str] = field(default_factory=list)
    page_count: int = 0
    total_sections_analyzed: int = 0

    def add_classification(
        self,
        classification: ComponentClassification,
        page_url: str,
        html_sample: str = "",
    ) -> None:
        """Add a classification result to the inventory.

        Merges with existing items if the same component type is found.

        Args:
            classification: The classification result.
            page_url: URL of the page where this was found.
            html_sample: HTML snippet for reference.
        """
        # Determine the inventory item name
        name = (
            classification.core_component_name
            or classification.suggested_name
            or "unknown"
        )

        # Check if this component already exists in inventory
        existing = self._find_existing(name, classification.component_type)

        if existing:
            existing.occurrence_count += 1
            if page_url not in existing.page_urls:
                existing.page_urls.append(page_url)
            if html_sample and len(existing.html_samples) < 3:
                existing.html_samples.append(html_sample[:500])
            # Update confidence if new classification is higher
            if classification.confidence > existing.confidence:
                existing.confidence = classification.confidence
                existing.rationale = classification.rationale
        else:
            item = InventoryItem(
                name=name,
                component_type=classification.component_type,
                core_component_name=classification.core_component_name,
                resource_type=classification.resource_type,
                confidence=classification.confidence,
                occurrence_count=1,
                page_urls=[page_url],
                html_samples=[html_sample[:500]] if html_sample else [],
                properties=classification.properties or [],
                rationale=classification.rationale,
            )
            self.items.append(item)

        self.total_sections_analyzed += 1

    def add_template_regions(self, regions: list[str]) -> None:
        """Add template regions discovered from page analysis."""
        for region in regions:
            if region not in self.template_regions:
                self.template_regions.append(region)

    def calculate_priorities(self) -> None:
        """Calculate implementation priorities based on occurrence and type."""
        for item in self.items:
            priority = 0

            # Higher priority for more frequently occurring components
            priority += min(item.occurrence_count * 10, 50)

            # Higher priority for core components (easier to implement)
            if item.component_type == "core_component":
                priority += 30
            elif item.component_type == "core_extension":
                priority += 20
            elif item.component_type == "container":
                priority += 25

            # Higher confidence = higher priority
            priority += int(item.confidence * 20)

            item.priority = priority

        # Sort by priority descending
        self.items.sort(key=lambda x: x.priority, reverse=True)

    def _find_existing(self, name: str, component_type: str) -> Optional[InventoryItem]:
        """Find an existing inventory item by name and type."""
        for item in self.items:
            if item.name == name and item.component_type == component_type:
                return item
        return None

    def get_summary(self) -> dict:
        """Generate a summary of the inventory."""
        type_counts = Counter(item.component_type for item in self.items)

        return {
            "total_components": len(self.items),
            "by_type": dict(type_counts),
            "template_regions": self.template_regions,
            "pages_analyzed": self.page_count,
            "total_sections": self.total_sections_analyzed,
            "top_components": [
                {
                    "name": item.name,
                    "type": item.component_type,
                    "occurrences": item.occurrence_count,
                    "confidence": item.confidence,
                    "priority": item.priority,
                }
                for item in self.items[:10]
            ],
        }

    def get_core_components(self) -> list[InventoryItem]:
        """Get all items classified as core components."""
        return [i for i in self.items if i.component_type == "core_component"]

    def get_extensions(self) -> list[InventoryItem]:
        """Get all items classified as core component extensions."""
        return [i for i in self.items if i.component_type == "core_extension"]

    def get_custom_components(self) -> list[InventoryItem]:
        """Get all items classified as custom components."""
        return [i for i in self.items if i.component_type == "custom_component"]

    def get_containers(self) -> list[InventoryItem]:
        """Get all items classified as containers."""
        return [i for i in self.items if i.component_type == "container"]

    def export_to_json(self, output_path: str) -> None:
        """Export the inventory to a JSON file.

        Args:
            output_path: Path to write the JSON file.
        """
        data = {
            "summary": self.get_summary(),
            "template_regions": self.template_regions,
            "components": [
                {
                    "name": item.name,
                    "component_type": item.component_type,
                    "core_component_name": item.core_component_name,
                    "resource_type": item.resource_type,
                    "confidence": item.confidence,
                    "occurrence_count": item.occurrence_count,
                    "page_urls": item.page_urls,
                    "properties": item.properties,
                    "rationale": item.rationale,
                    "priority": item.priority,
                    "html_samples": item.html_samples,
                }
                for item in self.items
            ],
        }

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Inventory exported to {output_path}")

    def export_report(self, output_path: str) -> None:
        """Export a human-readable report of the inventory.

        Args:
            output_path: Path to write the report.
        """
        self.calculate_priorities()
        summary = self.get_summary()

        lines = [
            "=" * 70,
            "AEM COMPONENT INVENTORY REPORT",
            "=" * 70,
            "",
            f"Pages Analyzed: {summary['pages_analyzed']}",
            f"Total Sections Analyzed: {summary['total_sections']}",
            f"Total Components Identified: {summary['total_components']}",
            "",
            "Component Types:",
        ]

        for comp_type, count in summary["by_type"].items():
            lines.append(f"  - {comp_type}: {count}")

        lines.extend([
            "",
            f"Template Regions: {', '.join(summary['template_regions'])}",
            "",
            "-" * 70,
            "COMPONENT DETAILS (sorted by priority)",
            "-" * 70,
        ])

        for item in self.items:
            lines.extend([
                "",
                f"  [{item.priority}] {item.name}",
                f"      Type: {item.component_type}",
                f"      Core Component: {item.core_component_name or 'N/A'}",
                f"      Resource Type: {item.resource_type or 'TBD'}",
                f"      Confidence: {item.confidence:.2f}",
                f"      Occurrences: {item.occurrence_count}",
                f"      Rationale: {item.rationale}",
            ])

            if item.properties:
                lines.append("      Properties:")
                for prop in item.properties:
                    lines.append(f"        - {prop.get('name', '?')}: {prop.get('type', 'String')}")

        lines.append("")
        lines.append("=" * 70)

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            f.write("\n".join(lines))

        logger.info(f"Inventory report exported to {output_path}")
