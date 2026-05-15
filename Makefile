SHELL := /bin/bash

VENV_DIR := .venv-whispeer
PYTHON := $(VENV_DIR)/bin/python
PIP := $(PYTHON) -m pip

SEED_DIR := .homeassistant-seed/base
RUNTIME_DIR := .homeassistant
DEV_CONFIG_DIR := $(RUNTIME_DIR)/dev
TEST_CONFIG_DIR := $(RUNTIME_DIR)/test

HA_IMAGE ?= ghcr.io/home-assistant/home-assistant:stable
DEV_CONTAINER ?= hass-dev
TEST_CONTAINER ?= hass-test
DEV_PORT ?= 8125
TEST_PORT ?= 8126
CUSTOM_COMPONENTS_CONTAINER_DIR ?= /workdir/custom_components
TZ ?= America/Monterrey
LANG ?= en_US.UTF-8

WHISPEER_TEST_MODE ?= 1
WHISPEER_USERNAME ?= john
WHISPEER_PASSWORD ?= doe
WHISPEER_BASE_URL ?= http://localhost:$(TEST_PORT)
WHISPEER_WS_URL ?= ws://localhost:$(TEST_PORT)/api/websocket
WHISPEER_CONTAINER_NAME ?= $(TEST_CONTAINER)
WHISPEER_BROWSER ?= chromium
WHISPEER_HEADED ?= 1
WHISPEER_SLOWMO_MS ?= 150
WHISPEER_TIMEOUT_MS ?= 4000
WHISPEER_STEP_DELAY_MS ?= 2000
WHISPEER_E2E_START_AT ?=
WHISPEER_E2E_STOP_AFTER ?=
WHISPEER_PRESERVE_STATE ?= 0
PYTEST_ARGS ?=
EFFECTIVE_WHISPEER_HEADED := $(if $(filter --headless,$(MAKECMDGOALS)),0,$(WHISPEER_HEADED))

BROADLINK_RM4_MINI_IP ?= 192.168.1.7
BROADLINK_RM4_PRO_IP ?= 192.168.1.8

.DEFAULT_GOAL := help


BACKEND_PYTEST_TARGETS := custom_components/whispeer/tests
BACKEND_MARK_EXPR := not integration and not e2e and not rf_fast
FRONTEND_PYTEST_TARGETS := tests/test_websocket_integration.py tests/test_whispeer_rspec.py
FRONTEND_MARK_EXPR := integration or e2e or rf_fast

.PHONY: help install setup setup-dev setup-test setup_broadlink dev r test test_backend test_frontend test_frontend_dev --headless \
	hass-dev hass-test wait-dev wait-test stop-dev stop-test refresh-seed \
	clean-test-state

--headless:
	@:

help:
	@printf "Available targets:\n"
	@printf "  make setup              Prepare seeded dev/test Home Assistant runtimes\n"
	@printf "  make dev                Recreate and start the development Home Assistant\n"
	@printf "  make r                  Alias for restarting the development Home Assistant\n"
	@printf "  make test               Run the full backend + websocket + one-tab Playwright flow\n"
	@printf "  make test_backend       Run the backend-only pytest flow\n"
	@printf "  make test_frontend      Run websocket integration + one-tab RSpec-style E2E against hass-test\n"
	@printf "  make test_frontend_dev  Run websocket integration + one-tab RSpec-style E2E against hass-dev\n"
	@printf "  make setup_broadlink    Override Broadlink IPs in the dev runtime\n"
	@printf "  make refresh-seed       Refresh the committed seed from $(DEV_CONTAINER)\n"

$(VENV_DIR)/.deps-installed: requirements_dev.txt requirements_test.txt
	rm -rf $(VENV_DIR)
	python3 -m venv $(VENV_DIR)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements_dev.txt -r requirements_test.txt
	$(PYTHON) -m playwright install chromium
	@touch $@

install: $(VENV_DIR)/.deps-installed

setup: install setup-dev setup-test

setup-dev: install
	@test -d $(SEED_DIR) || (echo "Missing seed at $(SEED_DIR). Run make refresh-seed after creating $(DEV_CONTAINER)." && exit 1)
	$(PYTHON) scripts/homeassistant_seed.py sync --seed $(SEED_DIR) --target $(DEV_CONFIG_DIR) --clean
	$(PYTHON) scripts/homeassistant_seed.py patch-broadlink --target $(DEV_CONFIG_DIR) --rm4-mini-ip "$(BROADLINK_RM4_MINI_IP)" --rm4-pro-ip "$(BROADLINK_RM4_PRO_IP)"

