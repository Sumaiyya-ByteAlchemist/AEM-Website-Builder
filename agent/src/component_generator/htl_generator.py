"""HTL Generator - Generates HTL (Sightly) templates for AEM components."""

import logging
from pathlib import Path
from typing import Optional

from jinja2 import Environment, BaseLoader

from ..figma_pipeline.aem_mapper import AEMComponentSpec
from ..utils.aem_utils import AEMUtils
from ..utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Jinja2 template for generating HTL files
HTL_TEMPLATE = '''\
<!--/*
    {{ title }} Component
    ================================================================================
    sling:resourceType: {{ resource_type }}
    {% if super_type %}sling:resourceSuperType: {{ super_type }}{% endif %}
*/-->
{% if is_extension %}
{# Core Component Extension - delegate to core with custom markup wrapper #}
<div class="cmp-{{ name }}"
     data-sly-use.model="${ '{{ model_class }}' }"
     data-sly-test="${model}">

    {# Delegate to the core component #}
    <sly data-sly-resource="${ '.' @ resourceType='{{ super_type }}'}" />
</div>
{% elif is_custom %}
{# Custom Component #}
<div class="cmp-{{ name }}"
     data-sly-use.model="${ '{{ model_class }}' }"
     data-sly-test="${model}">

{% for slot in content_slots %}
{% if slot.type == 'title' %}
    <{{ slot.get('heading_level', 'h2') }} class="cmp-{{ name }}__title"
       data-sly-test="${model.{{ slot.property_name or 'title' }}}">
        ${model.{{ slot.property_name or 'title' }}}
    </{{ slot.get('heading_level', 'h2') }}>
{% elif slot.type == 'subtitle' %}
    <p class="cmp-{{ name }}__subtitle"
       data-sly-test="${model.{{ slot.property_name or 'subtitle' }}}">
        ${model.{{ slot.property_name or 'subtitle' }}}
    </p>
{% elif slot.type == 'text' %}
    <div class="cmp-{{ name }}__text"
         data-sly-test="${model.{{ slot.property_name or 'text' }}}"
         data-sly-unwrap>
        ${model.{{ slot.property_name or 'text' }} @ context='html'}
    </div>
{% elif slot.type == 'image' %}
    <div class="cmp-{{ name }}__image"
         data-sly-test="${model.{{ slot.property_name or 'fileReference' }}}">
        <img src="${model.{{ slot.property_name or 'fileReference' }}}"
             alt="${model.{{ slot.alt_property or 'alt' }} || ''}"
             class="cmp-{{ name }}__image-src"/>
    </div>
{% elif slot.type == 'button' %}
    <a class="cmp-{{ name }}__cta"
       data-sly-test="${model.{{ slot.link_property or 'ctaLink' }}}"
       href="${model.{{ slot.link_property or 'ctaLink' }}}">
        ${model.{{ slot.text_property or 'ctaText' }}}
    </a>
{% endif %}
{% endfor %}

{% if is_container %}
    <div class="cmp-{{ name }}__content">
        <sly data-sly-resource="${'content' @ resourceType='wcm/foundation/components/responsivegrid'}" />
    </div>
{% endif %}

</div>
{% else %}
{# Direct Core Component usage (proxy) #}
<sly data-sly-resource="${ '.' @ resourceType='{{ super_type or resource_type }}'}" />
{% endif %}
'''


