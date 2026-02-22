"""AEM Package Builder - Creates AEM content packages (.zip) for deployment."""

import json
import logging
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from ..utils.aem_utils import AEMUtils

logger = logging.getLogger(__name__)


class AEMPackageBuilder:
    """Builds AEM content packages (.zip) for deployment via Package Manager.

    Creates CRX packages with:
    - META-INF/vault/filter.xml (package filters)
    - META-INF/vault/properties.xml (package metadata)
    - jcr_root/ (content tree)
    """

    def __init__(self, config: dict):
        self.config = config.get("content_migration", {}).get("package", {})
        self.aem_utils = AEMUtils(config)
        self.group = self.config.get("group", "modernization")
        self.version = self.config.get("version", "1.0.0")

    def build_content_package(
        self,
        content_dir: str,
        output_path: str,
        package_name: str = "content",
        filters: list = None,
    ) -> str:
        """Build an AEM content package from a directory.

        Args:
            content_dir: Directory containing jcr_root structure.
            output_path: Output path for the .zip package.
            package_name: Name of the package.
            filters: List of JCR paths to include as filters.

        Returns:
            Path to the created package.
        """
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        content_path = Path(content_dir)

        # Auto-detect filters if not provided
        if not filters:
            filters = self._detect_filters(content_path)

        with ZipFile(output, "w") as zf:
            # Add META-INF/vault files
            zf.writestr("META-INF/vault/filter.xml", self._generate_filter_xml(filters))
            zf.writestr(
                "META-INF/vault/properties.xml",
                self._generate_properties_xml(package_name),
            )
            zf.writestr("META-INF/vault/config.xml", self._generate_config_xml())

            # Add jcr_root content
            jcr_root = content_path / "jcr_root"
            if jcr_root.exists():
                for file_path in jcr_root.rglob("*"):
                    if file_path.is_file():
                        arcname = f"jcr_root/{file_path.relative_to(jcr_root)}"
                        zf.write(file_path, arcname)
            else:
                # Content dir IS the jcr_root
                for file_path in content_path.rglob("*"):
                    if file_path.is_file():
                        arcname = f"jcr_root/{file_path.relative_to(content_path)}"
                        zf.write(file_path, arcname)

        logger.info(f"Built content package: {output}")
        return str(output)

    def build_component_package(
        self,
        component_dirs: list[str],
        output_path: str,
    ) -> str:
        """Build a package containing AEM components.

        Args:
            component_dirs: List of component directories.
            output_path: Output path for the .zip package.

        Returns:
            Path to the created package.
        """
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        app_id = self.aem_utils.app_id
        filters = [f"/apps/{app_id}/components"]

        with ZipFile(output, "w") as zf:
            zf.writestr("META-INF/vault/filter.xml", self._generate_filter_xml(filters))
            zf.writestr(
                "META-INF/vault/properties.xml",
                self._generate_properties_xml("components"),
            )
            zf.writestr("META-INF/vault/config.xml", self._generate_config_xml())

            for comp_dir in component_dirs:
                comp_path = Path(comp_dir)
                if comp_path.exists():
                    for file_path in comp_path.rglob("*"):
                        if file_path.is_file():
                            # Calculate the path relative to jcr_root
                            arcname = f"jcr_root/apps/{app_id}/components/{comp_path.name}/{file_path.relative_to(comp_path)}"
                            zf.write(file_path, arcname)

        logger.info(f"Built component package: {output}")
        return str(output)

    def _generate_filter_xml(self, filters: list) -> str:
        """Generate the vault filter.xml."""
        filter_entries = "\n".join(
            f'    <filter root="{f}"/>' for f in filters
        )
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<workspaceFilter version="1.0">
{filter_entries}
</workspaceFilter>
'''

    def _generate_properties_xml(self, package_name: str) -> str:
        """Generate the vault properties.xml."""
        return f'''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!DOCTYPE properties SYSTEM "http://java.sun.com/dtd/properties.dtd">
<properties>
    <entry key="name">{self.aem_utils.app_id}-{package_name}</entry>
    <entry key="group">{self.group}</entry>
    <entry key="version">{self.version}</entry>
    <entry key="description">Generated by AEM Modernization Agent</entry>
    <entry key="requiresRoot">false</entry>
</properties>
'''

    def _generate_config_xml(self) -> str:
        """Generate the vault config.xml."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<vaultfs version="1.1">
    <aggregates/>
    <handlers/>
</vaultfs>
'''

    def _detect_filters(self, content_dir: Path) -> list:
        """Auto-detect package filters from directory structure."""
        filters = set()
        jcr_root = content_dir / "jcr_root"
        search_dir = jcr_root if jcr_root.exists() else content_dir

        for item in search_dir.iterdir():
            if item.is_dir():
                name = item.name
                if name == "apps":
                    # Add app-specific filter
                    for app_dir in item.iterdir():
                        if app_dir.is_dir():
                            filters.add(f"/apps/{app_dir.name}")
                elif name == "content":
                    for content_subdir in item.iterdir():
                        if content_subdir.is_dir():
                            if content_subdir.name == "dam":
                                for dam_dir in content_subdir.iterdir():
                                    if dam_dir.is_dir():
                                        filters.add(f"/content/dam/{dam_dir.name}")
                            else:
                                filters.add(f"/content/{content_subdir.name}")
                elif name == "conf":
                    for conf_dir in item.iterdir():
                        if conf_dir.is_dir():
                            filters.add(f"/conf/{conf_dir.name}")

        return sorted(filters) if filters else ["/content", "/apps", "/conf"]
