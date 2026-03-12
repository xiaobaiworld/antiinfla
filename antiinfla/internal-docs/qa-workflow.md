# QA Workflow

## Purpose

Define a repeatable release check for the public site.

## Current QA Scope

The current local QA run should check:

- every public HTML page in the repo
- canonical tag presence
- sitemap coverage
- robots file presence
- basic public page counts by type

## Current Command

```bash
python3 scripts/validate_public_site.py
```

## When To Run

- before each public-content commit
- after sitemap updates
- after category hub or guide changes
- after large food-page batches

## Current Limitation

This is a structural QA pass, not a content-truth or medical-review pass.

Evidence review and content quality still require editorial judgment.
