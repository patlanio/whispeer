# TODO list

Lista de tareas por hacer por la IA, cuando termines una marcala como terminada con una x, un humano vendra a revisar y eliminarla de la lista cuando todo este OK

## Comandos y generalidades de test
Cambia los nombres de los comandos, no quiero fastest, ni e2e_master ni e2e_panel, no se que significa, quiero:
- [x] make test (acepta `-- --headless`)
- [x] make test_backend
- [x] make test_frontend (acepta `-- --headless`)


## Renombra los tests ejecutados por 'make test'

Deben ser mas explicitos

### Backend (fastest)
- [x] 'custom_components/whispeer/tests/test_runtime_config.py::test_build_test_settings_prefers_options_over_environment'
	- change to -> `Checks that 'build_test_settings' prioritizes explicit options over environment variables and sets correct values and types.`
- [x] 'custom_components/whispeer/tests/test_runtime_config.py::test_build_test_settings_uses_defaults_when_values_missing'
	- change to -> `Verifies that defaults are used when options and environment values are missing.`
- [x] 'custom_components/whispeer/tests/test_test_support.py::test_harness_configures_interfaces_and_send_override'
	- change to -> `Ensures 'WhispeerTestHarness' applies interface configuration and provides a 'send_command' override when configured.`
- [x] 'custom_components/whispeer/tests/test_test_support.py::test_harness_consumes_matching_learn_override_once'
	- change to -> `Confirms the learn override queue is matched and consumed exactly once for a given device/interface.`
- [x] 'custom_components/whispeer/tests/test_test_support.py::test_harness_runs_default_session_override_transitions'
	- change to -> `Validates session override transition flow and resulting journal entries during a simulated learning session.`

### Integración (websocket)
- [x] 'tests/test_websocket_integration.py::test_test_state_reports_expected_shape' — forma esperada del estado del test
	- change to -> `Asserts the WebSocket 'get_state' response contains expected fields (enabled, journal, learning sessions, interfaces).`
- [x] 'tests/test_websocket_integration.py::test_test_commands_configure_and_reset_round_trip' — configure/reset round-trip
	- change to -> `Tests that the 'configure' command applies settings (interfaces, send_command), that the journal increases, and that 'reset' clears queues and config.`

### E2E / Playwright (RSpec-style)
- [x] panel shell / opens /whispeer
	- change to -> `Opens the Whispeer panel in Home Assistant and confirms the panel loads successfully.`
- [x] panel shell / shows add device button
	- change to -> `Verifies the "Add device" button is visible in the panel shell UI.`
- [x] device modal / renders core fields
	- change to -> `Opens the add-device modal and checks core input fields (name, domain, type) render correctly.`
- [x] device modal / rf conditionals
	- change to -> `Selects RF type and checks that the frequency field is visible and community code input is hidden.`
- [x] device modal / ir conditionals
	- change to -> `Selects IR type and checks that community code input appears while frequency is hidden.`
- [x] device modal / ble interfaces
	- change to -> `Selects BLE type and verifies available HCI BLE interfaces are listed in the modal.`
- [x] device creation / default ir device
	- change to -> `Creates a default IR device with all default command types and ensures it appears in the device list.`
- [x] device creation / default rf device
	- change to -> `Creates a default RF device, sets frequency, and verifies the device persists with correct frequency.`
- [x] device creation / community climate
	- change to -> `Imports a SmartIR community climate code ('1000') and saves a climate device via the modal.`
- [x] device creation / community fan
	- change to -> `Imports a SmartIR community fan code ('1000') and saves a fan device via the modal.`
- [x] device creation / community light
	- change to -> `Imports a SmartIR community light code ('1000') and saves a light device via the modal.`
- [x] device creation / community media player
	- change to -> `Imports a SmartIR community media player code ('1000') and saves a media player device via the modal.`
- [x] device creation / ble fan
	- change to -> `Creates a BLE fan device using the BLE scanner modal and learned advertisements for speed cells.`
- [x] device creation / ble default xmas
	- change to -> `Creates a BLE "xmas" default device by learning on/off advertisements and saving the device.`
- [x] device creation / expected device list
	- change to -> `Asserts the panel shows the full set of expected device names after creation.`
- [x] panel actions / default power command
	- change to -> `Executes the default 'power' command on a device and checks for a success toast in the UI.`
- [x] panel actions / default state sync
	- change to -> `Verifies device card toggles and option group controls are visible and update as expected.`
- [x] other devices / lists all created devices
	- change to -> `Opens Home Assistant's "Other Devices" view and ensures every created device is listed.`
- [x] other devices / shows expected controls
	- change to -> `Checks the official UI exposes switches, spinbuttons, and other controls for the devices.`
- [x] other devices / changes values from official ui
	- change to -> `Interacts with official UI controls to toggle device switches and click media player control.`
- [x] state reflection / captures call_service events
	- change to -> `Reads the test state via WebSocket to confirm 'call_service' events are present in the journal.`
- [x] state reflection / panel reflects other devices changes
	- change to -> `Confirms changes made in the official UI are reflected in the Whispeer panel device toggles.`

## Secciones

Esto es fuera del UI de whispeer pero hay que hacer pruebas

- [x] El sidebar y el header de home assistant: añade una prueba de que "Whispeer" esta en el sidebar y que en el header dice "Whispeer - Remote control made simple"

Estas son las secciones relevantes que tiene la UI de whispeer

- "panel shell" no dice nada, algo como "vista general" es mejor, renombralo
- header: debe tener el logo, el nombre, el boton de config y el boton "add device"
- cards: muestra la lista de cards, cuando esta vacia muestra un texto 

Usa una convecion para testing coherente: e2e_master simplemente no hace sentido semanticamente.


## Cambia la forma de hacer clicks y redirecciones

En pasadas iteraciones te vi hacer muchas faramallas para intentar tener todo dentro de un solo run y en una unica ventana, vi que te ibas al url del iframe, tuviste muchos problemas con el sidebar y cosas similares; todo debe ir a base de clicks, por ejemplo, cuando inicia la carga revisa que estes en /whispeer, haz todas las pruebas que van en esa pagina (no irte al url del iframe). Cuando necesites irte a revisar la UI de home assistant debes revisar si el sidebar esta abierto y abrirlo en caso de que no, entonces hacer click en overview (o vista general, por alguna razon esta en español el container de test lo cual esta mal); eso te muestra otra pantalla que tiene "areas", haz click en "devices" (o dispositivos, de nuevo, en español, eso esta mal). En esa pagina ya tienes todos los dispositivos creados. Añade un test de que todos dispositivos creados en el UI de whispeer estan presentes.

Para volver a /whispeer es igual, checa si el sidebar esta abierto y haz click en whispeer.

- [x] Terminado

## Authentication

Me molesta mucho tener que ver el login form, no se puede hacer un token de session antes de iniciar la prueba e inyectarlo antes de iniciar asi no perdemos tiempo. O de plano, si es mejor y si se puede, que la instancia no requiera contraseña.

- [x] Terminado

## Re haz la imagen seed de docker

Crea una instancia de prueba desde cero, configurala en ingles, con nombre "Whis-Home", con la integracion broadlink integrada por defecto y con el usuario john y password doe. Todo eso usala como seed. Pero se cuidadoso, hay mucha paja en la base. Las carpetas blueprints, script o los archivos scenes.yamls o secrets.yaml no parecen ser necesarios para tenerlos en seed y que sean parte del codebase. Copia solo lo que da la "identidad" del hogar, la integracion y el usuario. Todo lo demas es paja.

- [x] Terminado

- [x] Haz un commit al terminar
