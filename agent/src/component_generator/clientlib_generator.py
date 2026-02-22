"""Client Library Generator - Generates AEM clientlib folders with CSS and JS."""

import logging
from pathlib import Path

from ..figma_pipeline.aem_mapper import AEMComponentSpec
from ..utils.aem_utils import AEMUtils
from ..utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


class ClientLibGenerator:
    """Generates AEM Client Library (clientlib) folders for components.

    Creates:
    - clientlib folder with .content.xml
    - CSS file with BEM naming
    - JS file for interactive components
    - js.txt and css.txt manifest files
    """

    def __init__(self, config: dict):
        self.config = config.get("component_generation", {}).get("clientlib", {})
        self.aem_utils = AEMUtils(config)
        self.llm_client = LLMClient(config)
        self.category_prefix = self.config.get("categories_prefix", self.aem_utils.app_id)

    def generate(self, spec: AEMComponentSpec, output_dir: str) -> dict:
        """Generate clientlib files for a component.

        Args:
            spec: AEM component specification.
            output_dir: Base output directory for the AEM project.

        Returns:
            Dict with generated file paths and content.
        """
        files = {}

        # Skip for pure proxy components (use core component styling)
        if spec.component_type == "core_component" and not spec.design_tokens:
            return files

        clientlib_dir = (
            Path(output_dir) / "ui.apps" / "src" / "main" / "content" / "jcr_root"
            / "apps" / self.aem_utils.app_id / "clientlibs"
            / f"clientlib-{spec.name}"
        )

        # Generate .content.xml
        category = f"{self.category_prefix}.{spec.name}"
        content_xml = self._generate_content_xml(category, spec)
        files[str(clientlib_dir / ".content.xml")] = content_xml

        # Generate CSS
        css_content = self._generate_css(spec)
        css_dir = clientlib_dir / "css"
        files[str(css_dir / f"{spec.name}.css")] = css_content
        files[str(clientlib_dir / "css.txt")] = f"#base=css\n{spec.name}.css\n"

        # Generate JS for interactive components
        if self._needs_javascript(spec):
            js_content = self._generate_js(spec)
            js_dir = clientlib_dir / "js"
            files[str(js_dir / f"{spec.name}.js")] = js_content
            files[str(clientlib_dir / "js.txt")] = f"#base=js\n{spec.name}.js\n"

        # Write files
        for file_path, content in files.items():
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

        logger.info(f"Generated clientlib for '{spec.name}': {len(files)} files")
        return files

    def generate_base_clientlib(self, output_dir: str, design_tokens: dict = None) -> dict:
        """Generate the base site clientlib with design tokens.

        Args:
            output_dir: Base output directory.
            design_tokens: Optional design tokens for CSS variables.

        Returns:
            Dict with generated file paths.
        """
        files = {}
        clientlib_dir = (
            Path(output_dir) / "ui.apps" / "src" / "main" / "content" / "jcr_root"
            / "apps" / self.aem_utils.app_id / "clientlibs" / "clientlib-base"
        )

        # .content.xml
        content_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<jcr:root xmlns:cq="http://www.day.com/jcr/cq/1.0"
          xmlns:jcr="http://www.jcp.org/jcr/1.0"
    jcr:primaryType="cq:ClientLibraryFolder"
    categories="[{self.category_prefix}.base]"
    allowProxy="{{Boolean}}true"/>
'''
        files[str(clientlib_dir / ".content.xml")] = content_xml

        # Base CSS with design tokens
        base_css = self._generate_base_css(design_tokens)
        files[str(clientlib_dir / "css" / "base.css")] = base_css
        files[str(clientlib_dir / "css.txt")] = "#base=css\nbase.css\n"

        # Write files
        for file_path, content in files.items():
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

        return files

    def _generate_content_xml(self, category: str, spec: AEMComponentSpec) -> str:
        """Generate .content.xml for the clientlib folder."""
        dependencies = f"{self.category_prefix}.base"

        return f'''<?xml version="1.0" encoding="UTF-8"?>
