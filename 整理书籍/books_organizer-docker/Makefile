VERSION    ?= 0.1.0
IMAGE_FULL := books-organizer
IMAGE_WEB  := books-organizer-web
NAS        ?=
NAS_DIR    ?=

SRC_DIR := ../books_organizer

.PHONY: build build-web local-test save scp deploy migrate-db rollback clean

build: build-web
	docker buildx build --platform linux/amd64 \
		-t $(IMAGE_FULL):$(VERSION) \
		-f Dockerfile \
		--load \
		--build-context books_organizer=$(SRC_DIR) \
		.
	docker tag $(IMAGE_FULL):$(VERSION) $(IMAGE_FULL):latest

build-web:
	docker buildx build --platform linux/amd64 \
		-t $(IMAGE_WEB):$(VERSION) \
		-f Dockerfile.web \
		--load \
		--build-context books_organizer=$(SRC_DIR) \
		.
	docker tag $(IMAGE_WEB):$(VERSION) $(IMAGE_WEB):latest

local-test: build-web
	TAG=$(VERSION) docker compose up -d --force-recreate web
	@sleep 2
	@curl -sf http://localhost:8765/api/facets | head -c 400 ; echo

save:
	docker save $(IMAGE_FULL):$(VERSION) | gzip > $(IMAGE_FULL)-$(VERSION).tar.gz
	docker save $(IMAGE_WEB):$(VERSION)  | gzip > $(IMAGE_WEB)-$(VERSION).tar.gz
	@ls -lh *.tar.gz

scp:
	@test -n "$(NAS)" || (echo "NAS=user@host required"; exit 1)
	@test -n "$(NAS_DIR)" || (echo "NAS_DIR=/path required"; exit 1)
	ssh $(NAS) "mkdir -p $(NAS_DIR)/data"
	scp $(IMAGE_FULL)-$(VERSION).tar.gz $(IMAGE_WEB)-$(VERSION).tar.gz \
		docker-compose.yml $(NAS):$(NAS_DIR)/

migrate-db:
	@test -n "$(NAS)" || (echo "NAS=user@host required"; exit 1)
	@test -n "$(NAS_DIR)" || (echo "NAS_DIR=/path required"; exit 1)
	@echo "==> WAL checkpoint (确保所有写入都落到 books.db 主文件)"
	sqlite3 $(SRC_DIR)/books.db "PRAGMA wal_checkpoint(TRUNCATE);"
	@echo "==> rsync books.db + covers/ 到 NAS"
	rsync -avhP $(SRC_DIR)/books.db $(NAS):$(NAS_DIR)/data/
	rsync -avhP --delete $(SRC_DIR)/covers/ $(NAS):$(NAS_DIR)/data/covers/

deploy: build save scp
	@test -n "$(NAS)" || (echo "NAS=user@host required"; exit 1)
	@test -n "$(NAS_DIR)" || (echo "NAS_DIR=/path required"; exit 1)
	ssh $(NAS) "cd $(NAS_DIR) && \
		gunzip -c $(IMAGE_WEB)-$(VERSION).tar.gz | docker load && \
		gunzip -c $(IMAGE_FULL)-$(VERSION).tar.gz | docker load && \
		TAG=$(VERSION) docker compose up -d --force-recreate web && \
		docker ps --filter name=books-organizer"

rollback:
	@test -n "$(NAS)" || (echo "NAS=user@host required"; exit 1)
	@test -n "$(NAS_DIR)" || (echo "NAS_DIR=/path required"; exit 1)
	@test -n "$(PREV)" || (echo "PREV=<旧版本号> required"; exit 1)
	ssh $(NAS) "cd $(NAS_DIR) && TAG=$(PREV) docker compose up -d web"

clean:
	rm -f *.tar.gz
