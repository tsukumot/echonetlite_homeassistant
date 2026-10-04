"""KAITEKI climate entity."""

import logging

from homeassistant.components.climate.const import ATTR_HVAC_MODE
from homeassistant.const import ATTR_TEMPERATURE

from .climate import EchonetClimate

_LOGGER = logging.getLogger(__name__)


# 0x30: zone 1 / zone 2 / zone 3
# 0x31: zone 1+2 / zone 3
# 0x32: zone 1+3 / zone 2
# 0x33: zone 1 / zone 2+3
# 0x34: zone 1+2+3
ZONE_GROUPINGS = {
    0x30: ((1,), (2,), (3,)),
    0x31: ((1, 2), (3,)),
    0x32: ((1, 3), (2,)),
    0x33: ((1,), (2, 3)),
    0x34: ((1, 2, 3),),
}


STATUS_TO_BYTE = {
    "off": 0x30,
    "on": 0x31,
    "keep": 0x32,
}

AIRFLOW_TO_BYTE = {
    "low": 0x31,
    "high": 0x32,
    "auto": 0x41,
}

PROGRAM_OPERATION_TO_BYTE = {
    "off": 0x30,
    "timer1": 0x31,
    "timer2": 0x32,
    "timer3": 0x33,
}


class KaitekiZoneGroup:
    """Manage the climate entities belonging to one KAITEKI device."""

    def __init__(self, coordinator, grouping):
        """Initialize the zone group."""
        self.coordinator = coordinator
        self.grouping = grouping
        self.entities = []

    def add(self, entity):
        """Register an entity."""
        self.entities.append(entity)

    def get_entity_for_zone(self, zone):
        """Return the entity responsible for a physical zone."""
        for entity in self.entities:
            if zone in entity.zones:
                return entity

        return None

    def get_value(self, zone, attribute):
        """
        Return a value for a physical zone.

        If the corresponding entity no longer exists, use the first
        available zone in the order zone 1 -> zone 2 -> zone 3.
        """
        entity = self.get_entity_for_zone(zone)

        if entity is not None:
            return getattr(entity, attribute)

        for fallback_zone in (1, 2, 3):
            entity = self.get_entity_for_zone(fallback_zone)
            if entity is not None:
                return getattr(entity, attribute)

        return None

    def _current_f1(self):
        """Return the currently received F1 dictionary."""
        f1 = self.coordinator.data.get(0xF1)

        if not isinstance(f1, dict):
            return {}

        return f1

    def _get_unknown(self, zone, index):
        """Return an unknown F1 byte from the last received value."""
        key = f"unknown{zone}-{index}"
        value = self._current_f1().get(key)

        if value is None:
            return 0

        return value

    def build_f1(self, overrides=None):
        """
        Build the complete F1 EDT.

        Values not present in overrides are taken from the current
        climate entities. Unknown bytes are preserved from the received F1.
        """
        overrides = overrides or {}

        data = {}

        for zone in (1, 2, 3):
            data[f"zone{zone}Status"] = self.get_value(
                zone, "zone_status"
            )
            data[f"zone{zone}TargetTemp"] = self.get_value(
                zone, "target_temperature"
            )
            data[f"zone{zone}AirFlow"] = self.get_value(
                zone, "fan_mode"
            )
            data[f"zone{zone}ProgramOperation"] = self.get_value(
                zone, "zone_program_operation"
            )

            for index in (1, 2, 3):
                data[f"unknown{zone}-{index}"] = self._get_unknown(
                    zone, index
                )

        data.update(overrides)

        edt = bytearray()

        for zone in (1, 2, 3):
            status = data[f"zone{zone}Status"]
            target_temp = data[f"zone{zone}TargetTemp"]
            airflow = data[f"zone{zone}AirFlow"]
            program = data[f"zone{zone}ProgramOperation"]

            edt.append(STATUS_TO_BYTE[status])
            edt.append(int(target_temp))
            edt.append(AIRFLOW_TO_BYTE[airflow])

            edt.append(data[f"unknown{zone}-1"])
            edt.append(data[f"unknown{zone}-2"])
            edt.append(data[f"unknown{zone}-3"])

            edt.append(PROGRAM_OPERATION_TO_BYTE[program])

        return bytes(edt)

    async def async_set_f1(self, overrides=None):
        """Send a complete F1 SET."""
        edt = self.build_f1(overrides)

        mes = {
            "EPC": 0xF1,
            "PDC": len(edt),
            "EDT": edt,
        }

        await self.coordinator.async_set_and_verify(
            [0xF1],
            self.coordinator._instance.setMessages([mes]),
        )


class EchonetKaitekiClimate(EchonetClimate):
    """Representation of a KAITEKI climate zone/group."""

    def __init__(self, coordinator, config, zones, zone_group):
        """Initialize the KAITEKI climate entity."""
        super().__init__(coordinator, config)

        self.zones = tuple(zones)
        self.zone_group = zone_group

        suffix = "zone-" + "-".join(str(zone) for zone in self.zones)
        self._attr_unique_id = self._build_unique_id(suffix)

        zone_name = "+".join(str(zone) for zone in self.zones)
        self._attr_name = f"{self._device_name} Zone {zone_name}"

        zone_group.add(self)

    def _get_zone_value(self, suffix):
        """Return a value for the representative physical zone."""
        zone = self.zones[0]

        f1 = self.coordinator.data.get(0xF1)

        if not isinstance(f1, dict):
            return None

        return f1.get(f"zone{zone}{suffix}")

    @property
    def target_temperature(self):
        """Return the target temperature."""
        return self._get_zone_value("TargetTemp")

    @property
    def fan_mode(self):
        """Return the current fan mode."""
        return self._get_zone_value("AirFlow")

    @property
    def zone_status(self):
        """Return the current zone status."""
        return self._get_zone_value("Status")

    @property
    def zone_program_operation(self):
        """Return the current program operation."""
        return self._get_zone_value("ProgramOperation")

    async def async_set_temperature(self, **kwargs):
        """Set the target temperature for this zone group."""
        hvac_mode = kwargs.get(ATTR_HVAC_MODE)

        if hvac_mode is not None:
            await super().async_set_hvac_mode(hvac_mode)

        temperature = kwargs.get(ATTR_TEMPERATURE)

        if temperature is None:
            return

        temperature = self._normalize_settemp(temperature)

        overrides = {}

        for zone in self.zones:
            overrides[f"zone{zone}TargetTemp"] = temperature

        await self.zone_group.async_set_f1(overrides)

    async def async_set_fan_mode(self, fan_mode):
        """Set the fan mode for this zone group."""
        overrides = {}

        for zone in self.zones:
            overrides[f"zone{zone}AirFlow"] = fan_mode

        await self.zone_group.async_set_f1(overrides)


def create_kaiteki_climate_entities(coordinator, config):
    """Create KAITEKI climate entities according to zoneGrouping."""
    f2 = coordinator.data.get(0xF2)

    if not isinstance(f2, dict):
        _LOGGER.warning("KAITEKI F2 data is unavailable")
        return []

    grouping = f2.get("zoneGrouping")

    if grouping not in ZONE_GROUPINGS:
        _LOGGER.warning(
            "Unknown KAITEKI zoneGrouping: %s",
            grouping,
        )
        return []

    zone_group = KaitekiZoneGroup(
        coordinator,
        ZONE_GROUPINGS[grouping],
    )

    return [
        EchonetKaitekiClimate(
            coordinator,
            config,
            zones=zones,
            zone_group=zone_group,
        )
        for zones in ZONE_GROUPINGS[grouping]
    ]
