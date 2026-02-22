"""Tests for AEM utility functions."""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils.aem_utils import AEMUtils


@pytest.fixture
def config():
    return {
        "aem": {
            "version": "6.5.7",
            "project": {
                "group_id": "com.testsite",
                "artifact_id": "testsite",
                "app_title": "Test Site",
                "app_id": "testsite",
                "package": "com.testsite",
            },
        }
    }


@pytest.fixture
def aem_utils(config):
    return AEMUtils(config)


class TestAEMUtils:
    def test_get_component_path(self, aem_utils):
        assert aem_utils.get_component_path("hero") == "/apps/testsite/components/hero"

    def test_get_component_resource_type(self, aem_utils):
        assert aem_utils.get_component_resource_type("hero") == "testsite/components/hero"

    def test_get_template_path(self, aem_utils):
        assert aem_utils.get_template_path("content-page") == (
            "/conf/testsite/settings/wcm/templates/content-page"
        )

    def test_get_clientlib_category(self, aem_utils):
        assert aem_utils.get_clientlib_category("base") == "testsite.base"

    def test_get_sling_model_class_name(self, aem_utils):
        assert aem_utils.get_sling_model_class_name("hero-banner") == "HeroBanner"
        assert aem_utils.get_sling_model_class_name("card") == "Card"
        assert aem_utils.get_sling_model_class_name("content_block") == "ContentBlock"

    def test_get_sling_model_fqcn(self, aem_utils):
        assert aem_utils.get_sling_model_fqcn("hero") == "com.testsite.models.Hero"

    def test_sanitize_component_name(self):
        assert AEMUtils.sanitize_component_name("Hero Banner!") == "hero-banner"
        assert AEMUtils.sanitize_component_name("My_Component") == "my-component"
        assert AEMUtils.sanitize_component_name("  spaces  ") == "spaces"

    def test_sanitize_node_name(self):
        assert AEMUtils.sanitize_node_name("My Node!") == "mynode"
        assert AEMUtils.sanitize_node_name("test-name_123") == "test-name_123"

    def test_create_content_xml(self):
        xml = AEMUtils.create_content_xml(
            primary_type="cq:Component",
            properties={"jcr:title": "Test", "componentGroup": "Content"},
        )
        assert 'jcr:primaryType="cq:Component"' in xml
        assert 'jcr:title="Test"' in xml
        assert 'componentGroup="Content"' in xml

    def test_create_content_xml_with_resource_type(self):
        xml = AEMUtils.create_content_xml(
            primary_type="nt:unstructured",
            resource_type="mysite/components/hero",
        )
        assert 'sling:resourceType="mysite/components/hero"' in xml

    def test_generate_archetype_command(self, aem_utils):
        cmd = aem_utils.generate_archetype_command()
        assert "archetypeVersion=36" in cmd
        assert 'appId="testsite"' in cmd
        assert 'groupId="com.testsite"' in cmd


class TestDOMDecomposer:
    def test_import(self):
        from source_analysis.dom_decomposer import DOMDecomposer, DOMSection, PageStructure
        assert DOMDecomposer is not None

    def test_decompose_simple_page(self):
        from source_analysis.dom_decomposer import DOMDecomposer

        config = {"source_analysis": {"dom_decomposition": {}}}
        decomposer = DOMDecomposer(config)

        html = """
        <html>
        <body>
            <header class="site-header">
                <nav class="main-nav">
                    <a href="/">Home</a>
                </nav>
            </header>
            <main class="main-content">
                <h1>Hello World</h1>
                <p>This is a test page with some content.</p>
            </main>
            <footer class="site-footer">
                <p>Copyright 2024</p>
            </footer>
        </body>
        </html>
        """

        structure = decomposer.decompose("http://test.com", html, "Test Page")
        assert structure.url == "http://test.com"
        assert len(structure.sections) > 0

        # Should find header, content, footer sections
        section_types = [s.section_type for s in structure.sections]
        assert "header" in section_types or "navigation" in section_types


class TestComponentInventory:
    def test_import(self):
        from source_analysis.inventory import ComponentInventory, InventoryItem
        assert ComponentInventory is not None

    def test_add_classification(self):
        from source_analysis.inventory import ComponentInventory
        from source_analysis.component_classifier import ComponentClassification

        inventory = ComponentInventory()
        classification = ComponentClassification(
            component_type="core_component",
            core_component_name="teaser",
            resource_type="core/wcm/components/teaser/v2/teaser",
            confidence=0.9,
            rationale="Matched teaser pattern",
        )

        inventory.add_classification(classification, "http://test.com", "<div>test</div>")

        assert len(inventory.items) == 1
        assert inventory.items[0].name == "teaser"
        assert inventory.items[0].occurrence_count == 1

    def test_merge_duplicate_classifications(self):
        from source_analysis.inventory import ComponentInventory
        from source_analysis.component_classifier import ComponentClassification

        inventory = ComponentInventory()
        classification = ComponentClassification(
            component_type="core_component",
            core_component_name="teaser",
            resource_type="core/wcm/components/teaser/v2/teaser",
            confidence=0.9,
        )

        inventory.add_classification(classification, "http://test.com/page1")
        inventory.add_classification(classification, "http://test.com/page2")

        assert len(inventory.items) == 1
        assert inventory.items[0].occurrence_count == 2
        assert len(inventory.items[0].page_urls) == 2

    def test_get_summary(self):
        from source_analysis.inventory import ComponentInventory
        from source_analysis.component_classifier import ComponentClassification

        inventory = ComponentInventory()
        inventory.page_count = 5

        for name in ["teaser", "title", "text"]:
            classification = ComponentClassification(
                component_type="core_component",
                core_component_name=name,
                confidence=0.9,
            )
            inventory.add_classification(classification, "http://test.com")

        summary = inventory.get_summary()
        assert summary["total_components"] == 3
        assert summary["by_type"]["core_component"] == 3
        assert summary["pages_analyzed"] == 5
