"""KAITEKI multi-zone climate entities."""

from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode
from homeassistant.const import ATTR_TEMPERATURE
from pychonet.HomeAirConditioner import ENL_HVAC_MODE

from .climate import EchonetClimate


ZONE_GROUPINGS = {
    # 0x30: zone 1 / zone 2 / zone 3
    # 0x31: zone 1+2 / zone 3
    # 0x32: zone 1+3 / zone 2
    # 0x33: zone 1 / zone 2+3
    # 0x34: zone 1+2+3
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
    """Manage all climate entities belonging to one KAITEKI device."""

    def __init__(self, coordinator, grouping):
        self.coordinator = coordinator
        self.grouping = grouping
        self.entities = []

    def add(self, entity):
        """Register an active HA entity."""
        self.entities.append(entity)

    def _entity_for_zone(self, zone):
        """Return the active entity covering a physical zone."""
        for entity in self.entities:
            if zone in entity.zones:
                return entity
        return None

    def _value_for_zone(self, zone, attribute):
        """Read a value from the zone, falling back 1 -> 2 -> 3."""
        entity = self._entity_for_zone(zone)
        if entity is not None:
            return getattr(entity, attribute)

        for fallback_zone in (1, 2, 3):
            entity = self._entity_for_zone(fallback_zone)
            if entity is not None:
                return getattr(entity, attribute)

        return None

    def _f1_value(self, key):
        """Return a raw value retained by the F1 decoder."""
        f1 = self.coordinator.data.get(0xF1)
        if not isinstance(f1, dict):
            return None
        return f1.get(key)

    def _build_f1(self, overrides=None):
        """Build a complete F1 EDT from current entities plus overrides.

        A value of None in overrides means "keep the current value".
        Unknown F1 bytes are copied from the last received F1.
        """
        overrides = overrides or {}
        data = {}

        for zone in (1, 2, 3):
            for suffix, attribute in (
                ("Status", "zone_status"),
                ("TargetTemp", "target_temperature"),
                ("AirFlow", "fan_mode"),
                ("ProgramOperation", "zone_program_operation"),
            ):
                key = f"zone{zone}{suffix}"
                value = overrides.get(key)
                if value is None:
                    value = self._value_for_zone(zone, attribute)
                data[key] = value

            for index in (1, 2, 3):
                key = f"unknown{zone}-{index}"
                value = self._f1_value(key)
                if value is None:
                    raise ValueError(f"Current F1 does not contain {key}")
                data[key] = value

        edt = bytearray()
        for zone in (1, 2, 3):
            status = data[f"zone{zone}Status"]
            target_temp = data[f"zone{zone}TargetTemp"]
            airflow = data[f"zone{zone}AirFlow"]
            program = data[f"zone{zone}ProgramOperation"]

            if status not in STATUS_TO_BYTE:
                raise ValueError(f"Unknown zone{zone}Status: {status!r}")
            if airflow not in AIRFLOW_TO_BYTE:
                raise ValueError(f"Unknown zone{zone}AirFlow: {airflow!r}")
            if program not in PROGRAM_OPERATION_TO_BYTE:
                raise ValueError(
                    f"Unknown zone{zone}ProgramOperation: {program!r}"
                )
            if target_temp is None:
                raise ValueError(f"Current zone{zone}TargetTemp is unavailable")

            edt.extend(
                (
                    STATUS_TO_BYTE[status],
                    int(target_temp),
                    AIRFLOW_TO_BYTE[airflow],
                    data[f"unknown{zone}-1"],
                    data[f"unknown{zone}-2"],
                    data[f"unknown{zone}-3"],
                    PROGRAM_OPERATION_TO_BYTE[program],
                )
            )

        return bytes(edt)

    async def async_set_f1(self, overrides=None):
        """Send the complete F1 value and verify it with a targeted poll."""
        edt = self._build_f1(overrides)
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
    """Climate entity representing one KAITEKI zone group."""

    def __init__(self, coordinator, config, zones, zone_group):
        super().__init__(coordinator, config)
        self.zones = tuple(zones)
        self.zone_group = zone_group
        zone_group.add(self)

        zone_name = "+".join(str(zone) for zone in self.zones)
        self._attr_name = f"{self._device_name} Zone {zone_name}"
        self._attr_unique_id = self._build_unique_id(f"zone-{zone_name}")

        # KAITEKI airflow is carried by 0xF1 rather than the standard
        # ECHONET fan-speed EPC.
        self._attr_supported_features |= ClimateEntityFeature.FAN_MODE
        self._attr_fan_modes = list(AIRFLOW_TO_BYTE)

    def _zone_value(self, suffix):
        """Return a value for the first physical zone in this group."""
        f1 = self.coordinator.data.get(0xF1)
        if not isinstance(f1, dict):
            return None
        return f1.get(f"zone{self.zones[0]}{suffix}")

    @property
    def current_temperature(self):
        """Return the room temperature for the representative zone."""
        fa = self.coordinator.data.get(0xFA)
        if not isinstance(fa, dict):
            return super().current_temperature
        return fa.get(f"zone{self.zones[0]}Temp")

    @property
    def target_temperature(self):
        """Return the target temperature for this zone group."""
        return self._zone_value("TargetTemp")

    @property
    def fan_mode(self):
        """Return the airflow setting for this zone group."""
        return self._zone_value("AirFlow")

    @property
    def zone_program_operation(self):
        """Return the program operation for this zone group."""
        return self._zone_value("ProgramOperation")

    @property
    def is_on(self):
        """Return whether this zone is active, including the KAITEKI Keep state."""
        return self._zone_value("Status") in ("on", "keep")

    @property
    def hvac_mode(self):
        """Return HVAC mode, treating KAITEKI Keep like the shared 'other' mode.

        The integration's existing "その他" option is reused here:
        - as_idle: keep the last heat/cool/dry mode visible
        - otherwise: expose Keep as off

        Changing the HVAC mode uses the normal parent implementation, which
        writes 0x80/0xB0 and therefore naturally clears Keep.
        """
        if self._zone_value("Status") == "keep":
            if self.coordinator._user_options.get(ENL_HVAC_MODE) == "as_idle":
                return getattr(self, "_last_mode", HVACMode.OFF)
            return HVACMode.OFF
        return super().hvac_mode

    @property
    def hvac_action(self):
        """Return HVAC action, exposing KAITEKI Keep as idle when configured."""
        if self._zone_value("Status") == "keep":
            from homeassistant.components.climate.const import HVACAction
            if self.coordinator._user_options.get(ENL_HVAC_MODE) == "as_idle":
                return HVACAction.IDLE
            return HVACAction.OFF
        return super().hvac_action

    async def async_set_temperature(self, **kwargs):
        """Set target temperature for this zone group."""
        hvac_mode = kwargs.get(ATTR_HVAC_MODE)
        if hvac_mode is not None:
            await super().async_set_hvac_mode(hvac_mode)

        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        temperature = self._normalize_settemp(temperature)
        overrides = {
            f"zone{zone}TargetTemp": temperature for zone in self.zones
        }
        await self.zone_group.async_set_f1(overrides)

    async def async_set_fan_mode(self, fan_mode):
        """Set airflow for this zone group."""
        overrides = {f"zone{zone}AirFlow": fan_mode for zone in self.zones}
        await self.zone_group.async_set_f1(overrides)

    async def async_turn_on(self):
        """Turn on this zone group."""
        overrides = {f"zone{zone}Status": "on" for zone in self.zones}
        await self.zone_group.async_set_f1(overrides)

    async def async_turn_off(self):
        """Turn off, or enter Keep when program operation is active."""
        f1 = self.coordinator.data.get(0xF1)
        if not isinstance(f1, dict):
            raise ValueError("Current F1 data is unavailable")

        overrides = {}
        for zone in self.zones:
            program = f1.get(f"zone{zone}ProgramOperation")
            # The physical device uses the OFF command contextually:
            # only an active timer program enters Keep; otherwise power off.
            status = "keep" if program in ("timer1", "timer2", "timer3") else "off"
            overrides[f"zone{zone}Status"] = status

        await self.zone_group.async_set_f1(overrides)


def create_kaiteki_climate_entities(coordinator, config):
    """Create KAITEKI climate entities from F2 zoneGrouping."""
    f2 = coordinator.data.get(0xF2)
    if not isinstance(f2, dict):
        return []

    grouping = f2.get("zoneGrouping")
    zones = ZONE_GROUPINGS.get(grouping)
    if zones is None:
        return []

    zone_group = KaitekiZoneGroup(coordinator, zones)

    return [
        EchonetKaitekiClimate(
            coordinator,
            config,
            physical_zones,
            zone_group,
        )
        for physical_zones in zones
    ]
