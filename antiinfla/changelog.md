# Changelog

## Unreleased

- Completed Step 1: planning and execution framework.
- Added `development-plan.md` as the master roadmap for content, tooling, SEO, and LLM discoverability.
- Initialized `changelog.md` for step-based delivery tracking.
- Completed Step 2: information architecture.
- Added `docs/site-architecture.md` to define page families, URL rules, slug rules, page template rules, and internal linking rules.
- Added `data/foods-inventory.json` with the first 30 foods, category mapping, priorities, related foods, and guide targets.
- Completed Step 3: structured content inventory.
- Expanded `data/foods-inventory.json` into a production-ready planning dataset with search intents, summary angles, nutrient focus, evidence placeholders, image plans, and production batches.
- Added `docs/content-inventory-model.md` to define the inventory field model and the first recommended production batch.
- Completed Step 4: local content generation helpers.
- Added `scripts/generate_food_drafts.py` to generate internal draft scaffolds for the first production batch from structured inventory data.
- Added `docs/generation-workflow.md` to document how internal data becomes non-public draft output.
- Added `docs/site-operations-sop.md` to define the long-term workflow for new pages, page updates, QA, SEO/AEO/GEO checks, and release logging.
- Linked the SOP into the development and generation workflow docs.
- Completed Step 5: reusable public food page template and SOP alignment.
- Reworked `index.html` into a real anti-inflammatory content homepage entry point.
- Added `foods/blueberries/index.html` as the first representative public food page using the shared structure.
- Expanded `styles.css` with reusable homepage and food-page template styles.
- Completed Step 6: first public batch and crawlable site files.
- Added the remaining first-batch public food pages for Broccoli, Salmon, Olive Oil, Turmeric, Green Tea, Chia Seeds, and Oats.
- Expanded homepage navigation so all live batch pages are linked from the public entry point.
- Added `sitemap.xml` and `robots.txt` for the current public page set.
- Advanced `next.md` to Step 7: category hubs and first guide layer.
- Marked multilingual support as a deferred V2+ requirement in the roadmap, architecture notes, SOP, and current next-step notes.
- Completed Step 7: category hubs and first guide layer.
- Added category hub pages for fruits, vegetables, spices and herbs, nuts and seeds, whole grains and legumes, healthy fats, fish and seafood, and drinks.
- Added the first public guide page: `guides/best-anti-inflammatory-foods/`.
- Connected homepage, food pages, category hubs, and the guide layer through internal links.
- Updated `sitemap.xml` to include the new real public hub and guide pages.
- Advanced `next.md` to Step 8: metadata and structured SEO hardening.
