HERE = $(shell pwd)

UV_BIN      := $(or $(shell command -v uv 2>/dev/null),$(HOME)/.local/bin/uv)

PYTHON      := $(UV_BIN) run python
PYTEST      := $(UV_BIN) run pytest
PYFLAKES    := $(UV_BIN) run pyflakes
PYBLACK     := $(UV_BIN) run black

BUILD_DIRS = bin .build build include lib lib64 man share package *.egg dist *.egg-info .coverage .pytest_cache

DRY ?= true
ifneq ($(DRY),false)
PYBLACK_OPTS := --diff --check
endif

$(UV_BIN):
	@echo "Error: uv is not installed."
	@echo "Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
	@echo "Or see: https://docs.astral.sh/uv/getting-started/installation/"
	@exit 1

.PHONY: build
build: $(UV_BIN)
	$(UV_BIN) build

.PHONY: clean
clean:
	find kingpin -type f -name '*.pyc' -exec rm "{}" \;
	rm -f kingpin.zip
	rm -rf $(BUILD_DIRS) .venv docs/_build

.PHONY: lint
lint: $(UV_BIN)
	$(PYBLACK) $(PYBLACK_OPTS) kingpin

.PHONY: test
test: $(UV_BIN)
	PYTHONPATH=$(HERE) $(PYTEST) --cov=kingpin -v
	PYTHONPATH=$(HERE) $(PYFLAKES) kingpin
	PYTHONPATH=$(HERE) $(PYTHON) kingpin/bin/deploy.py --dry --script examples/test/sleep.json
	PYTHONPATH=$(HERE) $(PYTHON) kingpin/bin/deploy.py --dry --script examples/test/sleep.yaml

.PHONY: pack
pack: kingpin.zip
	$(PYTHON) kingpin.zip --help 2>&1 >/dev/null && echo Success || echo Fail

kingpin.zip: $(UV_BIN)
	rm -rf zip
	mkdir -p zip
	$(UV_BIN) run pip install --target ./zip ./
	find ./zip -name '*.pyc' -delete
	find ./zip -name '*.egg-info' | xargs rm -rf
	cd zip; ln -sf kingpin/bin/deploy.py ./__main__.py
	cd zip; zip -9mrv ../kingpin.zip .
	rm -rf zip

.PHONY: docs
docs: $(UV_BIN)
	$(UV_BIN) run --group docs $(MAKE) -C docs html

.PHONY: venv
venv: $(UV_BIN)
	$(UV_BIN) sync
