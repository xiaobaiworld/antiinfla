# Site Information Architecture

## Purpose

Define a stable structure for a lean anti-inflammatory content site so new pages can be added without redesigning the website each time.

This document is for internal planning only.

## Public Page Families

The public website should use four page families.

### 1. Homepage

Purpose:

- explain the site focus
- route users to major content clusters
- surface a small set of featured foods and guides

Recommended URL:

- `/`

### 2. Food Detail Pages

Purpose:

- target one food entity per page
- provide a direct answer for SEO, AEO, and GEO
- serve as the main scalable page type

Recommended URL pattern:

- `/foods/{slug}/`

Examples:

- `/foods/blueberries/`
- `/foods/turmeric/`
- `/foods/salmon/`

### 3. Category Hub Pages

Purpose:

- group related food pages
- strengthen internal linking
- target broader category queries

Recommended URL pattern:

- `/foods/category/{slug}/`

Examples:

- `/foods/category/fruits/`
- `/foods/category/vegetables/`
- `/foods/category/spices-herbs/`

### 4. Supporting Guide Pages

Purpose:

- target broader search intent and comparison-style queries
- link into food pages and hubs

Recommended URL pattern:

- `/guides/{slug}/`

Examples:

- `/guides/best-anti-inflammatory-foods/`
- `/guides/anti-inflammatory-breakfast-ideas/`

## Controlled Scope

The site should not add extra public page types unless a real need appears.

Avoid adding:

- tag archives with weak differentiation
- search result pages as public landing pages
- duplicate “benefits” microsites for each food
- public tool pages unless they clearly improve user value

## URL Rules

### General Rules

- use lowercase only
- use hyphen-separated slugs
- avoid dates in URLs
- avoid category names in food slugs
- avoid file extensions in public URLs
- prefer short descriptive paths

### Food Page URLs

Pattern:

- `/foods/{slug}/`

Rule:

- use the singular common food name as the canonical slug when natural

Examples:

- `blueberries`
- `strawberry`
- `olive-oil`
- `chia-seeds`

### Category Page URLs

Pattern:

- `/foods/category/{slug}/`

Allowed initial category slugs:

- `fruits`
- `vegetables`
- `spices-herbs`
- `nuts-seeds`
- `legumes-whole-grains`
- `healthy-fats`
- `fish-seafood`
- `drinks`

### Guide Page URLs

Pattern:

- `/guides/{slug}/`

Rule:

- use search-oriented descriptive slugs

Examples:

- `best-anti-inflammatory-foods`
- `anti-inflammatory-foods-by-category`
- `how-to-start-an-anti-inflammatory-diet`

## Slug Rules

### Food Slug Standard

- use the primary English display name
- convert spaces to hyphens
- remove punctuation unless required for readability
- prefer the common food name over scientific wording

### Display Name vs Slug

Display names can stay natural while slugs remain normalized.

Examples:

- `Blueberries` -> `blueberries`
- `Sweet Potato` -> `sweet-potato`
- `Green Tea` -> `green-tea`

### Future Alias Handling

If a food has synonyms, keep one canonical slug and store aliases in data.

Examples:

- `garbanzo beans` should resolve to `chickpeas`
- `bilberries` should not create a duplicate page unless content is truly different

## Page Template Rules

Each food detail page should use the same structural order.

### Required layout blocks

1. H1
2. one-sentence summary
3. quick answer box
4. what it is
5. anti-inflammatory relevance
6. key nutrients or compounds
7. possible health benefits
8. how to eat
9. shopping and storage
10. FAQ
11. related foods
12. evidence note

### Why this matters

- easier to scale
- easier for search engines to parse
- easier for large models to extract and compare
- easier to generate from structured data later

## Internal Linking Model

### Homepage linking rules

The homepage should link to:

- all major category hubs
- a selected set of featured food pages
- a selected set of guide pages

### Category hub linking rules

Each category hub should link to:

- all food pages in that category
- 2 to 4 related guides
- adjacent category hubs where relevant

### Food page linking rules

Each food page should link to:

- its primary category hub
- 3 to 6 related food pages
- 1 to 3 relevant guides

### Guide page linking rules

Each guide page should link to:

- the key food pages it references
- relevant category hubs
- other supporting guides when useful

## Entity Model

Each food should have a stable primary category and optional secondary traits.

### Primary categories

- fruits
- vegetables
- spices-herbs
- nuts-seeds
- legumes-whole-grains
- healthy-fats
- fish-seafood
- drinks

### Secondary traits examples

- antioxidant-rich
- omega-3-rich
- fiber-rich
- polyphenol-rich
- meal-friendly
- snack-friendly

These traits are useful for future guides and internal generation, but they should not create uncontrolled page sprawl at the start.

## Content Scaling Rules

To keep the site manageable:

- every new page must fit an existing page family
- every food must map to one primary category
- every page must fit a known internal-linking pattern
- every page must have a clear target query or entity

## Sitemap Policy

The sitemap should include:

- homepage
- all public category hubs
- all public food pages
- all public guides

The sitemap should not include:

- internal planning files
- internal tools
- draft pages
- incomplete placeholder pages

## Step 2 Deliverables

This document defines:

- public page families
- URL patterns
- slug rules
- page template rules
- internal linking rules
- category model
