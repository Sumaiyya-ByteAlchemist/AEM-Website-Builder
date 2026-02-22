"""Sling Model Generator - Generates Java Sling Model classes for AEM components."""

import logging
import re
from pathlib import Path

from ..figma_pipeline.aem_mapper import AEMComponentSpec
from ..utils.aem_utils import AEMUtils
from ..utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Java type mappings from JCR property types
JCR_TO_JAVA_TYPES = {
    "String": "String",
    "Boolean": "Boolean",
    "Long": "Long",
    "Double": "Double",
    "Calendar": "Calendar",
    "Date": "Calendar",
    "String[]": "String[]",
}

# Core Component delegation interfaces
CORE_DELEGATION_MAP = {
    "title": "com.adobe.cq.wcm.core.components.models.Title",
    "text": "com.adobe.cq.wcm.core.components.models.Text",
    "image": "com.adobe.cq.wcm.core.components.models.Image",
    "button": "com.adobe.cq.wcm.core.components.models.Button",
    "teaser": "com.adobe.cq.wcm.core.components.models.Teaser",
    "list": "com.adobe.cq.wcm.core.components.models.List",
    "navigation": "com.adobe.cq.wcm.core.components.models.Navigation",
    "breadcrumb": "com.adobe.cq.wcm.core.components.models.Breadcrumb",
    "carousel": "com.adobe.cq.wcm.core.components.models.Carousel",
    "accordion": "com.adobe.cq.wcm.core.components.models.Accordion",
    "tabs": "com.adobe.cq.wcm.core.components.models.Tabs",
    "container": "com.adobe.cq.wcm.core.components.models.LayoutContainer",
    "embed": "com.adobe.cq.wcm.core.components.models.Embed",
    "download": "com.adobe.cq.wcm.core.components.models.Download",
}


