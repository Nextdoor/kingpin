HERE = $(shell pwd)

VENV_CMD    := python3 -m venv
VENV_DIR    := $(HERE)/.venv
PYBLACK_BIN := $(VENV_DIR)/bin/black
PYTHON      := $(VENV_DIR)/bin/python

BUILD_DIRS = bin .build build include lib lib64 man share package *.egg

# Are we DRY? Automatically default us to DRY.
DRY ?= true
ifeq ($(DRY),false)
  PYBLACK := $(PYBLACK_BIN)
else
  PYBLACK := $(PYBLACK_BIN) --diff --check
endif

.PHONY: all build clean test docs

# Only execute a subset of our integration tests by default
INTEGRATION_TESTS ?= aws,rightscale,http,rollbar,slack,spotinst

# Hack to ensure we get 100% unit test coverage
export URLLIB_DEBUG=true

.PHONY: all
all: build

.PHONY: venv
venv: $(VENV_DIR)

$(VENV_DIR): requirements.txt requirements.test.txt
	$(VENV_CMD) --help
	$(VENV_CMD) $(VENV_DIR) && \
		find $(VENV_DIR) && \
		$(VENV_DIR)/bin/pip install -r requirements.test.txt && \
		$(VENV_DIR)/bin/pip install -r requirements.txt && \
		touch $(VENV_DIR)

.PHONY: build
build: $(VENV_DIR)
	$(PYTHON) setup.py install

pyblack:
	$(PYBLACK) kingpin 

.PHONY: clean
clean:
	find . -type f -name '*.pyc' -exec rm "{}" \;
	rm -f kingpin.zip
	rm -rf $(BUILD_DIRS)
	PATH=$(VENV_DIR)/bin:$(PATH) $(MAKE) -C docs clean

.PHONY: test
test: build docs
	$(PYTHON) setup.py test pyblack pyflakes
	# A few simple dry-tests of yaml and json scripts to make sure that the
	# full commandline actually works.
	PYTHONPATH=$(HERE) $(PYTHON) kingpin/bin/deploy.py --dry --script examples/test/sleep.json
	PYTHONPATH=$(HERE) $(PYTHON) kingpin/bin/deploy.py --dry --script examples/test/sleep.yaml

.PHONY: integration
integration: build
	. .venv/bin/activate
	INTEGRATION_TESTS=$(INTEGRATION_TESTS) PYFLAKES_NODOCTEST=True \
		$(PYTHON) setup.py integration pyblack

.PHONY: pack
pack: kingpin.zip
	$(PYTHON) kingpin.zip --help 2>&1 >/dev/null && echo Success || echo Fail

kingpin.zip:
	rm -rf zip
	mkdir -p zip
	pip install -r requirements.txt --target ./zip ./
	find ./zip -name '*.pyc' -delete
	find ./zip -name '*.egg-info' | xargs rm -rf
	cd zip; ln -sf kingpin/bin/deploy.py ./__main__.py
	cd zip; zip -9mrv ../kingpin.zip .
	rm -rf zip

docs:
	PATH=$(VENV_DIR)/bin:$(PATH) $(MAKE) -C docs html
