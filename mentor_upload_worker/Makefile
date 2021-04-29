DOCKER_IMAGE?=mentor-upload-worker
ROOT=$(shell dirname ${PWD})
VENV=.venv
VENV_PIP=$(VENV)/bin/pip
$(VENV):
	$(MAKE) $(VENV)-update

.PHONY $(VENV)-installed:
$(VENV)-installed:
	$(ROOT)/tools/virtualenv_ensure_installed.sh

.PHONY: $(VENV)-update
$(VENV)-update: $(VENV)-installed
	[ -d $(VENV) ] || virtualenv -p python3.8 $(VENV)
	$(VENV_PIP) install --upgrade pip
	$(VENV_PIP) install -r requirements.test.txt

.PHONY clean:
clean:
	rm -rf .pytest_cache .mypy_cache build

.PHONY docker-build:
docker-build:
	docker build -t $(DOCKER_IMAGE) .

.PHONY: format
format: $(VENV)
	cd $(ROOT) && $(MAKE) format

.PHONY: license
license:
	cd $(ROOT) && make license

.PHONY: test
test: $(VENV)
	. $(VENV)/bin/activate \
		&& export PYTHONPATH=$${PYTHONPATH}:$(PWD)/src \
		&& coverage run \
			--omit="$(PWD)/tests $(VENV)" \
			-m py.test -vv $(args)
			
.PHONY: test-all
test-all:
	$(MAKE) test-format
	$(MAKE) test-lint
	$(MAKE) test-license
	$(MAKE) test-types
	$(MAKE) test

.PHONY: test-format
test-format: $(VENV)
	cd $(ROOT) && $(MAKE) test-format

.PHONY: test-license
test-license:
	cd $(ROOT) && make test-license
	
.PHONY: test-lint
test-lint: $(VENV)
	cd $(ROOT) && $(MAKE) test-lint

.PHONY: test-types
test-types: $(VENV)
	cd $(ROOT) && $(MAKE) test-types

.PHONY: update-deps
update-deps: $(VENV)
	. $(VENV)/bin/activate && pip-upgrade requirements*
