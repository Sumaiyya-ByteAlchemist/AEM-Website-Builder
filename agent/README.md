# AEM Experience Modernization Agent

AI-powered agent that modernizes legacy websites into production-ready **Adobe Experience Manager (AEM)** projects using the [AEM Project Archetype](https://github.com/adobe/aem-project-archetype). It combines site analysis, Figma MCP integration, and LLM-driven code generation to produce traditional AEM components, templates, and content packages.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                  AEM Modernization Agent                        │
├─────────────┬──────────────┬──────────────┬────────────────────┤
│  Step 1     │  Step 2      │  Steps 3-5   │  Step 6            │
│  Source     │  Figma-to-   │  AEM Code    │  Deploy &          │
│  Analysis   │  AEM Pipeline│  Generation  │  Validate          │
├─────────────┼──────────────┼──────────────┼────────────────────┤
│ • Crawler   │ • MCP Client │ • HTL Gen    │ • SDK Manager      │
│ • DOM       │ • Design     │ • Dialog Gen │ • Maven Deployer   │
│   Decomposer│   Parser     │ • Model Gen  │ • Package Deployer │
│ • Component │ • AEM Mapper │ • ClientLib  │ • Validator        │
│   Classifier│              │ • Templates  │                    │
│ • Inventory │              │ • Policies   │                    │
│             │              │ • Content    │                    │
└─────────────┴──────────────┴──────────────┴────────────────────┘
         │              │              │               │
         ▼              ▼              ▼               ▼
   Claude API      Figma MCP     AEM Archetype    AEM Local SDK
```

### Pipeline Flow

```
Source Website ──┐
                 ├──► Component Inventory ──► AEM Component Specs
Figma Designs ───┘                                    │
                                                      ▼
                                          ┌──────────────────────┐
                                          │  AEM Project Output  │
                                          ├──────────────────────┤
                                          │ ui.apps/             │
                                          │   components/        │
                                          │     *.html (HTL)     │
                                          │     _cq_dialog/      │
                                          │   clientlibs/        │
                                          │ core/                │
                                          │   models/ (Sling)    │
                                          │ ui.content/          │
                                          │   templates/         │
                                          │   policies/          │
                                          │   content/           │
                                          └──────────────────────┘
                                                      │
                                                      ▼
                                              AEM Local SDK
                                          (Deploy & Validate)
```

---

## Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| Python | 3.10+ | Agent runtime |
| Java JDK | 11 | AEM SDK & Maven builds |
| Apache Maven | 3.3.9+ | AEM project builds |
| AEM SDK | 6.5.7+ or Cloud | Local development instance |
| Claude API Key | — | LLM-powered classification & code generation |

**Optional:**
- Figma Access Token — for Figma-to-AEM pipeline
- Figma MCP Server — for semantic design access
- Node.js 14+ — for frontend module builds

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Sumaiyya-ByteAlchemist/AEM-Website-Builder.git
cd AEM-Website-Builder/agent
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate   # macOS/Linux
# venv\Scripts\activate    # Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
# Required
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Required for Figma pipeline
FIGMA_ACCESS_TOKEN=figd_your-token-here

# AEM SDK (set path to your local SDK folder)
AEM_SDK_PATH=/path/to/aem-sdk
AEM_AUTHOR_URL=http://localhost:4502
AEM_ADMIN_USER=admin
AEM_ADMIN_PASSWORD=admin
```

### 5. Configure the Agent

Edit `config/agent_config.yaml` to customize your project:

```yaml
aem:
  version: "6.5.7"
  project:
    group_id: "com.mycompany"
    artifact_id: "mysite"
    app_title: "My Site"
    app_id: "mysite"
    package: "com.mycompany"
```

---

## Step-by-Step Usage

### Step 1: Analyze a Source Website

The Source Analysis Agent crawls a website, decomposes each page into semantic sections, and classifies them as AEM component candidates.

```bash
python src/main.py analyze https://example.com --max-pages 20 --output ./output/analysis
```

**What happens:**
1. **Crawl** — Visits up to 20 pages starting from the URL, respecting robots.txt and rate limits
2. **DOM Decomposition** — Parses each page's HTML into semantic sections (header, hero, navigation, content, footer, etc.)
3. **Component Classification** — Each section is classified using:
   - Rule-based heuristic matching against known AEM Core Component patterns
   - Claude LLM classification for ambiguous sections
4. **Inventory Generation** — Produces a prioritized component inventory

**Output:**
```
output/analysis/
├── inventory.json          # Machine-readable component inventory
└── inventory_report.txt    # Human-readable report
```

**Inventory classifies each section as one of:**
- `core_component` — Direct AEM Core Component (Text, Image, Title, Teaser, etc.)
- `core_extension` — Extends a Core Component with additional properties
- `custom_component` — Fully custom AEM component needed
- `container` — Layout container / responsive grid
- `template_region` — Part of the page template structure

---

### Step 2: Figma-to-AEM Pipeline (Optional)

If your source is a Figma design system, the agent connects via Figma's Model Context Protocol (MCP) server to semantically understand design components.

```bash
python src/main.py figma https://www.figma.com/file/XXXXX/MyDesign --output ./output/figma
```

**What happens:**
1. **MCP Connection** — Connects to Figma MCP server (falls back to REST API)
2. **Component Extraction** — Retrieves all components with layout, typography, colors
3. **Design Token Extraction** — Extracts colors, fonts, spacing as CSS custom properties
4. **AEM Mapping** — Maps each Figma component to an AEM Core Component or custom component spec

**Output:**
```
output/figma/
├── component_specs.json    # AEM component specifications
└── design_tokens.json      # Design tokens (CSS variables)
```

**Setting up Figma MCP Server:**

```bash
# Install the Figma MCP server
npx figma-developer-mcp --figma-api-key=YOUR_KEY

# The server runs on http://localhost:3845 by default
```

---

### Step 3-5: Generate AEM Project

Generate the complete AEM project with components, templates, policies, and content structure.

```bash
# From source analysis
python src/main.py generate \
  --inventory ./output/analysis/inventory.json \
  --output ./output/aem-project

# From Figma specs
python src/main.py generate \
  --specs ./output/figma/component_specs.json \
  --output ./output/aem-project

# Both sources combined
python src/main.py generate \
  --inventory ./output/analysis/inventory.json \
  --specs ./output/figma/component_specs.json \
  --output ./output/aem-project
```

**What is generated:**

```
output/aem-project/
├── ui.apps/
│   └── src/main/content/jcr_root/apps/{appId}/
│       ├── components/
│       │   ├── {component-name}/
│       │   │   ├── .content.xml           # Component definition
│       │   │   ├── {component-name}.html  # HTL template
│       │   │   └── _cq_dialog/
│       │   │       └── .content.xml       # Touch UI dialog
│       │   └── ...
│       └── clientlibs/
│           ├── clientlib-base/
│           │   ├── .content.xml
│           │   ├── css/base.css           # Design tokens & base styles
│           │   └── css.txt
│           └── clientlib-{component}/
│               ├── .content.xml
│               ├── css/{component}.css
│               ├── css.txt
│               ├── js/{component}.js      # (if interactive)
│               └── js.txt
├── core/
│   └── src/main/java/{package}/models/
│       ├── {Component}.java               # Sling Model
│       └── ...
└── ui.content/
    └── src/main/content/jcr_root/
        ├── conf/{appId}/settings/wcm/
        │   ├── templates/
        │   │   ├── content-page/          # Content page template
        │   │   └── landing-page/          # Landing page template
        │   └── policies/                  # Component policies & Style System
        └── content/{appId}/
            └── en/                        # Content structure
                ├── home/
                ├── about/
                └── contact/
```

**For each component, the agent generates:**

| Artifact | File | Description |
|---|---|---|
| Definition | `.content.xml` | `cq:Component` with title, group, superType |
| HTL Template | `{name}.html` | Sightly template with data-sly-use, data-sly-test |
| Touch UI Dialog | `_cq_dialog/.content.xml` | Coral UI 3 / Granite UI fields |
| Sling Model | `{Name}.java` | Java model with `@ValueMapValue` injection |
| CSS | `clientlib-{name}/css/{name}.css` | BEM naming, responsive, design tokens |
| JavaScript | `clientlib-{name}/js/{name}.js` | Only for interactive components |

---

### Step 6: Deploy & Test in AEM Local SDK

#### Setting Up AEM Local SDK

**1. Download AEM SDK:**

- For **AEM as a Cloud Service**: Download from [Adobe Software Distribution](https://experience.adobe.com/#/downloads/content/software-distribution/en/aemcloud.html)
- For **AEM 6.5**: Download the QuickStart JAR from Adobe licensing portal

**2. Set up the SDK directory:**

```bash
mkdir -p ~/aem-sdk
# Place the aem-sdk-quickstart-*.jar in this directory

# Set environment variable
export AEM_SDK_PATH=~/aem-sdk
```

**3. First-time setup — Start AEM author instance:**

```bash
cd ~/aem-sdk

# Start AEM author (first time takes several minutes)
java -Xmx2048m -jar aem-sdk-quickstart-*.jar \
  -p 4502 \
  -r author,nosamplecontent \
  -nointeractive

# AEM will unpack and start. Wait for:
# "Quickstart started" message in the console
```

**4. Access AEM:**
- Author: http://localhost:4502 (admin/admin)
- CRXDE Lite: http://localhost:4502/crx/de
- Package Manager: http://localhost:4502/crx/packmgr

#### Generate the AEM Maven Project First

Before deploying the generated components, scaffold the full Maven project:

```bash
# Generate AEM project from archetype
mvn -B org.apache.maven.plugins:maven-archetype-plugin:3.2.1:generate \
  -D archetypeGroupId=com.adobe.aem \
  -D archetypeArtifactId=aem-project-archetype \
  -D archetypeVersion=36 \
  -D appTitle="My Modernized Site" \
  -D appId="modernizedsite" \
  -D groupId="com.modernized" \
  -D artifactId="modernizedsite" \
  -D package="com.modernized" \
  -D aemVersion="6.5.7" \
  -D frontendModule="general" \
  -D includeExamples="n" \
  -D includeErrorHandler="y"
```

Or use the agent to show the exact command for your configuration:

```bash
python src/main.py show-archetype-cmd
```

#### Copy Generated Artifacts into Maven Project

```bash
# Copy generated components into the Maven project
cp -r output/aem-project/ui.apps/* modernizedsite/ui.apps/
cp -r output/aem-project/core/* modernizedsite/core/
cp -r output/aem-project/ui.content/* modernizedsite/ui.content/
```

#### Build and Deploy

```bash
# Option A: Use the agent CLI
python src/main.py deploy --project ./modernizedsite --validate

# Option B: Use Maven directly
cd modernizedsite
mvn clean install -PautoInstallSinglePackage -DskipTests
```

#### Check SDK Status

```bash
python src/main.py sdk-status
```

Output:
```
┌──────────────────────────┐
│     AEM SDK Status       │
├──────────┬───────┬───────┤
│ Instance │ Status│ URL   │
├──────────┼───────┼───────┤
│ Author   │ Running│ :4502│
│ Publish  │ Stopped│ :4503│
└──────────┴───────┴───────┘
```

#### Validate Deployment

After deploying, validate all components, templates, and content:

```bash
python src/main.py deploy --project ./modernizedsite --validate
```

The validator checks:
- AEM instance health
- OSGi bundle status (all bundles active)
- Each component exists at `/apps/{appId}/components/{name}`
- Each template exists and is enabled
- Content structure at `/content/{appId}`
- Client libraries are accessible

---

### Full Pipeline (All Steps)

Run the complete pipeline in one command:

```bash
python src/main.py run https://example.com \
  --output ./output \
  --figma-url https://www.figma.com/file/XXXXX/MyDesign \
  --max-pages 30
```

This runs Steps 1-5 sequentially. Then deploy manually:

```bash
python src/main.py deploy --project ./output/aem-project --validate
```

---

## Configuration Reference

### `config/agent_config.yaml`

| Section | Key | Default | Description |
|---|---|---|---|
| `llm.model` | — | `claude-sonnet-4-20250514` | Claude model for classification/generation |
| `source_analysis.crawler.max_pages` | — | `50` | Max pages to crawl |
| `source_analysis.crawler.max_depth` | — | `5` | Max crawl depth |
| `source_analysis.classification.min_confidence` | — | `0.7` | Min confidence for heuristic match |
| `aem.version` | — | `6.5.7` | Target AEM version |
| `aem.project.app_id` | — | `modernizedsite` | AEM app ID (used in paths) |
| `aem.project.group_id` | — | `com.modernized` | Maven group ID |
| `component_generation.htl.use_core_component_inheritance` | — | `true` | Use `sling:resourceSuperType` for extensions |
| `deployment.sdk.port_author` | — | `4502` | AEM author port |

### `config/component_mappings.yaml`

Defines how HTML patterns map to AEM Core Components. Each entry includes:
- `resource_type` — The `sling:resourceType`
- `patterns` — Tag names, CSS class patterns, and context clues
- `properties` — Expected JCR properties

---

## AEM Core Components Supported

| Component | Resource Type | Auto-Detected Patterns |
|---|---|---|
| Text | `core/wcm/components/text/v2/text` | `<p>`, `.text-block`, `.rich-text` |
| Title | `core/wcm/components/title/v3/title` | `<h1>`-`<h6>`, `.title`, `.heading` |
| Image | `core/wcm/components/image/v3/image` | `<img>`, `<picture>`, `.hero-image` |
| Button | `core/wcm/components/button/v2/button` | `<button>`, `.btn`, `.cta` |
| Teaser | `core/wcm/components/teaser/v2/teaser` | `.card`, `.teaser`, `.promo` |
| Navigation | `core/wcm/components/navigation/v2/navigation` | `<nav>`, `.navbar`, `.main-nav` |
| Breadcrumb | `core/wcm/components/breadcrumb/v3/breadcrumb` | `.breadcrumb`, `.breadcrumbs` |
| Accordion | `core/wcm/components/accordion/v1/accordion` | `.accordion`, `.faq`, `.collapse` |
| Tabs | `core/wcm/components/tabs/v1/tabs` | `.tabs`, `.tab-container` |
| Carousel | `core/wcm/components/carousel/v1/carousel` | `.carousel`, `.slider`, `.swiper` |
| List | `core/wcm/components/list/v3/list` | `<ul>`, `<ol>`, `.item-list` |
| Container | `core/wcm/components/container/v1/container` | `.container`, `.wrapper`, `<section>` |
| Separator | `core/wcm/components/separator/v1/separator` | `<hr>`, `.divider` |
| Embed | `core/wcm/components/embed/v2/embed` | `<iframe>`, `<video>`, `.embed` |
| Experience Fragment | `core/wcm/components/experiencefragment/v2/experiencefragment` | Shared header/footer |
| Search | `core/wcm/components/search/v1/search` | `.search-form`, `.search-bar` |
| Download | `core/wcm/components/download/v2/download` | `.file-download` |
| Language Nav | `core/wcm/components/languagenavigation/v2/languagenavigation` | `.language-selector` |

---

## Project Structure

```
agent/
├── README.md                          # This file
├── requirements.txt                   # Python dependencies
├── setup.py                           # Package setup
├── .env.example                       # Environment template
├── config/
│   ├── agent_config.yaml              # Main configuration
│   └── component_mappings.yaml        # AEM Core Component patterns
├── src/
│   ├── main.py                        # CLI entry point & orchestrator
│   ├── source_analysis/               # Step 1
│   │   ├── crawler.py                 # Site crawler (respects robots.txt)
│   │   ├── dom_decomposer.py          # HTML-to-sections decomposition
│   │   ├── component_classifier.py    # Heuristic + LLM classification
│   │   └── inventory.py               # Component inventory builder
│   ├── figma_pipeline/                # Step 2
│   │   ├── figma_mcp_client.py        # Figma MCP server integration
│   │   ├── design_parser.py           # Design token extraction
│   │   └── aem_mapper.py              # Figma-to-AEM component mapper
│   ├── component_generator/           # Steps 3-4
│   │   ├── htl_generator.py           # HTL (Sightly) templates
│   │   ├── dialog_generator.py        # Touch UI dialog XML
│   │   ├── model_generator.py         # Sling Model Java classes
│   │   ├── clientlib_generator.py     # Client libraries (CSS/JS)
│   │   └── templates/                 # Jinja2 code templates
│   ├── template_assembler/            # Step 5
│   │   ├── page_template_builder.py   # Editable page templates
│   │   ├── policy_generator.py        # Policies & Style System
│   │   └── content_structure.py       # Site content tree
│   ├── content_migrator/              # Step 5 (Content)
│   │   ├── content_extractor.py       # Extract text, images, metadata
│   │   ├── content_transformer.py     # Transform to JCR node structure
│   │   └── package_builder.py         # Build CRX .zip packages
│   ├── deployment/                    # Step 6
│   │   ├── sdk_manager.py             # AEM SDK lifecycle management
│   │   ├── deployer.py                # Maven & package deployment
│   │   └── validator.py               # Post-deployment validation
│   └── utils/
│       ├── llm_client.py              # Claude API integration
│       └── aem_utils.py               # AEM-specific utilities
├── templates/                         # Reference component templates
└── tests/                             # Unit tests
```

---

## Troubleshooting

| Issue | Solution |
|---|---|
| `ANTHROPIC_API_KEY not set` | Set in `.env` or export as environment variable |
| `Figma MCP connection refused` | Start the MCP server: `npx figma-developer-mcp` |
| `Maven build fails` | Ensure Java 11 and Maven 3.3.9+ are installed |
| `AEM not starting` | Check Java version (`java -version`), ensure port 4502 is free |
| `Bundles not active after deploy` | Check AEM Web Console: http://localhost:4502/system/console/bundles |
| `Component not showing in editor` | Verify the component group is added to the template policy |

---

## License

This project extends the [AEM Project Archetype](https://github.com/adobe/aem-project-archetype) which is licensed under the Apache License, Version 2.0.
