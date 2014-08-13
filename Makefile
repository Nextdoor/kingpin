HERE = $(shell pwd)
BIN = $(HERE)/bin

BUILD_DIRS = bin .build build include lib lib64 man share

.PHONY: all build clean test

all: build

build: .build

.build: requirements.txt requirements.test.txt
	python setup.py install
	pip install -r requirements.test.txt
	touch .build

clean:
	find . -type f -name '*.pyc' -exec rm "{}" \;
	rm -rf $(BUILD_DIRS)

test: build
	python setup.py test pep8 pyflakes

integration: build
	PYFLAKES_NODOCTEST=True python setup.py integration pep8 pyflakes
