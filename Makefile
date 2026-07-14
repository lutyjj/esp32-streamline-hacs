CONTAINER ?= docker

DEV_IMAGE := esp32-streamline-hacs-dev
LOCK_IMAGE := esp32-streamline-hacs-lock
HASSFEST_IMAGE := esp32-streamline-hacs-hassfest
ACTIONLINT_IMAGE := esp32-streamline-hacs-actionlint
RELEASE_TOOLS_IMAGE := esp32-streamline-hacs-release-tools

SOURCE := custom_components/streamline
TESTS := tests
TOOLS := tools
MODELS := $(SOURCE)/models.py
GENERATED_MODELS := .models.generated.py
STREAMLINE_REF ?= mainline
OPENAPI_URL := https://raw.githubusercontent.com/lutyjj/esp32-streamline/$(STREAMLINE_REF)/docs/openapi.json
VERSION ?= $(shell sed -n 's/^  "version": "\([^"]*\)"/\1/p' $(SOURCE)/manifest.json)
GIT_COMMON_DIR := $(abspath $(shell git rev-parse --git-common-dir))

CONTAINER_RUN := $(CONTAINER) run --rm --user "$(shell id -u):$(shell id -g)" \
	-v "$(CURDIR):/workspace" \
	-e HOME=/tmp -e MYPY_CACHE_DIR=/tmp/mypy -e PYTHONDONTWRITEBYTECODE=1 \
	-e RUFF_CACHE_DIR=/tmp/ruff -e STREAMLINE_OPENAPI=/tmp/device-openapi.json \
	-w /workspace $(DEV_IMAGE)
LOCK_RUN := $(CONTAINER) run --rm --user "$(shell id -u):$(shell id -g)" \
	-v "$(CURDIR):/workspace" -e UV_CACHE_DIR=/tmp/uv-cache \
	-w /workspace $(LOCK_IMAGE) uv
GIT_CLIFF := $(CONTAINER) run --rm --user "$(shell id -u):$(shell id -g)" \
	-v "$(CURDIR):/app" -v "$(GIT_COMMON_DIR):$(GIT_COMMON_DIR)" \
	-e HOME=/tmp -w /app $(RELEASE_TOOLS_IMAGE)

define render_models
	datamodel-codegen --url $(OPENAPI_URL) --input-file-type openapi \
		--openapi-scopes schemas --output-model-type pydantic_v2.BaseModel \
		--target-python-version 3.14 --use-standard-collections --use-union-operator \
		--enum-field-as-literal all --use-annotated --extra-fields ignore \
		--disable-timestamp --formatters builtin \
		--output $(1) && \
	ruff format --config pyproject.toml --line-length 100 $(1) && \
	ruff check --config pyproject.toml --fix --ignore E501 $(1) && \
	ruff format --config pyproject.toml --line-length 100 $(1)
endef

.PHONY: actionlint actionlint-image check dev-image format generate generate-check hassfest hassfest-image lint lock lock-check lock-image lock-upgrade quality release release-check release-history release-notes release-notes-check release-prepare release-tools-image test version-check version-prepare

lock-image:
	$(CONTAINER) build --target lock-tool -t $(LOCK_IMAGE) .

lock: lock-image
	$(LOCK_RUN) lock

lock-upgrade: lock-image
	$(LOCK_RUN) lock --upgrade

lock-check: lock-image
	$(LOCK_RUN) lock --check

dev-image:
	$(CONTAINER) build --target development -t $(DEV_IMAGE) .

actionlint-image:
	$(CONTAINER) build -f Dockerfile.actionlint -t $(ACTIONLINT_IMAGE) .

actionlint: actionlint-image
	$(CONTAINER) run --rm --user "$(shell id -u):$(shell id -g)" \
		-v "$(CURDIR):/repo:ro" -w /repo $(ACTIONLINT_IMAGE) -color

release-tools-image:
	$(CONTAINER) build -f Dockerfile.release-tools -t $(RELEASE_TOOLS_IMAGE) .

generate: dev-image
	$(CONTAINER_RUN) sh -c '$(call render_models,$(MODELS))'

generate-check: dev-image
	$(CONTAINER_RUN) sh -c 'trap "rm -f $(GENERATED_MODELS)" EXIT; \
		$(call render_models,$(GENERATED_MODELS)) && diff -u $(MODELS) $(GENERATED_MODELS)'

format: dev-image
	$(CONTAINER_RUN) sh -c 'ruff check --select I --fix $(SOURCE) $(TESTS) $(TOOLS) && ruff format $(SOURCE) $(TESTS) $(TOOLS)'

lint: dev-image
	$(CONTAINER_RUN) sh -c 'ruff format --check $(SOURCE) $(TESTS) $(TOOLS) && ruff check $(SOURCE) $(TESTS) $(TOOLS) && mypy $(SOURCE) $(TESTS) $(TOOLS)'

test: dev-image
	$(CONTAINER_RUN) sh -c 'python -c "import urllib.request; urllib.request.urlretrieve(\"$(OPENAPI_URL)\", \"$$STREAMLINE_OPENAPI\")" && PYTHONPATH=/workspace pytest -p no:cacheprovider -q'

hassfest-image:
	$(CONTAINER) build -f Dockerfile.hassfest -t $(HASSFEST_IMAGE) .

hassfest: hassfest-image
	$(CONTAINER) run --rm -v "$(CURDIR):/repo:ro" $(HASSFEST_IMAGE) \
		--core-path=/tmp --integration-path=/repo/custom_components/streamline

quality: lock-check generate-check lint test actionlint

check: quality hassfest

release-history:
	@remote="$$(git remote | sed -n '1p')"; \
		test -n "$$remote" || { echo "a git remote is required for release history" >&2; exit 2; }; \
		git fetch --quiet --force --prune --prune-tags "$$remote" '+refs/tags/*:refs/tags/*'

version-prepare: dev-image
	$(CONTAINER_RUN) python -m tools.release prepare "$(VERSION)"

version-check: dev-image
	$(CONTAINER_RUN) python -m tools.release check "$(VERSION)"

release-notes: release-history
	@$(MAKE) --no-print-directory version-check VERSION=$(VERSION) 1>&2
	@$(MAKE) --no-print-directory release-tools-image 1>&2
	@$(GIT_CLIFF) --unreleased --tag "v$(VERSION)" --strip all

release-notes-check:
	@notes="$$( $(MAKE) --no-print-directory release-notes VERSION=$(VERSION) )"; \
		test -n "$$(printf '%s' "$$notes" | tr -d '[:space:]')" || { \
			echo "release notes contain no user-facing changes" >&2; exit 2; \
		}

release-prepare:
	@test -z "$$(git status --porcelain)" || { echo "release preparation requires a clean worktree" >&2; exit 2; }
	$(MAKE) version-prepare VERSION=$(VERSION)
	$(MAKE) version-check VERSION=$(VERSION)
	$(MAKE) release-notes-check VERSION=$(VERSION)

release-check: version-check release-notes-check check

release: release-prepare
	$(MAKE) release-check VERSION=$(VERSION)
