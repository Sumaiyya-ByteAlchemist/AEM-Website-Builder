"""Dialog Generator - Generates AEM Touch UI component dialogs (_cq_dialog)."""

import logging
from pathlib import Path
from typing import Optional

from ..figma_pipeline.aem_mapper import AEMComponentSpec
from ..utils.aem_utils import AEMUtils
from ..utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


# Widget type mappings for AEM Coral UI / Granite UI
WIDGET_MAPPINGS = {
    "textfield": {
        "sling:resourceType": "granite/ui/components/coral/foundation/form/textfield",
    },
    "textarea": {
        "sling:resourceType": "granite/ui/components/coral/foundation/form/textarea",
    },
    "richtext": {
        "sling:resourceType": "cq/gui/components/authoring/dialog/richtext",
    },
    "pathbrowser": {
        "sling:resourceType": "granite/ui/components/coral/foundation/form/pathbrowser",
        "rootPath": "/content",
    },
    "checkbox": {
        "sling:resourceType": "granite/ui/components/coral/foundation/form/checkbox",
    },
    "select": {
        "sling:resourceType": "granite/ui/components/coral/foundation/form/select",
    },
    "numberfield": {
        "sling:resourceType": "granite/ui/components/coral/foundation/form/numberfield",
    },
    "colorfield": {
        "sling:resourceType": "granite/ui/components/coral/foundation/form/colorfield",
    },
    "datepicker": {
        "sling:resourceType": "granite/ui/components/coral/foundation/form/datepicker",
    },
    "imagefield": {
        "sling:resourceType": "cq/gui/components/authoring/dialog/fileupload",
        "fileReferenceParameter": "./fileReference",
    },
}


