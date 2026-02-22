"""Page Template Builder - Creates AEM editable page templates."""

import logging
from pathlib import Path

from ..utils.aem_utils import AEMUtils

logger = logging.getLogger(__name__)


class PageTemplateBuilder:
    """Builds AEM editable page templates from discovered page structures.

    Creates:
    - Template definition (template-type node)
    - Initial content structure
    - Template policies
    - Allowed component configurations
    """

    def __init__(self, config: dict):
        self.config = config.get("template_assembly", {})
        self.aem_utils = AEMUtils(config)
        self.default_structure = self.config.get("default_structure", ["header", "responsivegrid", "footer"])

    def generate_template(
        self,
        template_name: str,
        title: str,
        components: list,
        template_regions: list = None,
        output_dir: str = "",
    ) -> dict:
        """Generate a complete AEM page template.

        Args:
            template_name: Template technical name (e.g., 'content-page').
            title: Human-readable template title.
            components: List of AEMComponentSpec that can be used in this template.
            template_regions: Template regions from page analysis.
            output_dir: Base output directory.

        Returns:
            Dict of file paths to content.
        """
        files = {}
        regions = template_regions or self.default_structure

        conf_base = (
            Path(output_dir) / "ui.content" / "src" / "main" / "content" / "jcr_root"
            / "conf" / self.aem_utils.app_id / "settings" / "wcm" / "templates"
        )
        template_dir = conf_base / template_name

        # 1. Template type definition
        files[str(template_dir / ".content.xml")] = self._generate_template_definition(
            template_name, title
        )

        # 2. Structure (locked regions)
        files[str(template_dir / "structure" / ".content.xml")] = (
            self._generate_structure(template_name, regions, components)
        )

        # 3. Initial content
        files[str(template_dir / "initial" / ".content.xml")] = (
            self._generate_initial_content(template_name, regions)
        )

        # 4. Policies mapping
        files[str(template_dir / "policies" / ".content.xml")] = (
            self._generate_policies_mapping(template_name, components)
        )

        # 5. Thumbnail (placeholder)
        files[str(template_dir / "thumbnail.png")] = ""  # Placeholder

        # Write files
        for file_path, content in files.items():
            if content:  # Skip empty placeholders
                path = Path(file_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)

        logger.info(f"Generated template '{template_name}' with {len(regions)} regions")
        return files

    def _generate_template_definition(self, template_name: str, title: str) -> str:
        """Generate the template type .content.xml."""
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<jcr:root xmlns:sling="http://sling.apache.org/jcr/sling/1.0"
          xmlns:cq="http://www.day.com/jcr/cq/1.0"
          xmlns:jcr="http://www.jcp.org/jcr/1.0"
          xmlns:nt="http://www.jcp.org/jcr/nt/1.0"
    jcr:primaryType="cq:Template"
    jcr:title="{title}"
    jcr:description="Page template for {title}"
    status="enabled"
    ranking="{{Long}}100">
    <jcr:content
        jcr:primaryType="cq:PageContent"
        sling:resourceType="{self.aem_utils.app_id}/components/page"/>
</jcr:root>
'''

    def _generate_structure(
        self, template_name: str, regions: list, components: list
    ) -> str:
        """Generate the template structure with locked and editable regions."""
        app_id = self.aem_utils.app_id

        # Build allowed component list
        allowed_types = [f"{app_id}/components/{c.name}" for c in components if hasattr(c, "name")]
        # Always include core components
        core_types = [
            "core/wcm/components/text/v2/text",
            "core/wcm/components/title/v3/title",
            "core/wcm/components/image/v3/image",
            "core/wcm/components/button/v2/button",
            "core/wcm/components/teaser/v2/teaser",
            "core/wcm/components/separator/v1/separator",
            "core/wcm/components/container/v1/container",
            "core/wcm/components/embed/v2/embed",
            "core/wcm/components/list/v3/list",
            "core/wcm/components/download/v2/download",
        ]
        all_allowed = core_types + allowed_types

        # Generate region XML nodes
        region_nodes = []
        for region in regions:
            if region in ("header", "footer"):
                # Fixed experience fragment reference
                region_nodes.append(f'''        <{region}
            jcr:primaryType="nt:unstructured"
            sling:resourceType="core/wcm/components/experiencefragment/v2/experiencefragment"/>''')
            elif region == "navigation":
                region_nodes.append(f'''        <{region}
            jcr:primaryType="nt:unstructured"
            sling:resourceType="core/wcm/components/navigation/v2/navigation"/>''')
            else:
                # Editable responsive grid
                region_nodes.append(f'''        <{region}
            jcr:primaryType="nt:unstructured"
            sling:resourceType="wcm/foundation/components/responsivegrid"/>''')

        regions_xml = "\n".join(region_nodes)

        return f'''<?xml version="1.0" encoding="UTF-8"?>
<jcr:root xmlns:sling="http://sling.apache.org/jcr/sling/1.0"
          xmlns:cq="http://www.day.com/jcr/cq/1.0"
          xmlns:jcr="http://www.jcp.org/jcr/1.0"
          xmlns:nt="http://www.jcp.org/jcr/nt/1.0"
    jcr:primaryType="cq:Page">
    <jcr:content
        jcr:primaryType="cq:PageContent"
        sling:resourceType="{app_id}/components/page">
        <root
            jcr:primaryType="nt:unstructured"
            sling:resourceType="wcm/foundation/components/responsivegrid">
{regions_xml}
        </root>
        <cq:responsive jcr:primaryType="nt:unstructured">
            <breakpoints jcr:primaryType="nt:unstructured">
                <phone
                    jcr:primaryType="nt:unstructured"
                    title="Smaller Screen"
                    width="{{Long}}650"/>
                <tablet
                    jcr:primaryType="nt:unstructured"
                    title="Tablet"
                    width="{{Long}}1024"/>
            </breakpoints>
        </cq:responsive>
    </jcr:content>
</jcr:root>
'''

    def _generate_initial_content(self, template_name: str, regions: list) -> str:
        """Generate the template initial content."""
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<jcr:root xmlns:sling="http://sling.apache.org/jcr/sling/1.0"
          xmlns:cq="http://www.day.com/jcr/cq/1.0"
          xmlns:jcr="http://www.jcp.org/jcr/1.0"
          xmlns:nt="http://www.jcp.org/jcr/nt/1.0"
    jcr:primaryType="cq:Page">
    <jcr:content
        jcr:primaryType="cq:PageContent"
        sling:resourceType="{self.aem_utils.app_id}/components/page">
        <root
            jcr:primaryType="nt:unstructured"
            sling:resourceType="wcm/foundation/components/responsivegrid"/>
    </jcr:content>
</jcr:root>
'''

    def _generate_policies_mapping(self, template_name: str, components: list) -> str:
        """Generate template policies mapping."""
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<jcr:root xmlns:sling="http://sling.apache.org/jcr/sling/1.0"
          xmlns:cq="http://www.day.com/jcr/cq/1.0"
          xmlns:jcr="http://www.jcp.org/jcr/1.0"
          xmlns:nt="http://www.jcp.org/jcr/nt/1.0"
    jcr:primaryType="cq:Page">
    <jcr:content jcr:primaryType="nt:unstructured">
        <root
            jcr:primaryType="nt:unstructured"
            sling:resourceType="wcm/foundation/components/responsivegrid">
            <cq:policy
                jcr:primaryType="nt:unstructured"
                sling:resourceType="wcm/core/components/policy/policy"
                jcr:title="Default Layout Policy"/>
        </root>
    </jcr:content>
</jcr:root>
'''
