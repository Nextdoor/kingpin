HERE = $(shell pwd)
BIN = $(HERE)/bin

BUILD_DIRS = bin .build build include lib lib64 man share package *.egg

.PHONY: all build clean test docs

# Only execute a subset of our integration tests by default
INTEGRATION_TESTS ?= aws,rightscale,http,rollbar,slack,spotinst

# Hack to ensure we get 100% unit test coverage
export URLLIB_DEBUG=true

all: build
build: .build

.build: requirements.test.txt
	python setup.py install
	pip install -r requirements.test.txt
	touch .build

clean:
	find . -type f -name '*.pyc' -exec rm "{}" \;
	rm -f kingpin.zip
	rm -rf $(BUILD_DIRS)
	$(MAKE) -C docs clean

test: build docs
	python3 setup.py test pep8 pyflakes
	# A few simple dry-tests of yaml and json scripts to make sure that the
	# full commandline actually works.
	PYTHONPATH=$(HERE) python kingpin/bin/deploy.py --dry --script examples/test/sleep.json
	PYTHONPATH=$(HERE) python kingpin/bin/deploy.py --dry --script examples/test/sleep.yaml

integration: build
	INTEGRATION_TESTS=$(INTEGRATION_TESTS) PYFLAKES_NODOCTEST=True \
		python3 setup.py integration pep8 pyflakes

pack: kingpin.zip
	python kingpin.zip --help 2>&1 >/dev/null && echo Success || echo Fail

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
	$(MAKE) -C docs html