class DialogGenerator:
    """Generates Touch UI dialog XML files for AEM components.

    Creates _cq_dialog/.content.xml with Coral UI 3 / Granite UI widgets
    based on component properties.
    """

    def __init__(self, config: dict):
        self.config = config.get("component_generation", {}).get("dialog", {})
        self.aem_utils = AEMUtils(config)
        self.llm_client = LLMClient(config)
        self.use_coral_ui = self.config.get("use_coral_ui", True)

    def generate(self, spec: AEMComponentSpec, output_dir: str) -> dict:
        """Generate dialog XML files for a component.

        Args:
            spec: AEM component specification.
            output_dir: Base output directory for the AEM project.

        Returns:
            Dict with generated file paths and content.
        """
        files = {}
        component_dir = (
            Path(output_dir) / "ui.apps" / "src" / "main" / "content" / "jcr_root"
            / "apps" / self.aem_utils.app_id / "components" / spec.name
        )

        # Skip dialog for pure proxy components
        if spec.component_type == "core_component" and not spec.properties:
            logger.info(f"Skipping dialog for core component proxy '{spec.name}'")
            return files

        # Generate dialog XML
        dialog_xml = self._generate_dialog_xml(spec)
        dialog_path = component_dir / "_cq_dialog" / ".content.xml"
        files[str(dialog_path)] = dialog_xml

        # Write files
        for file_path, content in files.items():
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

        logger.info(f"Generated dialog for '{spec.name}': {len(spec.properties)} properties")
        return files

    def _generate_dialog_xml(self, spec: AEMComponentSpec) -> str:
        """Generate the _cq_dialog/.content.xml file."""
        properties = spec.properties or []

        if not properties:
            return self._generate_empty_dialog(spec)

        # Group properties into tabs if many
        use_tabs = len(properties) > 4
        if use_tabs:
            return self._generate_tabbed_dialog(spec, properties)
        else:
            return self._generate_simple_dialog(spec, properties)

    def _generate_simple_dialog(self, spec: AEMComponentSpec, properties: list) -> str:
        """Generate a simple single-panel dialog."""
        field_items = self._generate_field_items(properties, indent=24)

        return f'''<?xml version="1.0" encoding="UTF-8"?>
<jcr:root xmlns:sling="http://sling.apache.org/jcr/sling/1.0"
          xmlns:jcr="http://www.jcp.org/jcr/1.0"
          xmlns:nt="http://www.jcp.org/jcr/nt/1.0"
          xmlns:cq="http://www.day.com/jcr/cq/1.0"
          xmlns:granite="http://www.adobe.com/jcr/granite/1.0"
    jcr:primaryType="nt:unstructured"
    jcr:title="{spec.title}"
    sling:resourceType="cq/gui/components/authoring/dialog">
    <content
        jcr:primaryType="nt:unstructured"
        sling:resourceType="granite/ui/components/coral/foundation/fixedcolumns">
        <items jcr:primaryType="nt:unstructured">
            <column
                jcr:primaryType="nt:unstructured"
                sling:resourceType="granite/ui/components/coral/foundation/container">
                <items jcr:primaryType="nt:unstructured">
{field_items}
                </items>
            </column>
        </items>
    </content>
</jcr:root>
'''

    def _generate_tabbed_dialog(self, spec: AEMComponentSpec, properties: list) -> str:
        """Generate a tabbed dialog with properties split across tabs."""
        # Split properties into logical tabs
        tabs = self._organize_into_tabs(properties)
        tabs_xml = self._generate_tabs_xml(tabs, indent=20)

        return f'''<?xml version="1.0" encoding="UTF-8"?>
<jcr:root xmlns:sling="http://sling.apache.org/jcr/sling/1.0"
          xmlns:jcr="http://www.jcp.org/jcr/1.0"
          xmlns:nt="http://www.jcp.org/jcr/nt/1.0"
          xmlns:cq="http://www.day.com/jcr/cq/1.0"
          xmlns:granite="http://www.adobe.com/jcr/granite/1.0"
    jcr:primaryType="nt:unstructured"
    jcr:title="{spec.title}"
    sling:resourceType="cq/gui/components/authoring/dialog">
    <content
        jcr:primaryType="nt:unstructured"
        sling:resourceType="granite/ui/components/coral/foundation/container">
        <items jcr:primaryType="nt:unstructured">
            <tabs
                jcr:primaryType="nt:unstructured"
                sling:resourceType="granite/ui/components/coral/foundation/tabs"
                maximized="{{Boolean}}true">
                <items jcr:primaryType="nt:unstructured">
{tabs_xml}
                </items>
            </tabs>
        </items>
    </content>
</jcr:root>
'''

    def _generate_empty_dialog(self, spec: AEMComponentSpec) -> str:
        """Generate a minimal empty dialog."""
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<jcr:root xmlns:sling="http://sling.apache.org/jcr/sling/1.0"
          xmlns:jcr="http://www.jcp.org/jcr/1.0"
          xmlns:nt="http://www.jcp.org/jcr/nt/1.0"
          xmlns:cq="http://www.day.com/jcr/cq/1.0"
    jcr:primaryType="nt:unstructured"
    jcr:title="{spec.title}"
    sling:resourceType="cq/gui/components/authoring/dialog">
    <content
        jcr:primaryType="nt:unstructured"
        sling:resourceType="granite/ui/components/coral/foundation/container">
        <items jcr:primaryType="nt:unstructured"/>
    </content>
