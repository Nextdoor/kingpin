HERE = $(shell pwd)
BIN = $(HERE)/bin

BUILD_DIRS = bin .build build include lib lib64 man share

ZOOKEEPER = $(BIN)/zookeeper
ZOOKEEPER_VERSION ?= 3.4.6
ZOOKEEPER_PATH ?= $(ZOOKEEPER)
ZOOKEEPER_URL = http://apache.osuosl.org/zookeeper/zookeeper-$(ZOOKEEPER_VERSION)/zookeeper-$(ZOOKEEPER_VERSION).tar.gz

.PHONY: all build clean test zookeeper clean-zookeeper

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

integration: build $(ZOOKEEPER)
	PYFLAKES_NODOCTEST=True ZOOKEEPER_PATH=$(ZOOKEEPER_PATH) python setup.py integration pep8 pyflakes

$(ZOOKEEPER):
	@echo "Installing Zookeeper"
	mkdir -p $(BIN) && cd $(BIN) && curl -C - $(ZOOKEEPER_URL) | tar -zx
	mv $(BIN)/zookeeper-$(ZOOKEEPER_VERSION) $(ZOOKEEPER_PATH)
	chmod a+x $(ZOOKEEPER_PATH)/bin/zkServer.sh
	@echo "Finished installing Zookeeper"

zookeeper: $(ZOOKEEPER)

clean-zookeeper:
	rm -rf zookeeper $(ZOOKEEPER_PATH)
