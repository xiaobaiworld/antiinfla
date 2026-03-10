# Site Operations SOP

## Purpose

Define one operating procedure that covers both current development and future maintenance.

This SOP is intended to keep three things aligned:

- internal planning
- public site implementation
- later content updates and site maintenance

## Core Rule

Every site change must follow the same chain:

1. identify the change
2. record the change in `next.md`
3. update the relevant internal data or planning file first
4. implement the public or internal change
5. verify the result
6. commit to git
7. write the completed change into `changelog.md`
8. reset `next.md` to the next actionable step

## Change Types

There are four main types of work.

### 1. New page creation

Examples:

- new food page
- new category hub
- new guide page

### 2. Existing page update

Examples:

- revise wording
- improve structure
- add FAQ
- replace image
- improve metadata

### 3. Sitewide structural update

Examples:

- change template
- change CSS system
- change header or footer
- change internal linking patterns
- update sitemap or robots

### 4. Internal tooling update

Examples:

- improve generator scripts
- improve data model
- improve QA checks
- improve image workflow

## Standard Workflow For New Food Pages

Use this when adding a new food page.

### Phase A: Planning

1. confirm the food belongs in the site scope
2. confirm or create the canonical slug
3. assign the primary category
4. update `data/foods-inventory.json`
5. assign search intents, content focus, and production batch

### Phase B: Draft generation

1. run the internal generator if applicable
2. review the generated draft in `workspace/generated/`
3. fill research gaps for nutrients, usage, and evidence notes
4. decide whether the page is ready for public implementation

### Phase C: Public implementation

1. create the public page using the agreed template
2. add metadata and heading structure
3. add image and alt text
4. add related foods and guide links
5. add the page to the correct hub and internal links

### Phase D: Verification

1. verify URL and slug consistency
2. verify page structure matches the template
3. verify title, description, canonical, and internal links
4. verify image path and alt text
5. add the page to sitemap when it is truly public

### Phase E: Release log

1. commit the change
2. add a concise log entry to `changelog.md`
3. set the next task in `next.md`

## Standard Workflow For Existing Page Updates

Use this when a page already exists and needs revision.

### Phase A: Diagnose the reason for change

Possible reasons:

- content accuracy issue
- SEO weakness
- AEO or GEO weakness
- weak structure
- image issue
- broken links
- design inconsistency

### Phase B: Record scope before editing

Write the update goal in `next.md`.

Examples:

- strengthen the top summary
- improve FAQ quality
- reduce vague medical language
- improve related-link placement

### Phase C: Make the smallest effective change

Prefer targeted updates over unnecessary rewrites.

Good examples:

- improve the first screen summary
- replace thin FAQ questions with real query-aligned questions
- tighten evidence wording
- add missing category links

Bad examples:

- rewrite the whole page without a clear reason
- change URL structure casually
- add sections that break the common template

### Phase D: Re-verify page quality

Check:

- the page still matches the common structure
- internal links still work
- metadata still matches the page content
- the page still serves its main intent

### Phase E: Release log

1. commit
2. update `changelog.md`
3. define the next task in `next.md`

## Standard Workflow For Guide Pages

Use this when creating or updating supporting guides.

### Required checks

- the guide has a clear target query
- the guide is not duplicating a food page
- the guide links to real food pages
- the guide adds comparison, summary, or categorization value

Guide pages should not be thin listicles with no structure.

Each guide should usually include:

- summary block
- clear section hierarchy
- links to food pages
- category-level framing
- practical takeaways

## Standard Workflow For Category Hubs

Use this when creating or updating category hubs.

Category hubs should do three things:

1. explain the category briefly
2. list the included food pages clearly
3. route users into related guides

A category page should not exist unless it has enough child pages or strong planning value.

## SEO, AEO, And GEO Checkpoints

These checks apply before publishing or revising public pages.

### SEO checkpoints

- one clear target topic per page
- descriptive title and meta description
- stable URL and slug
- strong internal links
- inclusion in sitemap only when the page is ready

### AEO checkpoints

- direct summary near the top
- question-answer phrasing where useful
- FAQ based on real user intent
- concise and extractable answers

### GEO checkpoints

- stable headings
- explicit entity naming
- factual and comparable structure
- low ambiguity in the top sections
- clear related-page graph

## Public Quality Checklist

Before a page is treated as complete, confirm:

- the page uses the approved structure
- the copy is factual and not overstated
- the image is relevant and clean
- alt text is descriptive
- related links are present
- the page fits a hub and guide network
- the page can be understood quickly by both users and machines

## Internal Tooling Checklist

When changing internal tools, confirm:

- no tooling leaks into the public site
- generated outputs stay under internal folders
- the generator still reads current data correctly
- generated drafts remain aligned with the public template

## Maintenance Rhythm

After the site is live, maintenance should run in repeating cycles.

### Weekly or batch-level work

- add or revise one small batch of pages
- improve internal links
- review thin sections
- update `next.md` and `changelog.md`

### Monthly or milestone work

- review sitemap completeness
- review category coverage
- review duplicated or overlapping intent
- review whether guides need expansion
- review whether older pages need content refresh

## File Mapping

This is the working map for the SOP.

- `next.md`: current active task only
- `changelog.md`: completed step log
- `development-plan.md`: long-term roadmap
- `docs/site-architecture.md`: public structure rules
- `docs/content-inventory-model.md`: internal content model rules
- `docs/generation-workflow.md`: generator workflow
- `data/foods-inventory.json`: page planning source data
- `workspace/generated/`: internal draft outputs

## Important Constraint

Do not skip the internal data layer.

If a page is added or changed publicly, the internal source of truth should also be updated when relevant.

Otherwise the workflow will drift and future maintenance will become inconsistent.
