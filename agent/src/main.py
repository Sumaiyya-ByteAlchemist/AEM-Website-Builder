"""AEM Experience Modernization Agent - Main Orchestrator & CLI.

This is the central orchestrator that coordinates all pipeline stages:
1. Source Analysis  - Crawl & classify source site components
2. Figma Pipeline   - Convert Figma designs to AEM component specs
3. Project Setup    - Generate AEM project from archetype
4. Code Generation  - Generate HTL, dialogs, Sling Models, clientlibs
5. Template Assembly - Build page templates and policies
6. Content Migration - Extract, transform, and package content
7. Deployment       - Deploy to AEM SDK and validate
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import click
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from source_analysis.crawler import SiteCrawler
from source_analysis.dom_decomposer import DOMDecomposer
from source_analysis.component_classifier import ComponentClassifier
from source_analysis.inventory import ComponentInventory

from figma_pipeline.figma_mcp_client import FigmaMCPClient
from figma_pipeline.design_parser import DesignParser
from figma_pipeline.aem_mapper import FigmaToAEMMapper

from component_generator.htl_generator import HTLGenerator
from component_generator.dialog_generator import DialogGenerator
from component_generator.model_generator import SlingModelGenerator
from component_generator.clientlib_generator import ClientLibGenerator

from template_assembler.page_template_builder import PageTemplateBuilder
from template_assembler.policy_generator import PolicyGenerator
from template_assembler.content_structure import ContentStructureBuilder

from content_migrator.content_extractor import ContentExtractor
from content_migrator.content_transformer import ContentTransformer
from content_migrator.package_builder import AEMPackageBuilder

from deployment.sdk_manager import AEMSDKManager
from deployment.deployer import AEMDeployer
from deployment.validator import AEMValidator

from utils.aem_utils import AEMUtils

# Load environment variables
load_dotenv()

console = Console()
logger = logging.getLogger("aem-modernize")


def load_config(config_path: str = None) -> dict:
    """Load agent configuration from YAML file."""
    if config_path is None:
        config_path = str(Path(__file__).parent.parent / "config" / "agent_config.yaml")

    with open(config_path) as f:
        return yaml.safe_load(f)


def load_mappings(mappings_path: str = None) -> dict:
    """Load component mappings from YAML file."""
    if mappings_path is None:
        mappings_path = str(Path(__file__).parent.parent / "config" / "component_mappings.yaml")

    with open(mappings_path) as f:
        return yaml.safe_load(f)


# ============================================================================
# CLI Application
# ============================================================================

@click.group()
@click.option("--config", "-c", default=None, help="Path to agent_config.yaml")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(ctx, config, verbose):
    """AEM Experience Modernization Agent.

    AI-powered tool to modernize websites into AEM components and templates.
    """
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(config)
    ctx.obj["mappings"] = load_mappings()


# ============================================================================
# Step 1: Analyze Source Site
# ============================================================================

@cli.command()
@click.argument("url")
@click.option("--max-pages", "-m", default=20, help="Maximum pages to crawl")
@click.option("--output", "-o", default="./output/analysis", help="Output directory")
@click.pass_context
def analyze(ctx, url, max_pages, output):
    """Step 1: Analyze a source website and build component inventory.

    Crawls the given URL, decomposes each page into sections,
    and classifies sections as AEM component candidates.
    """
    config = ctx.obj["config"]
    mappings = ctx.obj["mappings"]

    # Override max_pages
    if "source_analysis" not in config:
        config["source_analysis"] = {}
    if "crawler" not in config["source_analysis"]:
        config["source_analysis"]["crawler"] = {}
    config["source_analysis"]["crawler"]["max_pages"] = max_pages

    console.print(Panel(f"[bold]Step 1: Source Analysis[/bold]\nAnalyzing: {url}"))

    # Phase 1: Crawl
    console.print("\n[bold cyan]Phase 1: Crawling site...[/bold cyan]")
    crawler = SiteCrawler(config)
    pages = crawler.crawl(url)
    console.print(f"  Crawled {len(pages)} pages")

    # Phase 2: Decompose DOM
    console.print("\n[bold cyan]Phase 2: Decomposing DOM...[/bold cyan]")
    decomposer = DOMDecomposer(config)
    structures = []
    for page in pages:
        structure = decomposer.decompose(page.url, page.html, page.title)
        structures.append(structure)
        console.print(f"  {page.url}: {len(structure.sections)} sections")

    # Phase 3: Classify components
    console.print("\n[bold cyan]Phase 3: Classifying components...[/bold cyan]")
    classifier = ComponentClassifier(config, mappings)
    inventory = ComponentInventory()
    inventory.page_count = len(pages)

    for structure in structures:
        classifications = classifier.classify_batch(
            structure.component_candidates,
            page_context=f"Page: {structure.url}, Title: {structure.title}",
        )
        inventory.add_template_regions(structure.template_regions)

        for candidate, classification in zip(structure.component_candidates, classifications):
            inventory.add_classification(
                classification,
                page_url=structure.url,
                html_sample=candidate.get("html_preview", ""),
            )

    inventory.calculate_priorities()

    # Export results
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)
    inventory.export_to_json(str(output_dir / "inventory.json"))
    inventory.export_report(str(output_dir / "inventory_report.txt"))

    # Display summary
    summary = inventory.get_summary()
    table = Table(title="Component Inventory Summary")
    table.add_column("Type", style="cyan")
    table.add_column("Count", style="green")
    for comp_type, count in summary["by_type"].items():
        table.add_row(comp_type, str(count))
    console.print(table)

    console.print(f"\n[green]Analysis complete! Results saved to {output}[/green]")


# ============================================================================
# Step 2: Figma-to-AEM Pipeline
# ============================================================================

@cli.command()
@click.argument("figma_url")
@click.option("--output", "-o", default="./output/figma", help="Output directory")
@click.pass_context
def figma(ctx, figma_url, output):
    """Step 2: Convert Figma designs to AEM component specs.

    Connects to Figma via MCP server, extracts components and design tokens,
    and maps them to AEM component specifications.
    """
    config = ctx.obj["config"]

    console.print(Panel(f"[bold]Step 2: Figma-to-AEM Pipeline[/bold]\nFigma: {figma_url}"))

    # Extract file key from URL
    file_key = _extract_figma_file_key(figma_url)
    if not file_key:
        console.print("[red]Invalid Figma URL. Expected format: https://www.figma.com/file/XXXXX/...[/red]")
        return

    # Initialize pipeline
    mcp_client = FigmaMCPClient(config)
    figma_token = os.environ.get("FIGMA_ACCESS_TOKEN")
    if figma_token:
        mcp_client.set_figma_token(figma_token)

    parser = DesignParser(config)
    mapper = FigmaToAEMMapper(config)

    # Phase 1: Fetch components
    console.print("\n[bold cyan]Phase 1: Fetching Figma components...[/bold cyan]")
    components = mcp_client.get_file_components(file_key)
    console.print(f"  Found {len(components)} components")

    # Phase 2: Extract design tokens
    console.print("\n[bold cyan]Phase 2: Extracting design tokens...[/bold cyan]")
    tokens = mcp_client.get_component_styles(file_key)
    parsed_tokens = parser.parse_design_tokens(tokens)

    # Phase 3: Parse and map components
    console.print("\n[bold cyan]Phase 3: Mapping to AEM components...[/bold cyan]")
    aem_specs = []
    for comp in components:
        parsed = parser.parse_component(comp)
        spec = mapper.map_component(parsed)
        aem_specs.append(spec)
        console.print(f"  {comp.name} -> {spec.component_type}: {spec.resource_type}")

    # Export results
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    specs_data = [
        {
            "name": s.name,
            "title": s.title,
            "component_type": s.component_type,
            "core_component": s.core_component_name,
            "resource_type": s.resource_type,
            "properties": s.properties,
            "styles": s.style_system_styles,
        }
        for s in aem_specs
    ]
    with open(output_dir / "component_specs.json", "w") as f:
        json.dump(specs_data, f, indent=2)

    with open(output_dir / "design_tokens.json", "w") as f:
        json.dump(parsed_tokens, f, indent=2)

    console.print(f"\n[green]Figma pipeline complete! {len(aem_specs)} components mapped.[/green]")


# ============================================================================
# Step 3: Generate AEM Project
# ============================================================================

@cli.command()
@click.option("--output", "-o", default="./output/aem-project", help="Output directory")
@click.option("--inventory", "-i", default=None, help="Path to inventory.json from analyze step")
@click.option("--specs", "-s", default=None, help="Path to component_specs.json from figma step")
@click.pass_context
def generate(ctx, output, inventory, specs):
    """Step 3-5: Generate AEM project with components, templates, and content.

    Uses the component inventory (from analyze) or component specs (from figma)
    to generate a complete AEM project.
    """
    config = ctx.obj["config"]
    mappings = ctx.obj["mappings"]
    aem_utils = AEMUtils(config)

    console.print(Panel("[bold]Steps 3-5: AEM Project Generation[/bold]"))

    # Load component specs
    from figma_pipeline.aem_mapper import AEMComponentSpec
    component_specs = []

    if specs:
        with open(specs) as f:
            specs_data = json.load(f)
        for s in specs_data:
            component_specs.append(AEMComponentSpec(
                name=s["name"],
                title=s.get("title", s["name"]),
                component_type=s["component_type"],
                core_component_name=s.get("core_component"),
                resource_type=s.get("resource_type", ""),
                properties=s.get("properties", []),
                style_system_styles=s.get("styles", []),
            ))
    elif inventory:
        with open(inventory) as f:
            inv_data = json.load(f)
        for c in inv_data.get("components", []):
            component_specs.append(AEMComponentSpec(
                name=c["name"],
                title=c["name"].replace("-", " ").title(),
                component_type=c["component_type"],
                core_component_name=c.get("core_component_name"),
                resource_type=c.get("resource_type", ""),
                super_type=AEMUtils.CORE_COMPONENT_TYPES.get(c.get("core_component_name", ""), None),
                properties=c.get("properties", []),
            ))

    if not component_specs:
        console.print("[yellow]No component specs provided. Generating project skeleton only.[/yellow]")

    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 3: Generate AEM archetype project
    console.print("\n[bold cyan]Step 3: Scaffolding AEM project...[/bold cyan]")
    console.print(f"  Project: {aem_utils.project_config.get('app_title', 'Modernized Site')}")
    console.print(f"  App ID: {aem_utils.app_id}")
    console.print(f"  Maven command:")
    console.print(f"  {aem_utils.generate_archetype_command()}")

    # Step 4: Generate components
    console.print(f"\n[bold cyan]Step 4: Generating {len(component_specs)} components...[/bold cyan]")

    htl_gen = HTLGenerator(config)
    dialog_gen = DialogGenerator(config)
    model_gen = SlingModelGenerator(config)
    clientlib_gen = ClientLibGenerator(config)

    for spec in component_specs:
        console.print(f"  Generating: {spec.name} ({spec.component_type})")
        htl_gen.generate(spec, str(output_dir))
        dialog_gen.generate(spec, str(output_dir))
        model_gen.generate(spec, str(output_dir))
        clientlib_gen.generate(spec, str(output_dir))

    # Generate base clientlib
    clientlib_gen.generate_base_clientlib(str(output_dir))

    # Step 5: Generate templates
    console.print("\n[bold cyan]Step 5: Generating templates...[/bold cyan]")

    template_builder = PageTemplateBuilder(config)
    policy_gen = PolicyGenerator(config)
    content_builder = ContentStructureBuilder(config)

    # Generate default page template
    template_builder.generate_template(
        "content-page",
        "Content Page",
        component_specs,
        template_regions=["header", "responsivegrid", "footer"],
        output_dir=str(output_dir),
    )

    # Generate landing page template
    template_builder.generate_template(
        "landing-page",
        "Landing Page",
        component_specs,
        template_regions=["header", "hero", "responsivegrid", "footer"],
        output_dir=str(output_dir),
    )

    # Generate policies
    policy_gen.generate_policies(component_specs, str(output_dir))

    # Generate content structure
    content_builder.generate_site_structure(
        pages=[
            {"name": "home", "title": "Home", "template": "landing-page"},
            {"name": "about", "title": "About Us", "template": "content-page"},
            {"name": "contact", "title": "Contact", "template": "content-page"},
        ],
        output_dir=str(output_dir),
    )

    console.print(f"\n[green]AEM project generated at {output_dir}[/green]")


# ============================================================================
# Step 6: Deploy to AEM SDK
# ============================================================================

@cli.command()
@click.option("--project", "-p", required=True, help="Path to AEM project directory")
@click.option("--skip-tests", is_flag=True, help="Skip tests during build")
@click.option("--validate", is_flag=True, help="Run validation after deployment")
@click.pass_context
def deploy(ctx, project, skip_tests, validate):
    """Step 6: Build, deploy, and validate on AEM local SDK.

    Builds the AEM project using Maven and deploys to a running
    local AEM SDK instance.
    """
    config = ctx.obj["config"]

    console.print(Panel("[bold]Step 6: Deploy to AEM SDK[/bold]"))

    sdk_manager = AEMSDKManager(config)
    deployer = AEMDeployer(config)
    validator_obj = AEMValidator(config)

    # Check if AEM is running
    if not sdk_manager.is_running("author"):
        console.print("[yellow]AEM author instance is not running.[/yellow]")
        console.print("Start AEM SDK first, then retry.")
        console.print(f"  SDK path: {sdk_manager.sdk_path or 'Not configured (set AEM_SDK_PATH)'}")
        return

    console.print("[green]AEM author instance is running.[/green]")

    # Build and deploy
    console.print("\n[bold cyan]Building and deploying...[/bold cyan]")
    success = deployer.maven_build_and_deploy(
        project,
        profiles=["autoInstallSinglePackage"],
        skip_tests=skip_tests,
    )

    if not success:
        console.print("[red]Build/deployment failed![/red]")
        return

    console.print("[green]Deployment successful![/green]")

    # Wait for stabilization
    deployer.wait_for_deployment()

    # Validate
    if validate:
        console.print("\n[bold cyan]Validating deployment...[/bold cyan]")

        # Get component names from project
        component_names = _discover_components(project, config)
        report = validator_obj.validate_all(component_names, ["content-page", "landing-page"])

        console.print(report.print_report())

        # Save report
        report_path = Path(project) / "validation-report.json"
        with open(report_path, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        console.print(f"\nReport saved to {report_path}")


# ============================================================================
# Full Pipeline
# ============================================================================

@cli.command()
@click.argument("source_url")
@click.option("--output", "-o", default="./output", help="Output directory")
@click.option("--figma-url", default=None, help="Optional Figma file URL")
@click.option("--max-pages", "-m", default=20, help="Maximum pages to crawl")
@click.pass_context
def run(ctx, source_url, output, figma_url, max_pages):
    """Run the complete modernization pipeline.

    Analyzes the source site, optionally integrates Figma designs,
    generates the AEM project, and prepares for deployment.
    """
    config = ctx.obj["config"]
    mappings = ctx.obj["mappings"]

    console.print(Panel(
        "[bold]AEM Experience Modernization Agent[/bold]\n"
        f"Source: {source_url}\n"
        f"Figma: {figma_url or 'N/A'}\n"
        f"Output: {output}"
    ))

    output_dir = Path(output)

    # Step 1: Analyze source
    console.print("\n" + "=" * 60)
    ctx.invoke(analyze, url=source_url, max_pages=max_pages, output=str(output_dir / "analysis"))

    # Step 2: Figma pipeline (optional)
    if figma_url:
        console.print("\n" + "=" * 60)
        ctx.invoke(figma, figma_url=figma_url, output=str(output_dir / "figma"))

    # Step 3-5: Generate project
    console.print("\n" + "=" * 60)
    inventory_path = str(output_dir / "analysis" / "inventory.json")
    specs_path = str(output_dir / "figma" / "component_specs.json") if figma_url else None

    ctx.invoke(
        generate,
        output=str(output_dir / "aem-project"),
        inventory=inventory_path,
        specs=specs_path,
    )

    console.print("\n" + "=" * 60)
    console.print(Panel(
        "[bold green]Modernization Complete![/bold green]\n\n"
        f"Generated AEM project: {output_dir / 'aem-project'}\n"
        f"Analysis report: {output_dir / 'analysis' / 'inventory_report.txt'}\n\n"
        "Next steps:\n"
        "  1. Review generated components and templates\n"
        "  2. Start AEM SDK: java -jar aem-sdk-quickstart-*.jar\n"
        "  3. Deploy: aem-modernize deploy -p ./output/aem-project\n"
        "  4. Access AEM: http://localhost:4502"
    ))


# ============================================================================
# SDK Management Commands
# ============================================================================

@cli.command()
@click.pass_context
def sdk_status(ctx):
    """Check AEM SDK instance status."""
    config = ctx.obj["config"]
    sdk_manager = AEMSDKManager(config)

    table = Table(title="AEM SDK Status")
    table.add_column("Instance", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("URL")

    for instance in ["author", "publish"]:
        running = sdk_manager.is_running(instance)
        url = sdk_manager.author_url if instance == "author" else sdk_manager.publish_url
        status = "[green]Running[/green]" if running else "[red]Stopped[/red]"
        table.add_row(instance.title(), status, url)

    console.print(table)

    if sdk_manager.sdk_path:
        console.print(f"\nSDK Path: {sdk_manager.sdk_path}")
    else:
        console.print("\n[yellow]AEM_SDK_PATH not set[/yellow]")


@cli.command()
@click.pass_context
def show_archetype_cmd(ctx):
    """Show the Maven archetype command for project generation."""
    config = ctx.obj["config"]
    aem_utils = AEMUtils(config)
    console.print("\n[bold]Maven Archetype Command:[/bold]\n")
    console.print(aem_utils.generate_archetype_command())


# ============================================================================
# Helpers
# ============================================================================

def _extract_figma_file_key(url: str) -> str:
    """Extract the file key from a Figma URL."""
    # https://www.figma.com/file/XXXXX/name or https://www.figma.com/design/XXXXX/name
    parts = url.rstrip("/").split("/")
    for i, part in enumerate(parts):
        if part in ("file", "design") and i + 1 < len(parts):
            return parts[i + 1]
    return ""


def _discover_components(project_dir: str, config: dict) -> list:
    """Discover component names from the project directory."""
    aem_utils = AEMUtils(config)
    components_dir = (
        Path(project_dir) / "ui.apps" / "src" / "main" / "content" / "jcr_root"
        / "apps" / aem_utils.app_id / "components"
    )

    if not components_dir.exists():
        return []

    return [
        d.name for d in components_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ]


if __name__ == "__main__":
    cli()
