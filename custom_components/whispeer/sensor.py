"""Sensor platform for Whispeer device entities."""
from homeassistant.components.sensor import SensorEntity

from .const import DOMAIN
from .entity import WhispeerEntity


async def async_setup_entry(hass, entry, async_add_devices):
    """Setup sensors reflecting Whispeer devices."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    devices = await coordinator.api.async_get_devices()
    entities = [
        WhispeerDeviceSensor(coordinator, entry, device)
        for device in devices
    ]
    if entities:
        async_add_devices(entities)


class WhispeerDeviceSensor(WhispeerEntity, SensorEntity):
    def __init__(self, coordinator, config_entry, device: dict):
        super().__init__(coordinator, config_entry)
        self._device = device

    @property
    def unique_id(self):
        return f"{self.config_entry.entry_id}_device_{self._device.get('id')}"

    @property
    def name(self):
        return self._device.get("name") or "Whispeer Device"

    @property
    def native_value(self):
        return self._device.get("type") or "unknown"

    @property
    def extra_state_attributes(self):
        attrs = {
            "device_id": self._device.get("id"),
            "type": self._device.get("type"),
        }
        emitter = self._device.get("emitter") or {}
        if emitter:
            attrs["emitter"] = emitter
        return attrs
