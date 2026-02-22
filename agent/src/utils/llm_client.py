"""LLM Client - Wrapper around Anthropic Claude API for AEM modernization tasks."""

import json
import logging
from typing import Any

import anthropic

logger = logging.getLogger(__name__)


class LLMClient:
    """Client for interacting with Claude API for AEM modernization tasks."""

    def __init__(self, config: dict):
        self.config = config.get("llm", {})
        self.model = self.config.get("model", "claude-sonnet-4-20250514")
        self.max_tokens = self.config.get("max_tokens", 8192)
        self.temperature = self.config.get("temperature", 0.2)
        self.client = anthropic.Anthropic()

    def classify_component(self, html_snippet: str, context: str, mappings: dict) -> dict:
        """Use Claude to classify an HTML snippet as an AEM component type.

        Args:
            html_snippet: The HTML markup to classify.
            context: Surrounding context (page URL, section name, etc.).
            mappings: Available AEM Core Component mappings.

        Returns:
            Classification result with component type, confidence, and rationale.
        """
        component_list = "\n".join(
            f"- {name}: {comp.get('resource_type', '')} - patterns: {comp.get('patterns', [])}"
            for name, comp in mappings.get("core_components", {}).items()
        )

        prompt = f"""You are an AEM (Adobe Experience Manager) component classification expert.

Analyze the following HTML snippet and classify it as one of the AEM Core Components,
a Core Component extension, or a custom component.

## Available Core Components:
{component_list}

## HTML Snippet:
```html
{html_snippet}
```

## Context:
{context}

## Instructions:
1. Identify the primary purpose of this HTML section
2. Match it to the most appropriate AEM Core Component
3. If it closely matches but needs extensions, classify as "core_extension"
4. If no core component fits, classify as "custom_component"
5. If it's a layout wrapper, classify as "container" or "template_region"

Respond in JSON format:
{{
    "component_type": "core_component|core_extension|custom_component|container|template_region",
    "core_component_name": "name from the list above or null",
    "resource_type": "the sling:resourceType",
    "confidence": 0.0-1.0,
    "rationale": "explanation of why this classification was chosen",
    "suggested_name": "suggested component name if custom",
    "properties": [
        {{"name": "property_name", "type": "String|Boolean|Long", "value": "extracted value"}}
    ],
    "children": ["list of child component suggestions if container"]
}}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )

        return self._parse_json_response(response.content[0].text)

    def generate_htl_template(self, component_spec: dict) -> str:
        """Generate HTL (Sightly) template code for a component.

        Args:
            component_spec: Component specification including name, type, properties.

        Returns:
            Generated HTL template string.
        """
        prompt = f"""You are an AEM HTL (Sightly) template expert.

Generate a production-ready HTL template for the following AEM component specification.

## Component Specification:
```json
{json.dumps(component_spec, indent=2)}
```

## Requirements:
1. Use HTL best practices (data-sly-use, data-sly-test, data-sly-list, data-sly-resource)
2. Use the Sling Model via data-sly-use for the Java model class
3. Include proper WCM mode handling (edit vs disabled)
4. Use BEM CSS naming convention
5. Make it accessible (ARIA attributes where appropriate)
6. If this extends a Core Component, use data-sly-resource to delegate
7. Include proper null checks with data-sly-test

Return ONLY the HTL template code, no explanation."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )

        return self._extract_code_block(response.content[0].text, "html")

    def generate_dialog_xml(self, component_spec: dict) -> str:
        """Generate Touch UI dialog XML for a component.

        Args:
            component_spec: Component specification with properties.

        Returns:
            Generated _cq_dialog/.content.xml string.
        """
        prompt = f"""You are an AEM Touch UI dialog expert.

Generate a production-ready _cq_dialog/.content.xml for the following AEM component.

## Component Specification:
```json
{json.dumps(component_spec, indent=2)}
```

## Requirements:
1. Use Coral UI 3 (Granite UI) components
2. Include proper field types for each property (textfield, pathbrowser, checkbox, etc.)
3. Add field labels and descriptions
4. Group fields in tabs if there are more than 4 properties
5. Include validation where appropriate (required fields)
6. Use proper jcr:primaryType and sling:resourceType for each node

Return ONLY the XML, no explanation."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )

        return self._extract_code_block(response.content[0].text, "xml")

    def generate_sling_model(self, component_spec: dict, package_name: str) -> str:
        """Generate a Sling Model Java class for a component.

        Args:
            component_spec: Component specification.
            package_name: Java package name.

        Returns:
            Generated Java source code.
        """
        prompt = f"""You are an AEM Sling Model expert.

