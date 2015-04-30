HERE = $(shell pwd)
BIN = $(HERE)/bin

BUILD_DIRS = bin .build build include lib lib64 man share package *.egg

.PHONY: all build clean test

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

test: build
	python setup.py test pep8 pyflakes

integration: build
	PYFLAKES_NODOCTEST=True python setup.py integration pep8 pyflakes

pack: kingpin.zip
	@python kingpin.zip --help 2>&1 >/dev/null && echo Success || echo Fail

kingpin.zip:
	rm -rf zip
	mkdir -p zip
	pip install --process-dependency-links --target ./zip ./
	find ./zip -name '*.pyc' -delete
	find ./zip -name '*.egg-info' | xargs rm -rf
	cd zip; ln -sf kingpin/bin/deploy.py ./__main__.py
	cd zip; zip -9mrv ../kingpin.zip .
	rm -rf zip

docs:
	cd docs; make clean html