setup-test: install clean-test-state
	@test -d $(SEED_DIR) || (echo "Missing seed at $(SEED_DIR). Run make refresh-seed after creating $(DEV_CONTAINER)." && exit 1)
	$(PYTHON) scripts/homeassistant_seed.py sync --seed $(SEED_DIR) --target $(TEST_CONFIG_DIR) --clean
	$(PYTHON) scripts/homeassistant_seed.py patch-broadlink --target $(TEST_CONFIG_DIR) --rm4-mini-ip "$(BROADLINK_RM4_MINI_IP)" --rm4-pro-ip "$(BROADLINK_RM4_PRO_IP)"


setup_broadlink: install
	@test -n "$(BROADLINK_RM4_MINI_IP)$(BROADLINK_RM4_PRO_IP)" || (echo "Set BROADLINK_RM4_MINI_IP and/or BROADLINK_RM4_PRO_IP before running make setup_broadlink." && exit 1)
	$(MAKE) stop-dev
	@test -d $(SEED_DIR) || (echo "Missing seed at $(SEED_DIR). Run make refresh-seed after creating $(DEV_CONTAINER)." && exit 1)
	$(PYTHON) scripts/homeassistant_seed.py sync --seed $(SEED_DIR) --target $(DEV_CONFIG_DIR) --clean
	$(PYTHON) scripts/homeassistant_seed.py patch-broadlink --target $(DEV_CONFIG_DIR) --rm4-mini-ip "$(BROADLINK_RM4_MINI_IP)" --rm4-pro-ip "$(BROADLINK_RM4_PRO_IP)"

stop-dev:
	@if [ -n "$$(docker ps -aq -f name=^/$(DEV_CONTAINER)$$)" ]; then docker rm -f $(DEV_CONTAINER); fi

stop-test:
	@if [ -n "$$(docker ps -aq -f name=^/$(TEST_CONTAINER)$$)" ]; then docker rm -f $(TEST_CONTAINER); fi

hass-dev: install
	$(MAKE) stop-dev
	$(MAKE) setup-dev
	docker run -d \
	  --name $(DEV_CONTAINER) \
	  -v "$(CURDIR)/$(DEV_CONFIG_DIR):/config" \
	  -v "$(CURDIR)/custom_components:$(CUSTOM_COMPONENTS_CONTAINER_DIR):ro" \
	  --privileged \
	  --restart=unless-stopped \
	  -e TZ=$(TZ) \
	  -e LANG=$(LANG) \
	  -e WHISPEER_TEST_MODE=$(WHISPEER_TEST_MODE) \
	  -p $(DEV_PORT):8123 \
	  $(HA_IMAGE)

hass-test: install
	$(MAKE) stop-test
	$(MAKE) setup-test
	docker run -d \
	  --name $(TEST_CONTAINER) \
	  -v "$(CURDIR)/$(TEST_CONFIG_DIR):/config" \
	  -v "$(CURDIR)/custom_components:$(CUSTOM_COMPONENTS_CONTAINER_DIR):ro" \
	  --privileged \
	  --restart=no \
	  -e TZ=$(TZ) \
	  -e LANG=$(LANG) \
	  -e WHISPEER_TEST_MODE=$(WHISPEER_TEST_MODE) \
	  -p $(TEST_PORT):8123 \
	  $(HA_IMAGE)

wait-dev: install
	$(PYTHON) scripts/wait_for_homeassistant.py --base-url http://localhost:$(DEV_PORT) --container-name $(DEV_CONTAINER)

wait-test: install
	$(PYTHON) scripts/wait_for_homeassistant.py --base-url http://localhost:$(TEST_PORT) --container-name $(TEST_CONTAINER)

dev: install
	$(MAKE) hass-dev
	$(MAKE) wait-dev

r: dev

clean-test-state:
	rm -f .pytest-cache/whispeer-storage-state.json

test_backend: install
	WHISPEER_LIVE_REPORT=1 \
	$(PYTHON) -m pytest $(BACKEND_PYTEST_TARGETS) -m "$(BACKEND_MARK_EXPR)" -q -s -rs $(PYTEST_ARGS)

