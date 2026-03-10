# Generation Workflow

## Purpose

Describe how internal planning data becomes reusable draft content without exposing tooling on the public site.

## Current Generator

Script:

- `scripts/generate_food_drafts.py`

Input:

- `data/foods-inventory.json`

Output:

- `workspace/generated/food-drafts/*.md`
- `workspace/generated/batch-1-manifest.json`

## What The Script Does

For the current `first_production_batch`, the script generates:

- one internal markdown scaffold per food
- frontmatter-like metadata block
- section prompts for the final page structure
- evidence and image placeholders
- a batch manifest for quick verification

## Why This Approach Fits The Project

- keeps tooling internal
- avoids manual copy-paste
- preserves a clean public site
- creates a stable handoff between data modeling and page implementation

## Intended Next Use

The generated drafts are not public pages.

They are intermediate materials for the next step:

- build the reusable public food page template
- translate scaffold content into actual HTML pages
- keep the source-of-truth in structured data

## Run Command

```bash
python3 scripts/generate_food_drafts.py
```

## Output Policy

Generated files should remain under internal folders such as `workspace/`.

They should not be linked from public HTML and should not be included in the public sitemap.
