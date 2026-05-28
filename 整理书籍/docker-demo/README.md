# docker-demo

Throwaway project. Its only job: validate the **full deployment chain**
(Mac build → image → scp → target NAS → running container → LAN-accessible web)
**before** dockerizing the real `books_organizer`.

## What it verifies

- Dockerfile builds and runs locally
- `docker buildx` cross-platform build (Mac arm64 → NAS amd64)
- `docker save` + `scp` + `docker load` image transfer works
- `docker compose` runs on the target NAS
- LAN access works from another machine
- Bind-mount of host directory into container works (simulates SMB-mounted book source)
- SQLite file persists across container restarts (simulates `books.db`)

When all 8 steps in `docs/CHECKLIST.md` pass, **delete this project** and move on
to dockerizing `books_organizer` for real.

## Files

- `app.py` — ~70-line Flask app with three routes
- `requirements.txt` — flask only
- `Dockerfile` — python:3.11-slim-bookworm base
- `docker-compose.yml` — service definition with volumes
- `Makefile` — `build / save / scp / deploy / local-run` targets
- `docs/CHECKLIST.md` — the 8-step verification list (run this manually)
- `.dockerignore` — keeps build context tiny

## Quick start (local Mac test, before any NAS work)

```bash
cd /Users/bai/code/整理书籍/docker-demo
make local-run
# expect: /health returns ok:true, /count increments, / lists /tmp contents
make local-stop
```

## Quick start (deploy to NAS)

```bash
# Edit these as needed:
make deploy NAS=ugreen@192.168.1.50 NAS_DIR=/volume1/docker/demo VERSION=0.1.0
```

Read `docs/CHECKLIST.md` for the full step-by-step.
