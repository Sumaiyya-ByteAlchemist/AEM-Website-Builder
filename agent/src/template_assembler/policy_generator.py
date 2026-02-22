"""Policy Generator - Creates AEM component policies and Style System configurations."""

import logging
from pathlib import Path

from ..figma_pipeline.aem_mapper import AEMComponentSpec
from ..utils.aem_utils import AEMUtils

logger = logging.getLogger(__name__)


class PolicyGenerator:
    """Generates AEM component policies including Style System configurations.

    Creates policies that define:
    - Allowed components in containers
    - Style System styles per component
    - Responsive grid configurations
    """

    def __init__(self, config: dict):
        self.config = config
        self.aem_utils = AEMUtils(config)

    def generate_policies(
        self,
        components: list[AEMComponentSpec],
        output_dir: str,
    ) -> dict:
        """Generate all component policies.

        Args:
            components: List of AEM component specifications.
            output_dir: Base output directory.

        Returns:
            Dict of file paths to content.
        """
        files = {}
        policies_base = (
            Path(output_dir) / "ui.content" / "src" / "main" / "content" / "jcr_root"
            / "conf" / self.aem_utils.app_id / "settings" / "wcm" / "policies"
        )

        # Generate policy for each component with Style System styles
        for comp in components:
            if comp.style_system_styles:
                policy_xml = self._generate_component_policy(comp)
                policy_path = (
                    policies_base / self.aem_utils.app_id / "components" / comp.name
                    / ".content.xml"
                )
                files[str(policy_path)] = policy_xml

        # Generate container/responsive grid policy
        container_policy = self._generate_container_policy(components)
        container_path = policies_base / "wcm" / "foundation" / "components" / "responsivegrid" / ".content.xml"
        files[str(container_path)] = container_policy

        # Write files
        for file_path, content in files.items():
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

        logger.info(f"Generated {len(files)} policy files")
        return files

    def _generate_component_policy(self, spec: AEMComponentSpec) -> str:
        """Generate a policy for a component with Style System styles."""
        styles_xml = self._generate_styles_xml(spec.style_system_styles)

        return f'''<?xml version="1.0" encoding="UTF-8"?>
<jcr:root xmlns:sling="http://sling.apache.org/jcr/sling/1.0"
          xmlns:jcr="http://www.jcp.org/jcr/1.0"
          xmlns:nt="http://www.jcp.org/jcr/nt/1.0"
    jcr:primaryType="nt:unstructured">
    <policy_default
        jcr:primaryType="nt:unstructured"
        jcr:title="{spec.title} Policy"
        sling:resourceType="wcm/core/components/policy/policy">
{styles_xml}
    </policy_default>
</jcr:root>
'''

    def _generate_styles_xml(self, styles: list) -> str:
        """Generate Style System XML nodes."""
        if not styles:
            return ""

        lines = [
            '        <cq:styleGroups jcr:primaryType="nt:unstructured">',
            '            <item0',
            '                jcr:primaryType="nt:unstructured"',
            '                jcr:title="Styles">',
            '                <cq:styles jcr:primaryType="nt:unstructured">',
        ]

        for i, style in enumerate(styles):
            label = style.get("label", f"Style {i}")
            css_class = style.get("css_class", "")
            lines.extend([
                f'                    <item{i}',
                f'                        jcr:primaryType="nt:unstructured"',
                f'                        jcr:title="{label}"',
                f'                        cq:styleClasses="{css_class}"/>',
            ])

        lines.extend([
            '                </cq:styles>',
            '            </item0>',
            '        </cq:styleGroups>',
        ])

        return "\n".join(lines)

    def _generate_container_policy(self, components: list[AEMComponentSpec]) -> str:
        """Generate a responsive grid policy with allowed components."""
        app_id = self.aem_utils.app_id

        # Build allowed components list
        allowed = []
        for comp in components:
            if comp.resource_type:
                allowed.append(comp.resource_type)

        # Add core components
        core_allowed = [
            "core/wcm/components/text/v2/text",
            "core/wcm/components/title/v3/title",
            "core/wcm/components/image/v3/image",
            "core/wcm/components/button/v2/button",
            "core/wcm/components/teaser/v2/teaser",
            "core/wcm/components/list/v3/list",
            "core/wcm/components/separator/v1/separator",
            "core/wcm/components/container/v1/container",
            "core/wcm/components/embed/v2/embed",
            "core/wcm/components/accordion/v1/accordion",
            "core/wcm/components/tabs/v1/tabs",
            "core/wcm/components/carousel/v1/carousel",
            "core/wcm/components/download/v2/download",
        ]
        all_allowed = sorted(set(core_allowed + allowed))
        allowed_str = ",".join(all_allowed)

        return f'''<?xml version="1.0" encoding="UTF-8"?>
<jcr:root xmlns:sling="http://sling.apache.org/jcr/sling/1.0"
          xmlns:jcr="http://www.jcp.org/jcr/1.0"
          xmlns:nt="http://www.jcp.org/jcr/nt/1.0"
    jcr:primaryType="nt:unstructured">
    <policy_default
        jcr:primaryType="nt:unstructured"
        jcr:title="Default Layout Container Policy"
        sling:resourceType="wcm/core/components/policy/policy"
        components="[{allowed_str}]"/>
</jcr:root>
'''
