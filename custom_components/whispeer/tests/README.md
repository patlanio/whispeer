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
- Playwright coverage for the Whispeer panel, including modal smoke, real device creation, RF fast-learn flows, default-domain add-command coverage for every supported command type, and SmartIR community-code imports for `climate`, `fan`, `media_player`, and `light`

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

Run these commands from `custom_components/whispeer`.

Create the virtual environment:

```bash
python3 -m venv .venv-tests
```

Install the minimum test dependencies:

```bash
.venv-tests/bin/python -m pip install pytest pytest-cov
```

Install the browser-driven test dependencies when you want websocket integration and E2E coverage:

```bash
.venv-tests/bin/python -m pip install playwright
.venv-tests/bin/python -m playwright install chromium
```

Run the current suite:

```bash
.venv-tests/bin/python -m pytest tests
```

Run the websocket integration tests:

```bash
WHISPEER_TEST_MODE=1 .venv-tests/bin/python -m pytest tests/test_websocket_integration.py -m integration
```

Run the headed Playwright smoke test and slow the browser down so the flow is easy to watch:

```bash
WHISPEER_TEST_MODE=1 .venv-tests/bin/python -m pytest tests/test_e2e_panel.py -m e2e --whispeer-headed --whispeer-slowmo-ms 250
```

Run only the RF fast-learn browser scenario:

```bash
WHISPEER_TEST_MODE=1 .venv-tests/bin/python -m pytest tests/test_e2e_panel.py -m rf_fast --whispeer-headed --whispeer-slowmo-ms 250
```

Run the expanded browser suite with the current runtime defaults:

```bash
WHISPEER_BASE_URL=http://localhost:8125 WHISPEER_WS_URL=ws://localhost:8125/api/websocket .venv-tests/bin/python -m pytest tests/test_e2e_panel.py -m e2e -vv -rs
```

## Notes

- `pytest-cov` is required because the parent repository pytest configuration adds `--cov=custom_components.whispeer`.
- The current unit tests do not require a full Home Assistant runtime.
- `WHISPEER_TEST_MODE=1` is only needed when running websocket or end-to-end tests against a real Home Assistant instance.
- The current runtime defaults assume `homeassistant-dev` on `http://localhost:8125`; override them with the pytest options or env vars below if your dev instance changes.
- The Playwright flow persists a browser storage state file at `--whispeer-storage-state` so the first login can be reused across runs.
- The integration and E2E tests reuse Playwright as the websocket transport so there is no second websocket client dependency to maintain.
- Browser tests run headless by default. Use `--whispeer-headed` when you want to watch the run locally.
- On Linux without `DISPLAY` or `WAYLAND_DISPLAY`, a requested headed run falls back to headless automatically so the suite still runs in remote shells and CI.
- If websocket or E2E tests suddenly start skipping with `Enable WHISPEER_TEST_MODE=1 in the Home Assistant runtime`, inspect the container with `docker exec homeassistant-dev sh -lc 'printenv | grep ^WHISPEER_TEST_MODE='`.
- The expanded E2E panel flow now creates two default-domain devices, one IR and one RF at `433.92`, and exercises `button`, `light`, `switch`, `numeric`, `group`, and `options` learn flows using deterministic Broadlink mocks.
- The SmartIR import scenario is mocked at the browser network layer so the `community code 1000` coverage stays deterministic and does not depend on GitHub availability.

Example for future integration or E2E runs:

```bash
WHISPEER_TEST_MODE=1 .venv-tests/bin/python -m pytest tests -m integration
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

The next implementation slice should expand Playwright coverage further into BLE scanner scenarios and BLE command-management flows.
