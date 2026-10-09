"""KAITEKI multi-zone climate entities."""
import logging
import asyncio
from homeassistant.exceptions import HomeAssistantError
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE
from pychonet.HomeAirConditioner import ENL_HVAC_MODE

from .climate import EchonetClimate

_LOGGER = logging.getLogger(__name__)
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
    def __init__(self, coordinator, grouping):
        self.coordinator = coordinator
        self.grouping = grouping
        self.entities = []
        self._lock = asyncio.Lock()

    def add(self, entity):
        self.entities.append(entity)

    def _build_f1(self, overrides=None):
        """現在のF1(0130.pyのデコード結果)をベースに、上書き分だけ変えて21バイト化する。"""
        overrides = overrides or {}
        f1 = self.coordinator.data.get(0xF1)
        if not isinstance(f1, dict):
            raise HomeAssistantError("F1 data is unavailable")

        edt = bytearray()
        for zone in (1, 2, 3):
            def pick(suffix):
                key = f"zone{zone}{suffix}"
                value = overrides.get(key)
                return f1.get(key) if value is None else value

            status = pick("Status")
            temp = pick("TargetTemp")
            airflow = pick("AirFlow")
            program = pick("ProgramOperation")
            unknowns = [f1.get(f"unknown{zone}-{i}") for i in (1, 2, 3)]

            if status not in STATUS_TO_BYTE:
                raise HomeAssistantError(f"Unknown zone{zone}Status: {status!r}")
            if airflow not in AIRFLOW_TO_BYTE:
                raise HomeAssistantError(f"Unknown zone{zone}AirFlow: {airflow!r}")
            if program not in PROGRAM_OPERATION_TO_BYTE:
                raise HomeAssistantError(f"Unknown zone{zone}ProgramOperation: {program!r}")
            if temp is None or any(u is None for u in unknowns):
                raise HomeAssistantError(f"Incomplete F1 data for zone {zone}")

            edt.extend((
                STATUS_TO_BYTE[status],
                int(temp),
                AIRFLOW_TO_BYTE[airflow],
                *unknowns,
                PROGRAM_OPERATION_TO_BYTE[program],
            ))
        return bytes(edt)  # 21 bytes

    async def async_set_f1(self, overrides=None):
        async with self._lock:
            edt = self._build_f1(overrides)
            ok = await self.coordinator._instance.setMessage(
                0xF1, int.from_bytes(edt, "big"), pdc=len(edt)
            )
            if not ok:
                raise HomeAssistantError("KAITEKI did not acknowledge F1")

            await asyncio.sleep(0.5)
            confirmed = await self.coordinator.poll_pychonet_specific([0xF1])
            if confirmed:
                self.coordinator.async_set_updated_data(
                    {**(self.coordinator.data or {}), **confirmed}
                )

class EchonetKaitekiClimate(EchonetClimate):
    """Climate entity representing one KAITEKI zone group."""

    _MODE_B0 = {
        0x42: HVACMode.COOL,
        0x43: HVACMode.HEAT,
        0x44: HVACMode.DRY,
    }

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
    def zone_status(self):
        return self._zone_value("Status")

    @property
    def is_on(self):
        return self._zone_value("Status") == "on"

    def _operation_hvac_mode(self):
        """Return the current common 0xB0 operation mode as an HA HVAC mode."""
        value = self.coordinator.data.get(0xB0)

        # The normal decoder supplies the symbolic value.  Accept the raw EPC
        # values too, so this remains usable if a device/decoder exposes bytes.
        if isinstance(value, dict):
            value = value.get("value", value.get("mode"))
        if isinstance(value, (bytes, bytearray)) and value:
            value = value[0]

        if isinstance(value, str):
            normalized = value.lower().replace("-", "_").replace(" ", "_")
            return {
                "auto": HVACMode.HEAT_COOL,
                "cooling": HVACMode.COOL,
                "heating": HVACMode.HEAT,
                "dehumidification": HVACMode.DRY,
            }.get(normalized)

        return {
            0x41: HVACMode.HEAT_COOL,
            0x42: HVACMode.COOL,
            0x43: HVACMode.HEAT,
            0x44: HVACMode.DRY,
        }.get(value)

    @property
    def hvac_mode(self):
        if self._zone_value("Status") == "on":
            return self._MODE_B0.get(self.coordinator.data.get(0xB0))
        return HVACMode.OFF 

    @property
    def hvac_modes(self):
        modes = [HVACMode.OFF]
        current = self._MODE_B0.get(self.coordinator.data.get(0xB0))
        if current is not None:
            modes.append(current)
        return modes

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
        else:
            await self.async_turn_on()   # 0xB0 は触らない

    @property
    def hvac_action(self):
        status = self._zone_value("Status")
        if status == "keep":
            return HVACAction.IDLE
        if status == "on":
            return {
                0x42: HVACAction.COOLING,
                0x43: HVACAction.HEATING,
                0x44: HVACAction.DRYING,
            }.get(self.coordinator.data.get(0xB0), HVACAction.IDLE)
        return HVACAction.OFF

    @property
    def extra_state_attributes(self):
        attrs = dict(super().extra_state_attributes or {})
        attrs["zone_status"] = self._zone_value("Status")   # on / off / keep
        attrs["zone_program_operation"] = self.zone_program_operation
        return attrs

    async def async_set_temperature(self, **kwargs):
        overrides = {}
        hvac_mode = kwargs.get(ATTR_HVAC_MODE)
        if hvac_mode == HVACMode.OFF:
            return await self.async_turn_off()
        if hvac_mode is not None:
            overrides.update({f"zone{z}Status": "on" for z in self.zones})

        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            t = self._normalize_settemp(temperature)
            overrides.update({f"zone{z}TargetTemp": t for z in self.zones})

        if overrides:
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
        # OFFを送る。タイマー有効時にkeepへ移行するかは機器側が決める。
        overrides = {f"zone{zone}Status": "off" for zone in self.zones}
        await self.zone_group.async_set_f1(overrides)

"""
        # Turn off, or enter Keep when program operation is active.
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
"""

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
