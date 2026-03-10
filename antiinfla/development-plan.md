# Anti-Inflammatory Content Site Development Plan

## Goal

Build a lean, static, content-first website focused on anti-inflammatory food information.

The public website should remain clean:

- only content pages, category pages, and required SEO files are published
- internal helper tools must stay inside the project and must not be exposed on the website
- each delivery step must be small, testable, and easy to commit independently

## Product Positioning

This is not a large platform.

It is a focused reference site that does three things well:

1. publish clear food and topic pages around anti-inflammatory diet information
2. make those pages easy for search engines to index and rank
3. make those pages easy for large models to discover, parse, quote, and recommend

## Working Principles

- Prefer static pages over complex systems
- Prefer repeatable templates over one-off writing
- Prefer internal scripts and local tooling over manual copy-paste
- Prefer verifiable source collection over vague health claims
- Prefer gradual release in small batches over big launches

## Scope

### Public website

- homepage
- food detail pages
- category and hub pages
- supporting guides
- image assets used by public pages
- sitemap, robots, metadata, structured data

### Internal-only project tooling

- content inventory builder
- page brief generator
- frontmatter and metadata helpers
- image sourcing and image manifest helpers
- internal QA and link-check helpers
- page generation scripts

These tools should live in local folders such as `scripts/`, `tools/`, `data/`, or `workspace/`.

## Content Strategy

### Initial page families

1. food detail pages
2. category hubs
3. supporting guides
4. glossary and method pages

### Recommended first 30 food pages

- Blueberries
- Strawberry
- Pomegranate
- Avocado
- Cherry
- Broccoli
- Spinach
- Kale
- Tomato
- Sweet Potato
- Turmeric
- Ginger
- Garlic
- Cinnamon
- Basil
- Rosemary
- Walnut
- Almond
- Chia Seeds
- Flax Seeds
- Lentils
- Chickpeas
- Oats
- Quinoa
- Olive Oil
- Avocado Oil
- Salmon
- Sardines
- Green Tea
- Matcha

### Supporting category hubs to add early

- Anti-Inflammatory Fruits
- Anti-Inflammatory Vegetables
- Anti-Inflammatory Spices and Herbs
- Anti-Inflammatory Nuts and Seeds
- Anti-Inflammatory Legumes and Whole Grains
- Anti-Inflammatory Healthy Fats
- Anti-Inflammatory Fish and Seafood
- Anti-Inflammatory Drinks

### Supporting guides to add after the first food batch

- Best Anti-Inflammatory Foods
- Anti-Inflammatory Breakfast Ideas
- Anti-Inflammatory Snacks
- Anti-Inflammatory Drinks
- How to Start an Anti-Inflammatory Diet
- Anti-Inflammatory Grocery List
- Anti-Inflammatory Foods by Category
- Foods That May Increase Inflammation

## Page Template Standard

Each food page should follow one stable structure.

### Required sections

1. Food Name
2. Hero Image
3. Short Description
4. Anti-Inflammatory Properties
5. Nutrition Facts
6. Health Benefits
7. How to Eat
8. Related Foods

### Additional sections worth adding

- Taste and texture
- Shopping and storage tips
- Simple serving ideas
- FAQ
- Key takeaways
- References or evidence notes

## SEO and LLM Discoverability Strategy

### Search engine goals

- strong page titles and meta descriptions
- clear URL structure
- stable internal linking
- category hubs that point to detail pages
- structured data where appropriate
- image alt text and image context
- sitemap and robots correctly maintained

### Large model discoverability goals

- plain factual writing
- stable headings and repeated template structure
- concise summary blocks near the top
- explicit entity naming
- lightweight pages with low visual noise around key facts
- references or evidence notes for sensitive health claims
- clear related-page network for retrieval and browsing

### Important caution

The site should avoid overstating medical claims.

Bad direction:

- claiming treatment outcomes without support
- writing vague wellness promises
- publishing pages with thin content and no distinguishing structure

Better direction:

- describe nutrients and researched anti-inflammatory relevance carefully
- keep language informational, not diagnostic
- add short evidence framing where needed

## Image Strategy

### Public-facing image rules

- one clean hero image per food page at minimum
- descriptive filename
- descriptive alt text
- compressed output
- consistent aspect ratio policy

### Internal workflow

- keep source tracking in a local manifest
- record image source, license, author, local path, processed path, alt text draft
- do not expose internal sourcing notes on the public page

## Internal Tooling Plan

### Tools to build

1. content inventory tool
2. page brief generator
3. page scaffold generator
4. image manifest generator
5. metadata and schema helper
6. internal QA checker

### Suggested local structure

- `scripts/` for automation scripts
- `tools/` for reusable helper modules
- `data/` for content inventory, manifests, and page definitions
- `workspace/` for drafts and temporary analysis files
- `content/` for structured page source files if we later move beyond raw HTML

## Delivery Workflow

Every implementation cycle should follow the same order.

1. write the current actionable step into `next.md`
2. implement only that step
3. verify the result
4. commit to git
5. write the completed work into `changelog.md`
6. clear and rewrite `next.md` for the next step

## Planned Steps

### Step 1

Set up the planning and execution framework.

- write the full development plan
- initialize `next.md`
- initialize `changelog.md`
- define the local-only tooling direction

### Step 2

Define the information architecture.

- homepage role
- food page URL pattern
- hub page URL pattern
- guide page URL pattern
- internal link rules
- slug conventions

### Step 3

Create the structured content inventory.

- build a data file for the first 30 foods
- add page status tracking
- add category mapping
- add priority and evidence notes

### Step 4

Build local content generation helpers.

- generate page skeletons from the food inventory
- generate metadata drafts
- generate related-food suggestions

### Step 5

Design and implement the reusable food page template.

- stable HTML structure
- reusable CSS patterns
- clear summary and section hierarchy

### Step 6

Create the first batch of food pages.

- start with 5 to 10 highest-priority foods
- ensure every page has complete core sections

### Step 7

Create category hubs and strengthen internal linking.

- category landing pages
- related food loops
- homepage to hub to detail structure

### Step 8

Build image sourcing and manifest workflow.

- manifest format
- naming rules
- alt text rules
- local processing notes

### Step 9

Add SEO infrastructure.

- sitemap
- robots
- canonical tags
- social metadata
- structured data strategy

### Step 10

Add LLM-friendly content improvements.

- summary blocks
- FAQ structure
- consistent factual sections
- entity-first headings

### Step 11

Create supporting guides.

- best foods
- grocery list
- breakfast ideas
- snacks
- drinks

### Step 12

Run QA and release management.

- link checks
- image checks
- metadata review
- content consistency review
- sitemap refresh

## Verification Rules

Each step must have acceptance criteria before it is considered done.

Examples:

- files created in the expected paths
- generated slugs are consistent
- public pages render without broken links
- sitemap contains only real public pages
- image manifests include required fields
- content pages follow the agreed template

## Current Recommendation

Do not start by writing all 30 pages manually.

That would be slow and inconsistent.

First define the structure and tooling so page creation becomes repeatable.
