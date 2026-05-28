# 8-step verification checklist

Demo's only purpose: prove the **deployment chain** end-to-end before touching books_organizer.
If any step fails, stop and fix that step before going further.

Replace `NAS_USER`, `NAS_IP`, `NAS_DIR` with your real values.

## Pre-flight (on the NAS, one-time)

```bash
ssh NAS_USER@NAS_IP
uname -a                         # confirm Linux + arch (expect x86_64 → amd64)
docker version                   # confirm docker daemon works
mkdir -p /volume1/docker/demo    # adjust path to your NAS layout
```

If `docker` is missing on Ugreen NAS, enable it via the Docker Manager UI first.

## Steps

| # | Action | Pass condition |
|---|---|---|
| 1 | `make build VERSION=0.1.0` (on Mac) | `docker images` shows `docker-demo:0.1.0` |
| 2 | `make local-run` (on Mac) | `/health` returns `{"ok":true,"arch":"x86_64",...}` |
| 3 | `make local-stop && rm -rf data/` | clean slate |
| 4 | `make save VERSION=0.1.0` | `docker-demo-0.1.0.tar.gz` exists (~50MB) |
| 5 | `make scp NAS=NAS_USER@NAS_IP NAS_DIR=/volume1/docker/demo` | files on NAS at that path |
| 6 | `make deploy NAS=NAS_USER@NAS_IP NAS_DIR=/volume1/docker/demo` | NAS container is running (`docker ps`) |
| 7 | From another LAN machine: `curl http://NAS_IP:8765/health` | returns NAS's arch + ok:true |
| 8 | `curl http://NAS_IP:8765/count` × 5 times; `docker compose restart demo`; `curl /count` again | counter keeps incrementing (proves persistent volume) |

## Real books source mount test (step 8.5)

After steps 1–8 pass, mount your source NAS share on the target NAS at e.g. `/mnt/book` (via SMB or NFS — set up at OS level, not in container), then:

```bash
ssh NAS_USER@NAS_IP "cd /volume1/docker/demo && \
  BOOKS_HOST_PATH=/mnt/book TAG=0.1.0 docker compose up -d --force-recreate"

curl http://NAS_IP:8765/
# Should list real book filenames from the source NAS
```

If `/` returns real filenames, the bind-mount strategy for the real `books_organizer` is validated.

## Rollback drill

```bash
# Tag a "broken" 0.1.1 by editing app.py to crash, then build/deploy
make deploy VERSION=0.1.1 NAS=...
# Confirm it's broken
curl http://NAS_IP:8765/health   # fails

# Roll back
ssh NAS_USER@NAS_IP "cd /volume1/docker/demo && TAG=0.1.0 docker compose up -d"
curl http://NAS_IP:8765/health   # back to ok
```

When this drill passes, you've also validated the rollback procedure.