<jcr:root xmlns:cq="http://www.day.com/jcr/cq/1.0"
          xmlns:jcr="http://www.jcp.org/jcr/1.0"
    jcr:primaryType="cq:ClientLibraryFolder"
    categories="[{category}]"
    dependencies="[{dependencies}]"
    allowProxy="{{Boolean}}true"/>
'''

    def _generate_css(self, spec: AEMComponentSpec) -> str:
        """Generate CSS for a component using BEM naming."""
        name = spec.name
        tokens = spec.design_tokens or {}

        # Try LLM generation for complex components with source HTML
        if spec.source_html:
            try:
                return self.llm_client.generate_css(
                    {"name": name, "title": spec.title, "properties": spec.properties},
                    spec.source_html[:2000],
                )
            except Exception as e:
                logger.warning(f"LLM CSS generation failed, using template: {e}")

        # Template-based CSS generation
        lines = [
            f"/* {spec.title} Component */",
            f".cmp-{name} {{",
            "  display: block;",
            "  position: relative;",
        ]

        # Add spacing from design tokens
        spacing = tokens.get("spacing", {})
        if spacing.get("padding"):
            padding = spacing["padding"]
            lines.append(f"  padding: {padding.get('top', 0)}px {padding.get('right', 0)}px "
                        f"{padding.get('bottom', 0)}px {padding.get('left', 0)}px;")

        lines.append("}")
        lines.append("")

        # Generate sub-element styles
        for slot in spec.content_slots:
            slot_name = slot.get("name", slot.get("type", "element"))
            lines.extend([
                f".cmp-{name}__{slot_name} {{",
            ])

            if slot.get("type") == "title":
                typo = slot.get("typography", {})
                if typo.get("font_size"):
                    lines.append(f"  font-size: {typo['font_size']}px;")
                if typo.get("font_weight"):
                    lines.append(f"  font-weight: {typo['font_weight']};")
                lines.append("  margin-bottom: 0.5em;")
            elif slot.get("type") == "image":
                lines.extend([
                    "  width: 100%;",
                    "  height: auto;",
                    "  display: block;",
                ])
            elif slot.get("type") == "button":
                lines.extend([
                    "  display: inline-block;",
                    "  padding: 0.75em 1.5em;",
                    "  text-decoration: none;",
                    "  cursor: pointer;",
                    "  transition: opacity 0.2s ease;",
                ])

            lines.append("}")
            lines.append("")

        # Add Style System variant styles
        for style in spec.style_system_styles:
            css_class = style.get("css_class", "")
            if css_class:
                lines.extend([
                    f"/* Style: {style.get('label', '')} */",
                    f".{css_class} {{",
                    "  /* Add variant-specific styles */",
                    "}",
                    "",
                ])

        # Responsive styles
        lines.extend([
            "/* Responsive */",
            "@media (max-width: 768px) {",
            f"  .cmp-{name} {{",
            "    /* Mobile adjustments */",
            "  }",
            "}",
        ])

        return "\n".join(lines)

    def _generate_js(self, spec: AEMComponentSpec) -> str:
        """Generate JavaScript for interactive components."""
        name = spec.name
        class_name = self.aem_utils.get_sling_model_class_name(name)

        return f'''"use strict";

/**
 * {spec.title} Component JavaScript
 */
