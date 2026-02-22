"""Content Structure Builder - Creates AEM content tree and page structure."""

import logging
from pathlib import Path

from ..utils.aem_utils import AEMUtils

logger = logging.getLogger(__name__)


class ContentStructureBuilder:
    """Builds the AEM content structure (site root, language root, pages).

    Creates the JCR content tree in ui.content module:
    /content/<appId>
      /en (or language root)
        /page1
        /page2
        ...
    """

    def __init__(self, config: dict):
        self.config = config
        self.aem_utils = AEMUtils(config)

    def generate_site_structure(
        self,
        pages: list[dict],
        output_dir: str,
        language: str = "en",
        country: str = "us",
    ) -> dict:
        """Generate the complete site content structure.

        Args:
            pages: List of page dicts with 'name', 'title', 'template', 'children'.
            output_dir: Base output directory.
            language: Language code.
            country: Country code.

        Returns:
            Dict of file paths to content.
        """
        files = {}
        app_id = self.aem_utils.app_id
        content_base = (
            Path(output_dir) / "ui.content" / "src" / "main" / "content" / "jcr_root"
            / "content" / app_id
        )

        # Site root
        files[str(content_base / ".content.xml")] = self._generate_site_root()

        # Language root
        lang_dir = content_base / language
        files[str(lang_dir / ".content.xml")] = self._generate_language_root(language, country)

        # Generate pages
        for page in pages:
            page_files = self._generate_page(page, lang_dir)
            files.update(page_files)

        # DAM structure
        dam_base = (
            Path(output_dir) / "ui.content" / "src" / "main" / "content" / "jcr_root"
            / "content" / "dam" / app_id
        )
        files[str(dam_base / ".content.xml")] = self._generate_dam_root()

        # Write files
        for file_path, content in files.items():
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

        logger.info(f"Generated content structure: {len(pages)} pages")
        return files

    def _generate_site_root(self) -> str:
        """Generate the site root .content.xml."""
        app_title = self.aem_utils.project_config.get("app_title", "Modernized Site")
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<jcr:root xmlns:sling="http://sling.apache.org/jcr/sling/1.0"
          xmlns:cq="http://www.day.com/jcr/cq/1.0"
          xmlns:jcr="http://www.jcp.org/jcr/1.0"
          xmlns:nt="http://www.jcp.org/jcr/nt/1.0"
    jcr:primaryType="cq:Page">
    <jcr:content
        jcr:primaryType="cq:PageContent"
        jcr:title="{app_title}"
        sling:resourceType="{self.aem_utils.app_id}/components/page"
        cq:conf="/conf/{self.aem_utils.app_id}"/>
</jcr:root>
'''

    def _generate_language_root(self, language: str, country: str) -> str:
        """Generate the language root page."""
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<jcr:root xmlns:sling="http://sling.apache.org/jcr/sling/1.0"
          xmlns:cq="http://www.day.com/jcr/cq/1.0"
          xmlns:jcr="http://www.jcp.org/jcr/1.0"
          xmlns:nt="http://www.jcp.org/jcr/nt/1.0"
    jcr:primaryType="cq:Page">
    <jcr:content
        jcr:primaryType="cq:PageContent"
        jcr:title="{language.upper()}"
        jcr:language="{language}_{country}"
        sling:resourceType="{self.aem_utils.app_id}/components/page"
        cq:conf="/conf/{self.aem_utils.app_id}"
        cq:template="/conf/{self.aem_utils.app_id}/settings/wcm/templates/content-page"/>
</jcr:root>
'''

    def _generate_page(self, page_def: dict, parent_dir: Path) -> dict:
        """Generate a single page and its children."""
        files = {}
        name = AEMUtils.sanitize_node_name(page_def.get("name", "page"))
        title = page_def.get("title", name.replace("-", " ").title())
        template = page_def.get("template", "content-page")
        page_dir = parent_dir / name

        page_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<jcr:root xmlns:sling="http://sling.apache.org/jcr/sling/1.0"
          xmlns:cq="http://www.day.com/jcr/cq/1.0"
          xmlns:jcr="http://www.jcp.org/jcr/1.0"
          xmlns:nt="http://www.jcp.org/jcr/nt/1.0"
    jcr:primaryType="cq:Page">
    <jcr:content
        jcr:primaryType="cq:PageContent"
        jcr:title="{title}"
        sling:resourceType="{self.aem_utils.app_id}/components/page"
        cq:template="/conf/{self.aem_utils.app_id}/settings/wcm/templates/{template}">
        <root
            jcr:primaryType="nt:unstructured"
            sling:resourceType="wcm/foundation/components/responsivegrid"/>
    </jcr:content>
</jcr:root>
'''
        files[str(page_dir / ".content.xml")] = page_xml

        # Recurse for child pages
        for child in page_def.get("children", []):
            child_files = self._generate_page(child, page_dir)
            files.update(child_files)

        return files

    def _generate_dam_root(self) -> str:
        """Generate the DAM folder root."""
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<jcr:root xmlns:sling="http://sling.apache.org/jcr/sling/1.0"
          xmlns:jcr="http://www.jcp.org/jcr/1.0"
          xmlns:nt="http://www.jcp.org/jcr/nt/1.0"
    jcr:primaryType="sling:OrderedFolder"
    jcr:title="{self.aem_utils.project_config.get('app_title', 'Modernized Site')} Assets"/>
'''
