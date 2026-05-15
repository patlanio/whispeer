# Whispeer test-suite foundation

This directory holds the shared runtime configuration and the first unit tests for the unified suite.

The current development target is the `homeassistant-dev` container, which serves Home Assistant on `http://localhost:8125` in this workspace.

## Current scope

The current suite is backend-focused and covers:

- runtime setting resolution
- the env-gated test harness overrides
- simulated learning-session transitions

The current integration slice also includes:

- websocket integration tests for `whispeer/test/get_state`, `whispeer/test/configure`, and `whispeer/test/reset`
- a pytest-describe Playwright suite that runs the full Whispeer E2E flow in one shared Chromium session, one browser window, and one tab, with Page Objects for the Whispeer panel and Home Assistant `other-devices` view

The integration exposes test-only websocket hooks when `WHISPEER_TEST_MODE=1` is set in the Home Assistant runtime.

For the integration and browser-driven tests in this repository, make sure `homeassistant-dev` is started with `WHISPEER_TEST_MODE=1` in the container environment before running pytest.

In the current workspace runtime, `homeassistant-dev` already has `WHISPEER_TEST_MODE=1` in the persisted container `Config.Env`, so the flag survives normal container restarts. No compose or launcher definition was found in the checked paths, so if that container is recreated from scratch the variable still has to be set by whatever external process creates it.

Available test control websocket commands:

- `whispeer/test/get_state`
- `whispeer/test/configure`
- `whispeer/test/reset`

Current override groups supported by `whispeer/test/configure`:

- `interfaces`
- `learn.queue`
- `frequency.queue`
- `send_command`
- `ble_scan`
- `ble_emit`

## How to run the current tests

Run the full repository test flow from the repository root:

```bash
make test
```

That single command does the following in order:

- runs the backend-only pytest layer
- recreates `hass-test`
- waits for Home Assistant on `http://localhost:8126`
- runs websocket integration plus the one-window, one-tab Playwright suite

For debugging, these narrower entrypoints are still available from the repository root:

```bash
make test_backend
make test_frontend
make test_frontend -- --headless
make test_frontend_dev
```

If you want to run the Python commands directly instead of `make`, create the repository virtual environment and install dependencies first:

```bash
python3 -m venv .venv-whispeer
.venv-whispeer/bin/python -m pip install -r requirements_dev.txt -r requirements_test.txt
.venv-whispeer/bin/python -m playwright install chromium
```

Run only a slice of the RSpec-style suite:

```bash
WHISPEER_E2E_START_AT=device_creation.default.ir \
WHISPEER_E2E_STOP_AFTER=other_devices.shows_expected_controls \
.venv-tests/bin/python -m pytest tests/test_whispeer_rspec.py -s -vv
```

## Notes

- `pytest-cov` is required because the parent repository pytest configuration adds `--cov=custom_components.whispeer`.
- The current unit tests do not require a full Home Assistant runtime.
- `WHISPEER_TEST_MODE=1` is only needed when running websocket or end-to-end tests against a real Home Assistant instance.
- The current runtime defaults assume `homeassistant-dev` on `http://localhost:8125`; override them with the pytest options or env vars below if your dev instance changes.
- The Playwright flow now injects a Home Assistant session token before the first navigation, so the visible login form is skipped and the suite starts already authenticated.
- The browser flow always navigates through the Home Assistant shell by clicking the sidebar, Overview, Devices, and Whispeer routes instead of loading the panel iframe URL directly.
- The integration tests use token-based websocket calls and the browser flow reuses a single Playwright page for the full run.
- Browser tests run headless by default. Use `--whispeer-headed` when you want to watch the run locally.
- `WHISPEER_SLOWMO_MS` slows each browser action; `WHISPEER_STEP_DELAY_MS` adds a pause between checklist items so the run is easier to follow.
- `WHISPEER_PRESERVE_STATE=1` disables the automatic test-harness reset before and after a test. This is useful when running the master checklist against `hass-dev` and you want to inspect the created devices afterward.
- The current E2E source of truth is `e2e_checklist.py`, and the executable suite lives in `tests/test_whispeer_rspec.py` using `pytest-describe` plus Page Objects under `tests/pages/`.
- On Linux without `DISPLAY` or `WAYLAND_DISPLAY`, a requested headed run falls back to headless automatically so the suite still runs in remote shells and CI.
- If websocket or E2E tests suddenly start skipping with `Enable WHISPEER_TEST_MODE=1 in the Home Assistant runtime`, inspect the container with `docker exec homeassistant-dev sh -lc 'printenv | grep ^WHISPEER_TEST_MODE='`.
- The current RSpec-style flow creates one default IR device, one default RF device at `433.92`, four SmartIR community devices from local `1000` fixtures, and two BLE devices learned through the scanner UI.
- SmartIR imports are mocked at the browser network layer from committed local `1000` fixtures, so the coverage stays deterministic and does not depend on GitHub availability.

Example for a focused browser slice:

```bash
WHISPEER_E2E_START_AT=device_creation.community.climate \
WHISPEER_E2E_STOP_AFTER=other_devices.changes_values \
make test_frontend
```

## Runtime configuration

Runtime configuration can be changed without editing tests by using pytest options or environment variables:

- `--whispeer-base-url` or `WHISPEER_BASE_URL`
- `--whispeer-ws-url` or `WHISPEER_WS_URL`
- `--whispeer-username` or `WHISPEER_USERNAME`
- `--whispeer-password` or `WHISPEER_PASSWORD`
- `--whispeer-storage-state` or `WHISPEER_STORAGE_STATE`
- `--whispeer-container-name` or `WHISPEER_CONTAINER_NAME`
- `--whispeer-container-host` or `WHISPEER_CONTAINER_HOST`
- `--whispeer-headed` or `WHISPEER_HEADED`
- `--whispeer-browser` or `WHISPEER_BROWSER`
- `--whispeer-slowmo-ms` or `WHISPEER_SLOWMO_MS`
- `--whispeer-timeout-ms` or `WHISPEER_TIMEOUT_MS`
- `--whispeer-live-report` or `WHISPEER_LIVE_REPORT`
- `WHISPEER_STEP_DELAY_MS`
- `WHISPEER_E2E_START_AT`
- `WHISPEER_E2E_STOP_AFTER`
- `WHISPEER_PRESERVE_STATE`

The next implementation slice should expand Playwright coverage further into BLE scanner scenarios and BLE command-management flows.
