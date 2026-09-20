CONTAINER ?= $(shell command -v docker >/dev/null 2>&1 && echo docker || echo podman)

DEV_IMAGE := esp32-streamline-hacs-dev
LOCK_IMAGE := esp32-streamline-hacs-lock
HASSFEST_IMAGE := esp32-streamline-hacs-hassfest
ACTIONLINT_IMAGE := esp32-streamline-hacs-actionlint

SOURCE := custom_components/streamline
TESTS := tests
MODELS := $(SOURCE)/models.py
GENERATED_MODELS := .models.generated.py
MANIFEST := $(SOURCE)/manifest.json
# Generate models and test payloads from one immutable device contract.
# Advance this pin and regenerate the models together.
STREAMLINE_CONTRACT_REF := 192d095cc6ea8be48eb455ab40e5ffdbf66015b6
STREAMLINE_REF ?= $(STREAMLINE_CONTRACT_REF)
OPENAPI_URL := https://raw.githubusercontent.com/lutyjj/esp32-streamline/$(STREAMLINE_REF)/docs/openapi.json
# Rules the contract's own prose, carried into generated docstrings, cannot
# meet. pyproject repeats them for $(MODELS); the check renders to a scratch
# path no per-file rule can name.
GENERATED_IGNORES := E501,RUF001
# release-please owns the version in manifest.json; version-check gates a
# published tree against it.
MANIFEST_VERSION := $(shell sed -n 's/^[[:space:]]*"version": "\([^"]*\)".*/\1/p' $(MANIFEST))
VERSION ?= $(MANIFEST_VERSION)

CONTAINER_RUN := $(CONTAINER) run --rm --user "$(shell id -u):$(shell id -g)" \
	-v "$(CURDIR):/workspace" \
	-e HOME=/tmp -e MYPY_CACHE_DIR=/tmp/mypy -e PYTHONDONTWRITEBYTECODE=1 \
	-e RUFF_CACHE_DIR=/tmp/ruff -e STREAMLINE_OPENAPI=/tmp/device-openapi.json \
	-w /workspace $(DEV_IMAGE)
LOCK_RUN := $(CONTAINER) run --rm --user "$(shell id -u):$(shell id -g)" \
	-v "$(CURDIR):/workspace" -e UV_CACHE_DIR=/tmp/uv-cache \
	-w /workspace $(LOCK_IMAGE) uv

define render_models
	python -c "import urllib.request; urllib.request.urlretrieve(\"$(OPENAPI_URL)\", \"$$STREAMLINE_OPENAPI\")" && \
	datamodel-codegen --input $$STREAMLINE_OPENAPI --input-file-type openapi \
		--openapi-scopes schemas --output-model-type pydantic_v2.BaseModel \
		--target-python-version 3.14 --use-standard-collections --use-union-operator \
		--enum-field-as-literal all --use-annotated --extra-fields ignore \
		--disable-timestamp --formatters builtin \
		--output $(1) && \
	ruff format --config pyproject.toml --line-length 100 $(1) && \
	ruff check --config pyproject.toml --fix --ignore $(GENERATED_IGNORES) $(1) && \
	ruff format --config pyproject.toml --line-length 100 $(1)
endef

.PHONY: actionlint actionlint-image check contract-check dev-image format generate generate-check hassfest hassfest-image lint lock lock-check lock-image lock-upgrade quality test version-check

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

generate: dev-image
	$(CONTAINER_RUN) sh -c '$(call render_models,$(MODELS))'

generate-check: dev-image
	$(CONTAINER_RUN) sh -c 'trap "rm -f $(GENERATED_MODELS)" EXIT; \
		$(call render_models,$(GENERATED_MODELS)) && diff -u $(MODELS) $(GENERATED_MODELS)'

format: dev-image
	$(CONTAINER_RUN) sh -c 'ruff check --select I --fix $(SOURCE) $(TESTS) && ruff format $(SOURCE) $(TESTS)'

lint: dev-image
	$(CONTAINER_RUN) sh -c 'ruff format --check $(SOURCE) $(TESTS) && ruff check $(SOURCE) $(TESTS) && mypy $(SOURCE) $(TESTS)'

test: dev-image
	$(CONTAINER_RUN) sh -c 'python -c "import urllib.request; urllib.request.urlretrieve(\"$(OPENAPI_URL)\", \"$$STREAMLINE_OPENAPI\")" && PYTHONPATH=/workspace pytest -p no:cacheprovider -q'

contract-check: generate-check test

hassfest-image:
	$(CONTAINER) build -f Dockerfile.hassfest -t $(HASSFEST_IMAGE) .

hassfest: hassfest-image
	$(CONTAINER) run --rm -v "$(CURDIR):/repo:ro" $(HASSFEST_IMAGE) \
		--core-path=/tmp --integration-path=/repo/custom_components/streamline

quality: lock-check contract-check lint actionlint

check: quality hassfest

# release-please bumps manifest.json and the changelog; this gate proves a
# tagged tree carries the version the release publishes.
version-check:
	@test -n "$(VERSION)" || { echo "VERSION is required" >&2; exit 2; }
	@printf '%s' "$(VERSION)" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$$' || { echo "VERSION must be a stable X.Y.Z release version" >&2; exit 2; }
	@test "$(VERSION)" = "$(MANIFEST_VERSION)" || { echo "VERSION=$(VERSION) does not match $(MANIFEST) ($(MANIFEST_VERSION))" >&2; exit 2; }
