# llmcli — CLI Tool Navigator

A navigation website that catalogs command-line tools in two categories:
1. **Traditional software** that exposes CLI interfaces (or wrappers that add CLI to GUI-only apps)
2. **AI/LLM tools** packaged as CLI tools, ready for agent invocation

The core insight: as AI agents take over more workflows, tools need CLI interfaces to be usable. This site helps developers and AI engineers discover what's already available — so they don't rebuild what exists.

---

## Project Analysis

### Why this is worth building

- **AI agents need CLI interfaces.** LLMs can't click buttons. Every tool without a CLI is a wall for agents. There's no good directory of "what's agent-usable."
- **MCP server ecosystem is exploding but undiscoverable.** Hundreds of MCP servers exist; no curated, quality-filtered directory exists yet.
- **Developers ask "is there a CLI for X?" constantly.** Current resources (awesome-cli-apps, tldr.sh) are static lists with no quality signals and no AI angle.
- **Two audiences, one product.** Traditional devs looking for CLI tools + AI engineers building agents. Both need the same information.

### Where value comes from

Not a list — a judgment layer. Collect tools, but also rate them:
- Is it maintained? (last commit, issue response rate)
- Is it agent-ready? (non-interactive mode, machine-readable output, no auth prompts)
- Is there an MCP server version?
- What's the install story? (brew, cargo, pip, npm — friction varies)

### Risks to manage

- **Maintenance rot**: tools go stale. Need automation to flag unmaintained entries.
- **SEO competition**: pure directories rank poorly. Need a unique angle — the AI-agent-ready framing is it.
- **Scope creep**: don't try to catalog everything. Start narrow (50-100 tools), go deep.

---

## Project Plan

### Phase 1 — Foundation (MVP)
- [ ] Define data schema for tool entries (name, description, category, install, agent-ready score, MCP status, repo URL)
- [ ] Pick tech stack: static site (Astro or 11ty) + JSON/YAML data files for easy contribution
- [ ] Design information architecture: categories, tags, filtering
- [ ] Seed with 30-50 high-quality tools across 5-6 categories

### Phase 2 — Content
- [ ] Categories to cover: DevOps/Infra, Data/DB, Media/Files, AI/LLM native, Web/HTTP, Productivity
- [ ] For each tool: add "use with AI" example (a prompt or shell snippet showing agent usage)
- [ ] Build contribution workflow (GitHub PRs, JSON schema validation)

### Phase 3 — Quality signals
- [ ] Script to check GitHub last-commit date for each tool
- [ ] Agent-ready scoring rubric (non-interactive flag, JSON output, stdin support, exit codes)
- [ ] MCP server tracker (link to registry or repo when available)

### Phase 4 — Distribution
- [ ] SEO: target "cli tool for X" queries
- [ ] Submit to Hacker News, developer newsletters
- [ ] GitHub awesome-list cross-posting

---

## Tech Stack Decision

**Recommended: Astro + static JSON data files**
- Fast static output, easy deployment to Cloudflare Pages or GitHub Pages
- Data files are plain JSON/YAML — contributors don't need to touch code
- Search via Pagefind (no backend needed)
- Zero runtime cost

---

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
