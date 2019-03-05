BIN = $(HERE)/bin

BUILD_DIRS = bin .build build include lib lib64 man share package *.egg

.PHONY: all build clean test docs

# Only execute a subset of our integration tests by default
INTEGRATION_TESTS ?= aws,rightscale,http,rollbar,slack,spotinst

# Hack to ensure we get 100% unit test coverage
export URLLIB_DEBUG=true

all: build

build: venv

clean:
	find . -type f -name '*.pyc' -exec rm "{}" \;
	rm -f kingpin.zip
	rm -rf $(BUILD_DIRS)
	$(MAKE) -C docs clean

test: build docs
	.venv3/bin/python3 setup.py test pep8 pyflakes
	# A few simple dry-tests of yaml and json scripts to make sure that the
	# full commandline actually works.
	.venv3/bin/python3 kingpin/bin/deploy.py --dry --script examples/test/sleep.json
	.venv3/bin/python3 kingpin/bin/deploy.py --dry --script examples/test/sleep.yaml

integration: build
	INTEGRATION_TESTS=$(INTEGRATION_TESTS) PYFLAKES_NODOCTEST=True \
		python3 setup.py integration pep8 pyflakes

pack: kingpin.zip
	@python3 kingpin.zip --help 2>&1 >/dev/null && echo Success || echo Fail

kingpin.zip:
	rm -rf zip
	mkdir -p zip
	.venv3/bin/pip3 install -r requirements.txt --target ./zip ./
	find ./zip -name '*.pyc' -delete
	find ./zip -name '*.egg-info' | xargs rm -rf
	cd zip; ln -sf kingpin/bin/deploy.py ./__main__.py
	cd zip; zip -9mrv ../kingpin.zip .
	rm -rf zip

docs: venv
	(source .venv3/bin/activate ; $(MAKE) -C docs html)

venv: .venv3/bin/activate
.venv3/bin/activate: requirements.test.txt requirements.txt
	@echo "Building .venv3 virtual environment..."
	@test -d .venv3 || python3 -m venv .venv3 && .venv3/bin/pip3 install pip --upgrade
	@.venv3/bin/pip3 install -r requirements.test.txt
	@.venv3/bin/pip3 install -r requirements.txt
	@touch .venv3/bin/activate
