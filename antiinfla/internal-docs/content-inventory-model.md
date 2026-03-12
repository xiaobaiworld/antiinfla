# Content Inventory Model

## Purpose

Turn the food list into a reusable internal production dataset.

This model is designed to support:

- page planning
- future generation scripts
- source collection
- image collection
- phased release management

## Field Definitions

### Core identity

- `name`: public display name
- `slug`: canonical URL slug
- `page_type`: currently `food-detail`
- `primary_category`: single required main category
- `secondary_traits`: reusable traits for filters, guides, and comparisons

### Planning and release

- `status`: current production status
- `priority`: relative production priority
- `production_batch`: small-batch release grouping

### Search and content direction

- `search_intents`: primary query patterns the page should answer
- `summary_angle`: the main framing for the intro and top summary
- `key_nutrients_focus`: nutrients or compounds to emphasize
- `content_focus`: which recurring page sections deserve emphasis

### Evidence workflow

- `evidence_status`: whether evidence notes are only placeholders or already reviewed
- `source_placeholders`: source buckets to fill during research

Recommended source buckets:

- `nutrition-profile`
- `fat-profile`
- `compound-profile`
- `polyphenols`
- `anti-inflammatory-compounds`
- `leafy-green-benefits`
- `whole-grain-benefits`
- `legume-benefits`
- `practical-usage`
- `cooking-usage`

### Image workflow

- `image_plan.status`: image sourcing state
- `image_plan.hero_subject`: what the hero image should depict
- `image_plan.alt_draft`: first-pass alt text

### Linking and expansion

- `related_foods`: detail pages to cross-link from the page
- `guide_targets`: supporting guides where the page should appear

## First Production Batch

The first batch should favor foods that meet at least one of these conditions:

- high recognition
- strong anti-inflammatory search intent
- broad category coverage
- easy-to-explain everyday use

Current recommended batch 1:

- Blueberries
- Broccoli
- Salmon
- Olive Oil
- Turmeric
- Green Tea
- Chia Seeds
- Oats

## Why This Batch Works

- covers fruits, vegetables, fish, healthy fats, spices, drinks, seeds, and grains
- includes several of the strongest head terms
- creates a realistic first cluster for internal linking
- gives the homepage and future guide pages enough variety

## Editorial Warning

Do not treat structured planning fields as final medical claims.

The dataset is a planning scaffold.

All public health-related wording still needs evidence review and careful phrasing.