class SlingModelGenerator:
    """Generates Sling Model Java classes for AEM components.

    Supports:
    - Custom Sling Models with @ValueMapValue injection
    - Core Component delegation pattern
    - Interface + Implementation pattern
    """

    def __init__(self, config: dict):
        self.config = config.get("component_generation", {}).get("sling_model", {})
        self.aem_utils = AEMUtils(config)
        self.llm_client = LLMClient(config)
        self.package_name = self.aem_utils.package_name

    def generate(self, spec: AEMComponentSpec, output_dir: str) -> dict:
        """Generate Sling Model Java files for a component.

        Args:
            spec: AEM component specification.
            output_dir: Base output directory for the AEM project.

        Returns:
            Dict with generated file paths and content.
        """
        files = {}

        # Skip for pure proxy components
        if spec.component_type == "core_component" and not spec.properties:
            return files

        class_name = self.aem_utils.get_sling_model_class_name(spec.name)
        package_path = self.package_name.replace(".", "/")
        model_dir = Path(output_dir) / "core" / "src" / "main" / "java" / package_path / "models"

        if spec.component_type == "core_extension" and spec.core_component_name in CORE_DELEGATION_MAP:
            # Generate delegation model
            java_content = self._generate_delegation_model(spec, class_name)
        else:
            # Generate standard Sling Model
            java_content = self._generate_standard_model(spec, class_name)

        model_path = model_dir / f"{class_name}.java"
        files[str(model_path)] = java_content

        # Write files
        for file_path, content in files.items():
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

        logger.info(f"Generated Sling Model for '{spec.name}': {class_name}.java")
        return files

    def _generate_standard_model(self, spec: AEMComponentSpec, class_name: str) -> str:
        """Generate a standard Sling Model class."""
        resource_type = spec.resource_type
        properties = spec.properties or []

        # Build imports
        imports = [
            "javax.annotation.PostConstruct",
            "org.apache.sling.api.SlingHttpServletRequest",
            "org.apache.sling.api.resource.Resource",
            "org.apache.sling.models.annotations.DefaultInjectionStrategy",
            "org.apache.sling.models.annotations.Model",
            "org.apache.sling.models.annotations.injectorspecific.ValueMapValue",
        ]

        # Add type-specific imports
        for prop in properties:
            java_type = JCR_TO_JAVA_TYPES.get(prop.get("type", "String"), "String")
            if java_type == "Calendar":
                imports.append("java.util.Calendar")

        imports = sorted(set(imports))
        imports_str = "\n".join(f"import {imp};" for imp in imports)

        # Build fields
        fields_str = self._generate_fields(properties)

        # Build getters
        getters_str = self._generate_getters(properties)

        return f'''package {self.package_name}.models;

{imports_str}

/**
 * Sling Model for the {spec.title} component.
 *
 * @sling:resourceType {resource_type}
 */
@Model(
    adaptables = SlingHttpServletRequest.class,
    adapters = {class_name}.class,
    resourceType = {class_name}.RESOURCE_TYPE,
    defaultInjectionStrategy = DefaultInjectionStrategy.OPTIONAL
)
public class {class_name} {{

    protected static final String RESOURCE_TYPE = "{resource_type}";

{fields_str}

    @PostConstruct
    protected void init() {{
        // Initialization logic
    }}

{getters_str}
}}
'''

    def _generate_delegation_model(self, spec: AEMComponentSpec, class_name: str) -> str:
        """Generate a Sling Model that delegates to a Core Component model."""
        core_interface = CORE_DELEGATION_MAP.get(spec.core_component_name, "")
        core_class_simple = core_interface.split(".")[-1] if core_interface else ""
        resource_type = spec.resource_type
        extra_properties = spec.properties or []

        imports = [
            "javax.annotation.PostConstruct",
            "org.apache.sling.api.SlingHttpServletRequest",
            "org.apache.sling.models.annotations.DefaultInjectionStrategy",
            "org.apache.sling.models.annotations.Model",
            "org.apache.sling.models.annotations.Via",
            "org.apache.sling.models.annotations.injectorspecific.Self",
            "org.apache.sling.models.annotations.injectorspecific.ValueMapValue",
            "org.apache.sling.models.annotations.via.ResourceSuperType",
        ]

        if core_interface:
            imports.append(core_interface)

        # Add imports for extra properties
        for prop in extra_properties:
            java_type = JCR_TO_JAVA_TYPES.get(prop.get("type", "String"), "String")
            if java_type == "Calendar":
                imports.append("java.util.Calendar")

        imports = sorted(set(imports))
        imports_str = "\n".join(f"import {imp};" for imp in imports)

        # Build extra fields
        extra_fields = self._generate_fields(extra_properties)
        extra_getters = self._generate_getters(extra_properties)

        implements = f" implements {core_class_simple}" if core_class_simple else ""
        delegate_field = ""
        if core_class_simple:
            delegate_field = f'''
    @Self
    @Via(type = ResourceSuperType.class)
    private {core_class_simple} delegate;
'''

        return f'''package {self.package_name}.models;

{imports_str}

/**
 * Sling Model for the {spec.title} component.
 * Extends the Core {core_class_simple or "Component"} with additional properties.
 *
 * @sling:resourceType {resource_type}
 */
@Model(
    adaptables = SlingHttpServletRequest.class,
    adapters = {{ {class_name}.class{", " + core_class_simple + ".class" if core_class_simple else ""} }},
    resourceType = {class_name}.RESOURCE_TYPE,
    defaultInjectionStrategy = DefaultInjectionStrategy.OPTIONAL
)
public class {class_name}{implements} {{

    protected static final String RESOURCE_TYPE = "{resource_type}";
{delegate_field}
{extra_fields}

    @PostConstruct
    protected void init() {{
        // Additional initialization
    }}

    /**
     * Returns the delegate Core Component model.
     */
    public {core_class_simple or "Object"} getDelegate() {{
        return delegate;
    }}

{extra_getters}
}}
'''

    def _generate_fields(self, properties: list) -> str:
        """Generate Java field declarations."""
        fields = []
        for prop in properties:
            name = prop.get("name", "unknown")
            java_name = self._to_java_field_name(name)
            java_type = JCR_TO_JAVA_TYPES.get(prop.get("type", "String"), "String")

            fields.append(f'    @ValueMapValue\n    private {java_type} {java_name};')

        return "\n\n".join(fields)

    def _generate_getters(self, properties: list) -> str:
        """Generate Java getter methods."""
        getters = []
        for prop in properties:
            name = prop.get("name", "unknown")
            java_name = self._to_java_field_name(name)
            java_type = JCR_TO_JAVA_TYPES.get(prop.get("type", "String"), "String")
            getter_name = f"get{java_name[0].upper()}{java_name[1:]}"
            label = prop.get("label", name)

            getters.append(f'''    /**
     * Returns the {label.lower()}.
     */
    public {java_type} {getter_name}() {{
        return {java_name};
    }}''')

        return "\n\n".join(getters)

    def _to_java_field_name(self, name: str) -> str:
        """Convert a JCR property name to a Java field name."""
        # Remove JCR namespace prefix
        name = re.sub(r"^[a-z]+:", "", name)
        # Convert kebab-case/snake_case to camelCase
        parts = re.split(r"[-_]", name)
        return parts[0] + "".join(p.capitalize() for p in parts[1:])
