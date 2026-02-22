"""AEM-specific utility functions."""

import os
import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AEMUtils:
    """Utility class for AEM-specific operations."""

    # Standard AEM Core Component resource types
    CORE_COMPONENT_TYPES = {
        "text": "core/wcm/components/text/v2/text",
        "title": "core/wcm/components/title/v3/title",
        "image": "core/wcm/components/image/v3/image",
        "button": "core/wcm/components/button/v2/button",
        "teaser": "core/wcm/components/teaser/v2/teaser",
        "list": "core/wcm/components/list/v3/list",
        "navigation": "core/wcm/components/navigation/v2/navigation",
        "breadcrumb": "core/wcm/components/breadcrumb/v3/breadcrumb",
        "accordion": "core/wcm/components/accordion/v1/accordion",
        "tabs": "core/wcm/components/tabs/v1/tabs",
        "carousel": "core/wcm/components/carousel/v1/carousel",
        "container": "core/wcm/components/container/v1/container",
        "experiencefragment": "core/wcm/components/experiencefragment/v2/experiencefragment",
        "separator": "core/wcm/components/separator/v1/separator",
        "embed": "core/wcm/components/embed/v2/embed",
        "contentfragment": "core/wcm/components/contentfragment/v1/contentfragment",
        "download": "core/wcm/components/download/v2/download",
        "search": "core/wcm/components/search/v1/search",
        "languagenavigation": "core/wcm/components/languagenavigation/v2/languagenavigation",
        "page": "core/wcm/components/page/v3/page",
    }

    def __init__(self, config: dict):
        self.config = config.get("aem", {})
        self.project_config = self.config.get("project", {})
        self.app_id = self.project_config.get("app_id", "modernizedsite")
        self.group_id = self.project_config.get("group_id", "com.modernized")
        self.package_name = self.project_config.get("package", self.group_id)

    def get_component_path(self, component_name: str) -> str:
        """Get the JCR path for a component.

        Args:
            component_name: The component name (e.g., 'hero', 'card').

        Returns:
            Full JCR path like /apps/mysite/components/hero.
        """
        return f"/apps/{self.app_id}/components/{component_name}"

    def get_component_resource_type(self, component_name: str) -> str:
        """Get the sling:resourceType for a project component.

        Args:
            component_name: The component name.

        Returns:
            Resource type like mysite/components/hero.
        """
        return f"{self.app_id}/components/{component_name}"

    def get_template_path(self, template_name: str) -> str:
        """Get the JCR path for a page template."""
        return f"/conf/{self.app_id}/settings/wcm/templates/{template_name}"

    def get_policy_path(self, policy_name: str) -> str:
        """Get the JCR path for a component policy."""
        return f"/conf/{self.app_id}/settings/wcm/policies/{policy_name}"

    def get_clientlib_category(self, category_suffix: str) -> str:
        """Get the clientlib category name."""
        return f"{self.app_id}.{category_suffix}"

    def get_content_path(self, page_path: str = "") -> str:
        """Get the content path."""
        return f"/content/{self.app_id}/{page_path}".rstrip("/")

    def get_dam_path(self, asset_path: str = "") -> str:
        """Get the DAM asset path."""
        return f"/content/dam/{self.app_id}/{asset_path}".rstrip("/")

    def get_java_package_path(self) -> str:
        """Get the Java source package path."""
        return self.package_name.replace(".", "/")

    def get_sling_model_class_name(self, component_name: str) -> str:
        """Convert component name to Java class name for Sling Model.

        Args:
            component_name: Component name like 'hero-banner'.

        Returns:
            Java class name like 'HeroBanner'.
        """
        return "".join(word.capitalize() for word in re.split(r"[-_]", component_name))

    def get_sling_model_fqcn(self, component_name: str) -> str:
        """Get fully qualified class name for a Sling Model."""
        class_name = self.get_sling_model_class_name(component_name)
        return f"{self.package_name}.models.{class_name}"

    @staticmethod
    def create_content_xml(
        primary_type: str = "nt:unstructured",
        resource_type: Optional[str] = None,
        properties: Optional[dict] = None,
    ) -> str:
        """Generate a .content.xml file for a JCR node.

        Args:
            primary_type: The jcr:primaryType.
            resource_type: Optional sling:resourceType.
            properties: Additional properties.

        Returns:
            XML string for .content.xml.
        """
        props = properties or {}
        attrs = [
            'xmlns:jcr="http://www.jcp.org/jcr/1.0"',
            'xmlns:nt="http://www.jcp.org/jcr/nt/1.0"',
            'xmlns:sling="http://sling.apache.org/jcr/sling/1.0"',
            'xmlns:cq="http://www.day.com/jcr/cq/1.0"',
            f'jcr:primaryType="{primary_type}"',
        ]

        if resource_type:
            attrs.append(f'sling:resourceType="{resource_type}"')

        for key, value in props.items():
            if isinstance(value, bool):
                attrs.append(f'{key}="{{Boolean}}{str(value).lower()}"')
            elif isinstance(value, int):
                attrs.append(f'{key}="{{Long}}{value}"')
            elif isinstance(value, list):
                val_str = ",".join(str(v) for v in value)
                attrs.append(f'{key}="[{val_str}]"')
            else:
                # Escape XML special characters
                escaped = (
                    str(value)
                    .replace("&", "&amp;")
                    .replace('"', "&quot;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                attrs.append(f'{key}="{escaped}"')

        attr_str = "\n    ".join(attrs)
        return f'<?xml version="1.0" encoding="UTF-8"?>\n<jcr:root\n    {attr_str}/>\n'

    @staticmethod
    def sanitize_component_name(name: str) -> str:
        """Sanitize a string to be a valid AEM component name.

        Args:
            name: Raw name string.

        Returns:
            Sanitized component name (lowercase, hyphens, no special chars).
        """
        # Remove special characters, replace spaces/underscores with hyphens
        name = re.sub(r"[^a-zA-Z0-9\s_-]", "", name)
        name = re.sub(r"[\s_]+", "-", name)
        name = re.sub(r"-+", "-", name)
        return name.lower().strip("-")

    @staticmethod
    def sanitize_node_name(name: str) -> str:
        """Sanitize a string to be a valid JCR node name."""
        name = re.sub(r"[^a-zA-Z0-9_-]", "", name)
        return name.lower()

    def find_aem_project_structure(self, project_dir: str) -> dict:
        """Scan a directory for AEM project structure and identify key paths.

        Args:
            project_dir: Root directory of the AEM project.

        Returns:
            Dict with discovered paths for components, templates, etc.
        """
        project_dir = Path(project_dir)
        structure = {
            "root": str(project_dir),
            "ui_apps": None,
            "ui_content": None,
            "ui_frontend": None,
            "core": None,
            "components_dir": None,
            "templates_dir": None,
            "clientlibs_dir": None,
        }

        # Look for standard AEM module directories
        for subdir in project_dir.rglob("*"):
            if not subdir.is_dir():
                continue
            name = subdir.name
            if name == "ui.apps":
                structure["ui_apps"] = str(subdir)
            elif name == "ui.content":
                structure["ui_content"] = str(subdir)
            elif name == "ui.frontend":
                structure["ui_frontend"] = str(subdir)
            elif name == "core" and (subdir / "pom.xml").exists():
                structure["core"] = str(subdir)

        # Find component directory within ui.apps
        if structure["ui_apps"]:
            ui_apps = Path(structure["ui_apps"])
            for comp_dir in ui_apps.rglob("components"):
                if "jcr_root" in str(comp_dir) and "apps" in str(comp_dir):
                    structure["components_dir"] = str(comp_dir)
                    break

        # Find clientlibs directory
        if structure["ui_apps"]:
            ui_apps = Path(structure["ui_apps"])
            for cl_dir in ui_apps.rglob("clientlibs"):
                if "jcr_root" in str(cl_dir) and "apps" in str(cl_dir):
                    structure["clientlibs_dir"] = str(cl_dir)
                    break

        # Find templates directory in ui.content
        if structure["ui_content"]:
            ui_content = Path(structure["ui_content"])
            for tmpl_dir in ui_content.rglob("templates"):
                if "jcr_root" in str(tmpl_dir) and "conf" in str(tmpl_dir):
                    structure["templates_dir"] = str(tmpl_dir)
                    break

        return structure

    def generate_archetype_command(self) -> str:
        """Generate the Maven archetype command to scaffold the AEM project."""
        return (
            f"mvn -B org.apache.maven.plugins:maven-archetype-plugin:3.2.1:generate \\\n"
            f"  -D archetypeGroupId=com.adobe.aem \\\n"
            f"  -D archetypeArtifactId=aem-project-archetype \\\n"
            f"  -D archetypeVersion=36 \\\n"
            f"  -D appTitle=\"{self.project_config.get('app_title', 'Modernized Site')}\" \\\n"
            f"  -D appId=\"{self.app_id}\" \\\n"
            f"  -D groupId=\"{self.group_id}\" \\\n"
            f"  -D artifactId=\"{self.project_config.get('artifact_id', self.app_id)}\" \\\n"
            f"  -D package=\"{self.package_name}\" \\\n"
            f"  -D aemVersion=\"{self.config.get('version', '6.5.7')}\" \\\n"
            f"  -D frontendModule=\"general\" \\\n"
            f"  -D includeExamples=\"n\" \\\n"
            f"  -D includeErrorHandler=\"y\" \\\n"
            f"  -D includeDispatcherConfig=\"y\""
        )
