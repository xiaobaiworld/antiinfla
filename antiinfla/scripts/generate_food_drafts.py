#!/usr/bin/env python3

import argparse
import json
from pathlib import Path


def load_inventory(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_frontmatter(food: dict) -> str:
    lines = [
        "---",
        f'title: "{food["name"]}"',
        f'slug: "{food["slug"]}"',
        f'category: "{food["primary_category"]}"',
        f'priority: {food["priority"]}',
        f'production_batch: {food["production_batch"]}',
        "search_intents:",
    ]
    lines.extend(f'  - "{item}"' for item in food["search_intents"])
    lines.append("key_nutrients_focus:")
    lines.extend(f'  - "{item}"' for item in food["key_nutrients_focus"])
    lines.append("content_focus:")
    lines.extend(f'  - "{item}"' for item in food["content_focus"])
    lines.append("related_foods:")
    lines.extend(f'  - "{item}"' for item in food["related_foods"])
    lines.append("guide_targets:")
    lines.extend(f'  - "{item}"' for item in food["guide_targets"])
    lines.append("---")
    return "\n".join(lines)


def build_markdown(food: dict) -> str:
    related = ", ".join(food["related_foods"])
    guides = ", ".join(food["guide_targets"])
    nutrients = ", ".join(food["key_nutrients_focus"])
    source_buckets = ", ".join(food["source_placeholders"])
    faq_seeds = "\n".join(f"- {item}" for item in food["search_intents"])

    body = f"""{build_frontmatter(food)}

# {food["name"]}

Internal draft scaffold generated from structured inventory.
This file is not a public page.

## Summary Angle

{food["summary_angle"]}

## Quick Answer

Draft a 2-4 sentence answer for:
- what this food is
- whether it fits an anti-inflammatory diet
- the most relevant practical use case

## What It Is

Draft notes:
- category: {food["primary_category"]}
- traits: {", ".join(food["secondary_traits"])}

## Anti-Inflammatory Relevance

Focus points:
- explain the likely anti-inflammatory relevance carefully
- avoid treatment language
- connect the explanation to food compounds or dietary pattern context

## Key Nutrients Or Compounds

Priority nutrients or compounds:
- {nutrients}

## Potential Health Benefits

Draft notes:
- keep wording informational
- align claims to evidence quality

## How To Eat

Angle cues:
- primary intent: {", ".join(food["content_focus"])}
- likely related guides: {guides}

## Shopping And Storage

Draft simple buying and storage guidance.

## FAQ

Use search intent as FAQ seeds:
{faq_seeds}

## Image Plan

- status: {food["image_plan"]["status"]}
- hero subject: {food["image_plan"]["hero_subject"]}
- alt draft: {food["image_plan"]["alt_draft"]}

## Evidence Notes

- evidence status: {food["evidence_status"]}
- source buckets to fill: {source_buckets}

## Internal Linking

- related foods: {related}
- guide targets: {guides}
"""
    return body


def build_manifest(foods: list[dict]) -> dict:
    return {
        "count": len(foods),
        "slugs": [food["slug"] for food in foods],
        "categories": sorted({food["primary_category"] for food in foods}),
    }


def write_outputs(inventory: dict, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    drafts_dir = output_dir / "food-drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)

    batch_slugs = set(inventory["first_production_batch"])
    foods = [food for food in inventory["foods"] if food["slug"] in batch_slugs]
    foods.sort(key=lambda item: (item["production_batch"], item["priority"], item["slug"]))

    written: list[Path] = []
    for food in foods:
        path = drafts_dir / f'{food["slug"]}.md'
        path.write_text(build_markdown(food), encoding="utf-8")
        written.append(path)

    manifest_path = output_dir / "batch-1-manifest.json"
    manifest = build_manifest(foods)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    written.append(manifest_path)

    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate internal food draft scaffolds.")
    parser.add_argument(
        "--inventory",
        default="data/foods-inventory.json",
        help="Path to the food inventory JSON file.",
    )
    parser.add_argument(
        "--output-dir",
        default="workspace/generated",
        help="Directory for internal generated draft outputs.",
    )
    args = parser.parse_args()

    inventory = load_inventory(Path(args.inventory))
    written = write_outputs(inventory, Path(args.output_dir))

    print(f"Generated {len(written)} files")
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
