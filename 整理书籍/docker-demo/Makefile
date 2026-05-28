VERSION ?= 0.1.0
IMAGE   := docker-demo
TARBALL := $(IMAGE)-$(VERSION).tar.gz
NAS     ?=
NAS_DIR ?=

.PHONY: build local-run local-stop save scp deploy clean

build:
	docker buildx build --platform linux/amd64 -t $(IMAGE):$(VERSION) --load .
	docker tag $(IMAGE):$(VERSION) $(IMAGE):latest

local-run:
	TAG=$(VERSION) docker compose up -d --force-recreate
	@sleep 1
	@curl -sf http://localhost:8765/health | python3 -m json.tool || true

local-stop:
	docker compose down

save:
	docker save $(IMAGE):$(VERSION) | gzip > $(TARBALL)
	@ls -lh $(TARBALL)

scp:
	@test -n "$(NAS)" || (echo "NAS=user@host required"; exit 1)
	@test -n "$(NAS_DIR)" || (echo "NAS_DIR=/path required"; exit 1)
	ssh $(NAS) "mkdir -p $(NAS_DIR)"
	scp $(TARBALL) docker-compose.yml $(NAS):$(NAS_DIR)/

deploy: build save scp
	@test -n "$(NAS)" || (echo "NAS=user@host required"; exit 1)
	@test -n "$(NAS_DIR)" || (echo "NAS_DIR=/path required"; exit 1)
	ssh $(NAS) "cd $(NAS_DIR) && \
		gunzip -c $(TARBALL) | docker load && \
		TAG=$(VERSION) docker compose up -d --force-recreate && \
		docker ps --filter name=docker-demo"

clean:
	rm -f $(IMAGE)-*.tar.gz
	rm -rf data/