(function() {{
    "use strict";

    var NS = "{self.aem_utils.app_id}";
    var IS = "{name}";

    var selectors = {{
        self: '[data-cmp-is="{name}"]',
    }};

    function {class_name}(config) {{
        var that = this;

        function init(element) {{
            that.element = element;
            // Initialize component behavior
            bindEvents();
        }}

        function bindEvents() {{
            // Add event listeners
        }}

        if (config && config.element) {{
            init(config.element);
        }}
    }}

    function onDocumentReady() {{
        var elements = document.querySelectorAll(selectors.self);
        for (var i = 0; i < elements.length; i++) {{
            new {class_name}({{ element: elements[i] }});
        }}

        // Listen for new components added via AEM editor
        var MutationObserver = window.MutationObserver || window.WebKitMutationObserver;
        if (MutationObserver) {{
            var observer = new MutationObserver(function(mutations) {{
                mutations.forEach(function(mutation) {{
                    var addedNodes = mutation.addedNodes;
                    for (var i = 0; i < addedNodes.length; i++) {{
                        if (addedNodes[i].querySelectorAll) {{
                            var newElements = addedNodes[i].querySelectorAll(selectors.self);
                            for (var j = 0; j < newElements.length; j++) {{
                                new {class_name}({{ element: newElements[j] }});
                            }}
                        }}
                    }}
                }});
            }});

            observer.observe(document.body, {{
                subtree: true,
                childList: true,
            }});
        }}
    }}

    if (document.readyState !== "loading") {{
        onDocumentReady();
    }} else {{
        document.addEventListener("DOMContentLoaded", onDocumentReady);
    }}

}})();
'''

    def _generate_base_css(self, design_tokens: dict = None) -> str:
        """Generate the base site CSS with design tokens."""
        lines = [
            "/* Base Site Styles - Generated by AEM Modernization Agent */",
            "",
            "/* Design Tokens */",
            ":root {",
        ]

        if design_tokens:
            for category, tokens in design_tokens.items():
                if tokens:
                    lines.append(f"  /* {category.title()} */")
                    for var_name in tokens:
                        lines.append(f"  {var_name}: initial;")
        else:
            lines.extend([
                "  /* Colors */",
                "  --color-primary: #0052cc;",
                "  --color-secondary: #172b4d;",
                "  --color-accent: #ff5630;",
                "  --color-background: #ffffff;",
                "  --color-surface: #f4f5f7;",
                "  --color-text: #172b4d;",
                "  --color-text-light: #6b778c;",
                "",
                "  /* Typography */",
                "  --font-family-primary: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;",
                "  --font-family-heading: var(--font-family-primary);",
                "  --font-size-base: 16px;",
                "  --font-size-sm: 14px;",
                "  --font-size-lg: 18px;",
                "  --font-size-xl: 24px;",
                "  --font-size-2xl: 32px;",
                "  --font-size-3xl: 48px;",
                "",
                "  /* Spacing */",
                "  --space-xs: 4px;",
                "  --space-sm: 8px;",
                "  --space-md: 16px;",
                "  --space-lg: 24px;",
                "  --space-xl: 32px;",
                "  --space-2xl: 48px;",
                "  --space-3xl: 64px;",
                "",
                "  /* Layout */",
                "  --container-max-width: 1200px;",
                "  --grid-columns: 12;",
                "  --grid-gutter: 24px;",
            ])

        lines.extend([
            "}",
            "",
            "/* Base Reset & Defaults */",
            "*, *::before, *::after {",
            "  box-sizing: border-box;",
            "}",
            "",
            "body {",
            "  font-family: var(--font-family-primary);",
            "  font-size: var(--font-size-base);",
            "  color: var(--color-text);",
            "  background-color: var(--color-background);",
            "  line-height: 1.5;",
            "  margin: 0;",
            "}",
            "",
            "img {",
            "  max-width: 100%;",
            "  height: auto;",
            "}",
            "",
            "a {",
            "  color: var(--color-primary);",
            "}",
            "",
            ".container {",
            "  max-width: var(--container-max-width);",
            "  margin: 0 auto;",
            "  padding: 0 var(--grid-gutter);",
            "}",
        ])

        return "\n".join(lines)

    def _needs_javascript(self, spec: AEMComponentSpec) -> bool:
        """Determine if a component needs JavaScript."""
        # Interactive components need JS
        interactive_types = {"carousel", "accordion", "tabs"}
        if spec.core_component_name in interactive_types:
            return False  # Core components handle their own JS

        # Custom components with interactive elements
        if any(elem.get("type") == "interactive" for elem in spec.content_slots):
            return True

        # Components with specific names suggesting interactivity
        interactive_keywords = ["toggle", "modal", "dropdown", "popup", "collapse", "animate"]
        return any(kw in spec.name.lower() for kw in interactive_keywords)