class HTLGenerator:
    """Generates HTL (Sightly) template files for AEM components.

    Supports:
    - Core Component proxies (simple delegation)
    - Core Component extensions (custom wrapper + delegation)
    - Fully custom components (complete HTL markup)
    """

    def __init__(self, config: dict):
        self.config = config.get("component_generation", {}).get("htl", {})
        self.aem_utils = AEMUtils(config)
        self.llm_client = LLMClient(config)
        self.use_core_inheritance = self.config.get("use_core_component_inheritance", True)

        self.jinja_env = Environment(loader=BaseLoader())

    def generate(self, spec: AEMComponentSpec, output_dir: str) -> dict:
        """Generate HTL files for a component.

        Args:
            spec: AEM component specification.
            output_dir: Base output directory for the AEM project.

        Returns:
            Dict with generated file paths and content.
        """
        files = {}
        component_dir = Path(output_dir) / "ui.apps" / "src" / "main" / "content" / "jcr_root" / "apps" / self.aem_utils.app_id / "components" / spec.name

        # Generate .content.xml (component definition)
        content_xml = self._generate_component_definition(spec)
        files[str(component_dir / ".content.xml")] = content_xml

        # Generate the HTL template
        if spec.component_type == "custom_component" or spec.component_type == "core_extension":
            # Use LLM for complex custom components
            if spec.source_html and spec.component_type == "custom_component":
                htl_content = self._generate_htl_with_llm(spec)
            else:
                htl_content = self._generate_htl_from_template(spec)
            files[str(component_dir / f"{spec.name}.html")] = htl_content
        else:
            # Core component proxy - just needs delegation
            htl_content = self._generate_proxy_htl(spec)
            files[str(component_dir / f"{spec.name}.html")] = htl_content

        # Write files
        for file_path, content in files.items():
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

        logger.info(f"Generated HTL for '{spec.name}': {len(files)} files")
        return files

    def _generate_component_definition(self, spec: AEMComponentSpec) -> str:
        """Generate .content.xml component definition."""
        properties = {
            "jcr:title": spec.title,
            "componentGroup": spec.component_group,
        }

        resource_type = None
        if spec.super_type:
            properties["sling:resourceSuperType"] = spec.super_type

        return AEMUtils.create_content_xml(
            primary_type="cq:Component",
            resource_type=resource_type,
            properties=properties,
        )

    def _generate_htl_from_template(self, spec: AEMComponentSpec) -> str:
        """Generate HTL using the Jinja2 template."""
        model_class = self.aem_utils.get_sling_model_fqcn(spec.name)

        # Prepare content slots with property names
        prepared_slots = []
        for slot in spec.content_slots:
            prepared_slot = dict(slot)
            if "property_name" not in prepared_slot:
                prepared_slot["property_name"] = slot.get("name", slot["type"])
            prepared_slots.append(prepared_slot)

        template = self.jinja_env.from_string(HTL_TEMPLATE)
        return template.render(
            name=spec.name,
            title=spec.title,
            resource_type=spec.resource_type,
            super_type=spec.super_type,
            model_class=model_class,
            is_extension=spec.component_type == "core_extension",
            is_custom=spec.component_type == "custom_component",
            is_container=spec.is_container,
            content_slots=prepared_slots,
        )

    def _generate_proxy_htl(self, spec: AEMComponentSpec) -> str:
        """Generate a simple proxy HTL that delegates to the core component."""
        core_type = spec.super_type or AEMUtils.CORE_COMPONENT_TYPES.get(
            spec.core_component_name, ""
        )

        return (
            f'<!--/* {spec.title} - Core Component Proxy */-->\n'
            f'<sly data-sly-resource="${{\'.\' @ resourceType=\'{core_type}\'}}" />\n'
        )

    def _generate_htl_with_llm(self, spec: AEMComponentSpec) -> str:
        """Use LLM to generate HTL for complex custom components."""
        component_spec_data = {
            "name": spec.name,
            "title": spec.title,
            "component_type": spec.component_type,
            "resource_type": spec.resource_type,
            "properties": spec.properties,
            "content_slots": spec.content_slots,
            "is_container": spec.is_container,
            "source_html": spec.source_html[:2000] if spec.source_html else "",
            "model_class": self.aem_utils.get_sling_model_fqcn(spec.name),
            "css_classes": spec.css_classes,
        }

        try:
            return self.llm_client.generate_htl_template(component_spec_data)
        except Exception as e:
            logger.warning(f"LLM HTL generation failed, using template: {e}")
            return self._generate_htl_from_template(spec)
