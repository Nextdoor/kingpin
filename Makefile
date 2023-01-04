HERE = $(shell pwd)

VENV_CMD    := python3 -m venv
VENV_DIR    := $(HERE)/.venv
PYTHON      := $(VENV_DIR)/bin/python
PYTEST      := $(VENV_DIR)/bin/pytest
PYFLAKES    := $(VENV_DIR)/bin/pyflakes
PYBLACK     := $(VENV_DIR)/bin/black

BUILD_DIRS = bin .build build include lib lib64 man share package *.egg dist *.egg-info .coverage .pytest_cache

DRY ?= true
ifneq ($(DRY),false)
  PYBLACK_OPTS := --diff --check
endif

.PHONY: build
build: $(VENV_DIR)
	$(PYTHON) -m build

.PHONY: clean
clean: $(VENV_DIR)
	find kingpin -type f -name '*.pyc' -exec rm "{}" \;
	rm -f kingpin.zip
	rm -rf $(BUILD_DIRS)
	PATH=$(VENV_DIR)/bin:$(PATH) $(MAKE) -C docs clean

.PHONY: lint
lint: $(VENV_DIR)
	$(PYBLACK) $(PYBLACK_OPTS) kingpin

.PHONY: test
test: $(VENV_DIR)
	PYTHONPATH=$(HERE) $(PYTEST) --cov=kingpin -v
	PYTHONPATH=$(HERE) $(PYFLAKES) kingpin
	PYTHONPATH=$(HERE) $(PYTHON) kingpin/bin/deploy.py --dry --script examples/test/sleep.json
	PYTHONPATH=$(HERE) $(PYTHON) kingpin/bin/deploy.py --dry --script examples/test/sleep.yaml

.PHONY: pack
pack: kingpin.zip
	$(PYTHON) kingpin.zip --help 2>&1 >/dev/null && echo Success || echo Fail

kingpin.zip: $(VENV_DIR)
	rm -rf zip
	mkdir -p zip
	$(PYTHON) -m pip install -r requirements.txt --target ./zip ./
	find ./zip -name '*.pyc' -delete
	find ./zip -name '*.egg-info' | xargs rm -rf
	cd zip; ln -sf kingpin/bin/deploy.py ./__main__.py
	cd zip; zip -9mrv ../kingpin.zip .
	rm -rf zip

.PHONY: docs
docs: $(VENV_DIR)
	PATH=$(VENV_DIR)/bin:$(PATH) $(MAKE) -C docs html

.PHONY: venv
venv: $(VENV_DIR)

$(VENV_DIR): requirements.txt requirements.test.txt
	$(VENV_CMD) $(VENV_DIR)
	$(PYTHON) -m pip install -U pip setuptools wheel
	$(PYTHON) -m pip install -r requirements.test.txt
	$(PYTHON) -m pip install -r requirements.txt
	touch $(VENV_DIR)




