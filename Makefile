CONTAINER ?= docker

DEV_IMAGE := esp32-streamline-hacs-dev
LOCK_IMAGE := esp32-streamline-hacs-lock
HASSFEST_IMAGE := esp32-streamline-hacs-hassfest

SOURCE := custom_components/streamline
TESTS := tests
MODELS := $(SOURCE)/models.py
GENERATED_MODELS := .models.generated.py
STREAMLINE_REF ?= mainline
OPENAPI_URL := https://raw.githubusercontent.com/lutyjj/esp32-streamline/$(STREAMLINE_REF)/docs/openapi.json

CONTAINER_RUN := $(CONTAINER) run --rm --user "$(shell id -u):$(shell id -g)" \
	-v "$(CURDIR):/workspace" \
	-e HOME=/tmp -e MYPY_CACHE_DIR=/tmp/mypy -e PYTHONDONTWRITEBYTECODE=1 \
	-e RUFF_CACHE_DIR=/tmp/ruff -e STREAMLINE_OPENAPI=/tmp/device-openapi.json \
	-w /workspace $(DEV_IMAGE)
LOCK_RUN := $(CONTAINER) run --rm --user "$(shell id -u):$(shell id -g)" \
	-v "$(CURDIR):/workspace" -e UV_CACHE_DIR=/tmp/uv-cache \
	-w /workspace $(LOCK_IMAGE) uv

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

.PHONY: check dev-image format generate generate-check hassfest hassfest-image lint lock lock-check lock-image lock-upgrade quality test

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

hassfest-image:
	$(CONTAINER) build -f Dockerfile.hassfest -t $(HASSFEST_IMAGE) .

hassfest: hassfest-image
	$(CONTAINER) run --rm -v "$(CURDIR):/repo:ro" $(HASSFEST_IMAGE) \
		--core-path=/tmp --integration-path=/repo/custom_components/streamline

quality: lock-check generate-check lint test

check: quality hassfest
