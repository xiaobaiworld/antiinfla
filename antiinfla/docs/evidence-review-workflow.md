# Evidence Review Workflow

## Purpose

Define how public health-adjacent food pages should be strengthened without drifting into overclaiming.

This workflow is for content-quality upgrades on already live pages.

## Evidence Framing Rules

Use a food-first standard.

- describe foods as part of an eating pattern
- describe compounds and nutrients as context, not proof of treatment
- prefer "may support" or "is commonly included" over direct outcome claims
- avoid implying that one food can diagnose, treat, cure, or prevent disease by itself

## Review Tiers

### Tier 1: Nutrition grounding

Confirm that the page only names broadly established nutrients or compounds for that food.

Examples:

- fiber
- vitamin C
- omega-3 fats
- polyphenols

### Tier 2: Practical use grounding

Confirm that "how to eat" and shopping advice stay practical and non-medical.

Examples:

- fresh, frozen, roasted, brewed, baked
- storage, routine use, meal combinations

### Tier 3: Evidence note grounding

Confirm that the evidence note tells readers what the page is and is not claiming.

Good signals:

- this page is informational
- evidence varies by nutrient, food matrix, and overall dietary pattern
- the page does not treat the food as a standalone solution

## FAQ Upgrade Standard

When revising FAQ blocks:

- prefer real user-intent questions over filler
- include at least one practical question
- include at least one caution or framing question where useful
- keep answers short and extractable

## Manifest Update Rule

When a live page receives a real evidence-strengthening pass:

1. update `data/live-source-manifest.json`
2. move reviewed fields beyond `placeholder`
3. add review notes or source-family targets when helpful

## Selected Batch Strategy

During this step, prioritize pages that anchor major site intents:

- berries and fruit
- fish and seafood
- healthy fats
- drinks
- spices
- breakfast staples

## Current Constraint

This workflow improves factual framing and source tracking.

It does not replace future source collection with primary references, and it does not authorize stronger medical claims.