test_frontend: install
	$(MAKE) hass-test
	$(MAKE) wait-test
	WHISPEER_BASE_URL=http://localhost:$(TEST_PORT) \
	WHISPEER_WS_URL=ws://localhost:$(TEST_PORT)/api/websocket \
	WHISPEER_CONTAINER_NAME=$(TEST_CONTAINER) \
	WHISPEER_BROWSER=$(WHISPEER_BROWSER) \
	WHISPEER_HEADED=$(EFFECTIVE_WHISPEER_HEADED) \
	WHISPEER_SLOWMO_MS=$(WHISPEER_SLOWMO_MS) \
	WHISPEER_TIMEOUT_MS=$(WHISPEER_TIMEOUT_MS) \
	WHISPEER_STEP_DELAY_MS=$(WHISPEER_STEP_DELAY_MS) \
	WHISPEER_E2E_START_AT="$(WHISPEER_E2E_START_AT)" \
	WHISPEER_E2E_STOP_AFTER="$(WHISPEER_E2E_STOP_AFTER)" \
	WHISPEER_PRESERVE_STATE=$(WHISPEER_PRESERVE_STATE) \
	WHISPEER_LIVE_REPORT=1 \
	$(PYTHON) -m pytest $(FRONTEND_PYTEST_TARGETS) -m "$(FRONTEND_MARK_EXPR)" -q -s -rs $(PYTEST_ARGS)

test_frontend_dev: install
	$(MAKE) hass-dev
	$(MAKE) wait-dev
	WHISPEER_BASE_URL=http://localhost:$(DEV_PORT) \
	WHISPEER_WS_URL=ws://localhost:$(DEV_PORT)/api/websocket \
	WHISPEER_CONTAINER_NAME=$(DEV_CONTAINER) \
	WHISPEER_BROWSER=$(WHISPEER_BROWSER) \
	WHISPEER_HEADED=$(EFFECTIVE_WHISPEER_HEADED) \
	WHISPEER_SLOWMO_MS=$(WHISPEER_SLOWMO_MS) \
	WHISPEER_TIMEOUT_MS=$(WHISPEER_TIMEOUT_MS) \
	WHISPEER_STEP_DELAY_MS=$(WHISPEER_STEP_DELAY_MS) \
	WHISPEER_E2E_START_AT="$(WHISPEER_E2E_START_AT)" \
	WHISPEER_E2E_STOP_AFTER="$(WHISPEER_E2E_STOP_AFTER)" \
	WHISPEER_PRESERVE_STATE=1 \
	WHISPEER_LIVE_REPORT=1 \
	$(PYTHON) -m pytest $(FRONTEND_PYTEST_TARGETS) -m "$(FRONTEND_MARK_EXPR)" -q -s -rs $(PYTEST_ARGS)

test: install
	@headless=0; \
	for arg in $(MAKECMDGOALS) $(MAKEFLAGS); do \
	  if [ "$$arg" = "--headless" ]; then headless=1; fi; \
	done; \
	if [ "$$headless" = "1" ]; then \
	  $(MAKE) test_backend PYTEST_ARGS="$(PYTEST_ARGS)" WHISPEER_HEADED=0; \
	  $(MAKE) test_frontend PYTEST_ARGS="$(PYTEST_ARGS)" WHISPEER_PRESERVE_STATE=0 WHISPEER_HEADED=0; \
	else \
	  $(MAKE) test_backend PYTEST_ARGS="$(PYTEST_ARGS)"; \
	  $(MAKE) test_frontend PYTEST_ARGS="$(PYTEST_ARGS)" WHISPEER_PRESERVE_STATE=0; \
	fi

refresh-seed:
	@test -n "$$(docker ps -aq -f name=^/$(DEV_CONTAINER)$$)" || (echo "Container $(DEV_CONTAINER) does not exist." && exit 1)
	@if [ -n "$$(docker ps -q -f name=^/$(DEV_CONTAINER)$$)" ]; then docker stop $(DEV_CONTAINER); fi
	rm -rf $(SEED_DIR)
	mkdir -p $(SEED_DIR)
	docker cp $(DEV_CONTAINER):/config/. $(SEED_DIR)/
	$(PYTHON) scripts/homeassistant_seed.py curate --target $(SEED_DIR)