</jcr:root>
'''

    def _generate_field_items(self, properties: list, indent: int = 24) -> str:
        """Generate XML for dialog field items."""
        indent_str = " " * indent
        items = []

        for prop in properties:
            name = prop.get("name", "untitled")
            prop_type = prop.get("type", "String")
            widget = prop.get("widget", self._infer_widget(name, prop_type))
            label = prop.get("label", self._name_to_label(name))
            required = prop.get("required", False)

            widget_config = WIDGET_MAPPINGS.get(widget, WIDGET_MAPPINGS["textfield"])
            resource_type = widget_config["sling:resourceType"]

            node_name = AEMUtils.sanitize_node_name(name)

            field_xml = f'{indent_str}<{node_name}\n'
            field_xml += f'{indent_str}    jcr:primaryType="nt:unstructured"\n'
            field_xml += f'{indent_str}    sling:resourceType="{resource_type}"\n'
            field_xml += f'{indent_str}    fieldLabel="{label}"\n'
            field_xml += f'{indent_str}    name="./{name}"'

            if required:
                field_xml += f'\n{indent_str}    required="{{Boolean}}true"'

            # Add extra widget-specific properties
            for key, value in widget_config.items():
                if key != "sling:resourceType":
                    field_xml += f'\n{indent_str}    {key}="{value}"'

            # Handle select options
            if widget == "select" and prop.get("options"):
                field_xml += ">\n"
                field_xml += f'{indent_str}    <items jcr:primaryType="nt:unstructured">\n'
                for opt in prop["options"]:
                    opt_name = AEMUtils.sanitize_node_name(str(opt))
                    field_xml += f'{indent_str}        <{opt_name}\n'
                    field_xml += f'{indent_str}            jcr:primaryType="nt:unstructured"\n'
                    field_xml += f'{indent_str}            text="{opt}"\n'
                    field_xml += f'{indent_str}            value="{opt}"/>\n'
                field_xml += f'{indent_str}    </items>\n'
                field_xml += f'{indent_str}</{node_name}>'
            else:
                field_xml += "/>"

            items.append(field_xml)

        return "\n".join(items)

    def _generate_tabs_xml(self, tabs: dict, indent: int = 20) -> str:
        """Generate XML for tabbed dialog sections."""
        indent_str = " " * indent
        tab_xmls = []

        for tab_name, tab_properties in tabs.items():
            node_name = AEMUtils.sanitize_node_name(tab_name)
            fields = self._generate_field_items(tab_properties, indent=indent + 16)

            tab_xml = f'''{indent_str}<{node_name}
{indent_str}    jcr:primaryType="nt:unstructured"
{indent_str}    jcr:title="{tab_name}"
{indent_str}    sling:resourceType="granite/ui/components/coral/foundation/container">
{indent_str}    <items jcr:primaryType="nt:unstructured">
{fields}
{indent_str}    </items>
{indent_str}</{node_name}>'''

            tab_xmls.append(tab_xml)

        return "\n".join(tab_xmls)

    def _organize_into_tabs(self, properties: list) -> dict:
        """Organize properties into logical tabs."""
        tabs = {"Properties": [], "Advanced": []}

        for prop in properties:
            name = prop.get("name", "").lower()
            widget = prop.get("widget", "")

            # Heuristic: image/file properties go to a separate tab
            if widget in ("imagefield", "pathbrowser") and "image" in name:
                tabs.setdefault("Media", []).append(prop)
            elif any(kw in name for kw in ["link", "url", "href", "target"]):
                tabs.setdefault("Links", []).append(prop)
            elif any(kw in name for kw in ["css", "style", "class", "id"]):
                tabs["Advanced"].append(prop)
            else:
                tabs["Properties"].append(prop)

        # Remove empty tabs
        return {k: v for k, v in tabs.items() if v}

    def _infer_widget(self, name: str, prop_type: str) -> str:
        """Infer the appropriate widget type from property name and type."""
        name_lower = name.lower()

        if prop_type == "Boolean":
            return "checkbox"
        if prop_type == "Long":
            return "numberfield"

        if "text" in name_lower and "rich" in name_lower:
            return "richtext"
        if "description" in name_lower or "body" in name_lower:
            return "richtext"
        if any(kw in name_lower for kw in ["path", "link", "url", "href", "reference"]):
            return "pathbrowser"
        if any(kw in name_lower for kw in ["image", "file", "asset"]):
            return "imagefield"
        if any(kw in name_lower for kw in ["color", "colour"]):
            return "colorfield"
        if any(kw in name_lower for kw in ["date", "time"]):
            return "datepicker"

        return "textfield"

    def _name_to_label(self, name: str) -> str:
        """Convert a property name to a human-readable label."""
        # Remove jcr: prefix
        name = name.replace("jcr:", "")
        # Split camelCase and hyphen/underscore
        import re
        words = re.sub(r"([A-Z])", r" \1", name)
        words = words.replace("-", " ").replace("_", " ")
        return " ".join(w.capitalize() for w in words.split())
