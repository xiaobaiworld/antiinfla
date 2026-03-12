# Image And Source Workflow

## Purpose

Define the internal workflow for:

- planning public images
- tracking evidence and source notes
- keeping research inputs separate from public page output

This workflow is internal-only.

## Scope

Use this workflow for all live and future food pages.

Public pages should only expose:

- finished copy
- finished images
- alt text

They should not expose:

- raw source notes
- research snippets
- image licensing notes
- internal planning comments

## Image Workflow

### Storage roles

- public-facing image assets belong in the future public asset path
- raw research or candidate files should stay in internal folders only
- planning metadata should live in `data/live-image-manifest.json`

### Required image fields

- `slug`
- `page_type`
- `hero_image_needed`
- `hero_subject`
- `alt_text_draft`
- `source_status`
- `processed_status`
- `public_asset_status`

### Naming rules

- use the food slug in image filenames
- keep filenames lowercase and hyphenated
- prefer one clear hero image per food page first

## Source And Evidence Workflow

### Storage roles

- planning metadata should live in `data/live-source-manifest.json`
- detailed notes can later live under `workspace/research/`

### Required source fields

- `slug`
- `page_type`
- `nutrition_source_status`
- `compound_source_status`
- `usage_source_status`
- `copy_review_status`
- `evidence_note_status`

### Review rule

Public copy should only use cautious wording until evidence notes are properly reviewed.

## Current Status Model

### Image statuses

- `needed`
- `collecting`
- `ready-for-processing`
- `processed`
- `published`

### Source statuses

- `placeholder`
- `collecting`
- `reviewed`

## Workflow Sequence

1. create or update the planning entry in both manifests
2. collect image candidates and source notes internally
3. refine alt text draft and evidence framing
4. update the public page only when materials are ready

## Current Constraint

The current site uses CSS-based placeholder visuals for food hero areas.

That is acceptable during early production, but future batches should move toward real images tracked through this workflow.
