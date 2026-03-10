#!/usr/bin/env python3

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BASE = "https://www.antiinflammatorydiets.com"


def collect_public_pages() -> list[Path]:
    pages = [ROOT / "index.html"]
    pages.extend(sorted((ROOT / "foods").glob("*/index.html")))
    pages.extend(sorted((ROOT / "foods/category").glob("*/index.html")))
    pages.extend(sorted((ROOT / "guides").glob("*/index.html")))
    return pages


def expected_url(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    if rel == "index.html":
        return f"{BASE}/"
    if rel.endswith("/index.html"):
        clean = rel[: -len("index.html")]
        return f"{BASE}/{clean}"
    raise ValueError(f"Unexpected public path: {path}")


def extract_canonical(text: str) -> str | None:
    match = re.search(r'<link rel="canonical" href="([^"]+)"', text)
    return match.group(1) if match else None


def main() -> int:
    pages = collect_public_pages()
    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    robots_exists = (ROOT / "robots.txt").exists()

    issues: list[str] = []

    for page in pages:
        text = page.read_text(encoding="utf-8")
        canonical = extract_canonical(text)
        expected = expected_url(page)
        if canonical != expected:
            issues.append(f"canonical mismatch: {page} -> {canonical} != {expected}")
        if expected not in sitemap:
            issues.append(f"sitemap missing URL: {expected}")

    if not robots_exists:
        issues.append("robots.txt is missing")

    print(f"public_pages={len(pages)}")
    print(f"sitemap_urls={sitemap.count('<loc>')}")
    print(f"robots_present={robots_exists}")

    if issues:
        print("issues:")
        for issue in issues:
            print(issue)
        return 1

    print("status=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