Generate a production-ready Sling Model Java class for the following AEM component.

## Component Specification:
```json
{json.dumps(component_spec, indent=2)}
```

## Package: {package_name}

## Requirements:
1. Use @Model annotation with adaptables = SlingHttpServletRequest.class
2. Set defaultInjectionStrategy = DefaultInjectionStrategy.OPTIONAL
3. Use @ValueMapValue for JCR properties
4. Use @ChildResource for child nodes
5. Include @PostConstruct init method if needed
6. Add Javadoc comments
7. If extending a Core Component, delegate to the core model
8. Use proper imports

Return ONLY the Java source code, no explanation."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )

        return self._extract_code_block(response.content[0].text, "java")

    def generate_css(self, component_spec: dict, html_reference: str) -> str:
        """Generate CSS styles for a component.

        Args:
            component_spec: Component specification.
            html_reference: Reference HTML for styling.

        Returns:
            Generated CSS string.
        """
        prompt = f"""You are a front-end CSS expert specializing in AEM component styling.

Generate production-ready CSS for the following AEM component.

## Component Specification:
```json
{json.dumps(component_spec, indent=2)}
```

## Reference HTML:
```html
{html_reference}
```

## Requirements:
1. Use BEM naming convention
2. Make it responsive with mobile-first approach
3. Use CSS custom properties (variables) for theming
4. Include hover/focus states for interactive elements
5. Ensure accessibility (focus indicators, contrast)
6. Keep selectors specific to the component (scoped)

Return ONLY the CSS code, no explanation."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )

        return self._extract_code_block(response.content[0].text, "css")

    def analyze_figma_component(self, design_data: dict) -> dict:
        """Analyze a Figma component and map it to AEM concepts.

        Args:
            design_data: Figma component data from MCP server.

        Returns:
            Analysis result with AEM component mapping.
        """
        prompt = f"""You are an expert in both Figma design systems and AEM component architecture.

Analyze this Figma component data and determine the best AEM component mapping.

## Figma Component Data:
```json
{json.dumps(design_data, indent=2)}
```

## Instructions:
1. Identify the visual purpose of this component
2. Extract design tokens (colors, typography, spacing)
3. Map to the most appropriate AEM Core Component or suggest a custom one
4. Define the component properties based on the design variants
5. Suggest responsive behavior

Respond in JSON format:
{{
    "component_name": "name",
    "aem_mapping": {{
        "type": "core_component|core_extension|custom_component",
        "core_component": "name or null",
        "resource_type": "sling:resourceType"
    }},
    "design_tokens": {{
        "colors": {{}},
        "typography": {{}},
        "spacing": {{}}
    }},
    "properties": [],
    "variants": [],
    "responsive_behavior": {{}}
}}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )

        return self._parse_json_response(response.content[0].text)

    def generate_content_mapping(self, source_content: dict, target_components: list) -> dict:
        """Map source content to target AEM component structure.

        Args:
            source_content: Extracted source content.
            target_components: Available target AEM components.

        Returns:
            Content mapping for migration.
        """
        prompt = f"""You are an AEM content migration expert.

Map the following source content to AEM component structure.

## Source Content:
```json
{json.dumps(source_content, indent=2)}
```

## Available AEM Components:
```json
{json.dumps(target_components, indent=2)}
```

## Instructions:
1. Map each content piece to the appropriate AEM component
2. Transform content values to match AEM property names
3. Handle rich text conversion (ensure valid AEM RTE format)
4. Map images to DAM asset references
5. Preserve content hierarchy

Respond in JSON format with the JCR node structure for the page content."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )

        return self._parse_json_response(response.content[0].text)

    def _parse_json_response(self, text: str) -> dict:
        """Extract and parse JSON from LLM response text."""
        # Try to find JSON block in markdown code fences
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            text = text[start:end].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON response, returning raw text")
            return {"raw_response": text, "parse_error": True}

    def _extract_code_block(self, text: str, language: str) -> str:
        """Extract code block from LLM response."""
        marker = f"```{language}"
        if marker in text:
            start = text.index(marker) + len(marker)
            end = text.index("```", start)
            return text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            return text[start:end].strip()
        return text.strip()
