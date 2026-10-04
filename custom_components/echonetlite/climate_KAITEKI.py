"""KAITEKI climate entity."""

import logging

from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
)
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


class KaitekiZoneGroup:
    """Manage climate entities belonging to one KAITEKI device."""

    def __init__(self, grouping):
        """Initialize the zone group."""
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
        Get an attribute from the entity responsible for a zone.

        If that entity no longer exists, fall back in the order
        zone 1 -> zone 2 -> zone 3.
        """
        entity = self.get_entity_for_zone(zone)

        if entity is not None:
            return getattr(entity, attribute)

        # Fallback for an entity that was removed/disabled by the user.
        for fallback_zone in (1, 2, 3):
            entity = self.get_entity_for_zone(fallback_zone)

            if entity is not None:
                return getattr(entity, attribute)

        return None


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

    @property
    def target_temperature(self):
        """Return the target temperature for this entity."""
        return self._get_zone_value("TargetTemp")

    @property
    def fan_mode(self):
        """Return the fan mode for this entity."""
        return self._get_zone_value("AirFlow")

    @property
    def zone_status(self):
        """Return the status for this entity."""
        return self._get_zone_value("Status")

    @property
    def zone_program_operation(self):
        """Return the program operation value for this entity."""
        return self._get_zone_value("ProgramOperation")

    def _get_zone_value(self, suffix):
        """Return the value for the first physical zone represented by this entity."""
        zone = self.zones[0]
        return self.coordinator.data.get(f"zone{zone}{suffix}")

    async def async_set_temperature(self, **kwargs):
        """Set the target temperature for this zone group."""
        hvac_mode = kwargs.get(ATTR_HVAC_MODE)

        if hvac_mode is not None:
            # hvac_mode is handled by the common climate implementation.
            await self.async_set_hvac_mode(hvac_mode)

        temperature = kwargs.get(ATTR_TEMPERATURE)

        if temperature is None:
            return

        temperature = self._normalize_settemp(temperature)

        # F1 construction/SET is intentionally not implemented yet.
        #
        # The next step will collect:
        #
        #   zone1TargetTemp
        #   zone2TargetTemp
        #   zone3TargetTemp
        #
        # from the three physical zones, replace the values belonging to
        # self.zones, and send the resulting F1.
        raise NotImplementedError(
            "KAITEKI F1 temperature SET is not implemented yet"
        )

    async def async_set_fan_mode(self, fan_mode):
        """Set the fan mode for this zone group."""
        # F1 construction/SET is intentionally not implemented yet.
        raise NotImplementedError(
            "KAITEKI F1 fan mode SET is not implemented yet"
        )


def create_kaiteki_climate_entities(coordinator, config):
    """
    Create KAITEKI climate entities according to zoneGrouping.

    Returns:
        List of KAITEKI climate entities.
    """
    grouping = coordinator.data.get("zoneGrouping")

    if grouping not in ZONE_GROUPINGS:
        _LOGGER.warning(
            "Unknown KAITEKI zoneGrouping: 0x%02X",
            grouping if grouping is not None else 0,
        )
        return []

    zone_group = KaitekiZoneGroup(ZONE_GROUPINGS[grouping])

    return [
        EchonetKaitekiClimate(
            coordinator,
            config,
            zones=zones,
            zone_group=zone_group,
        )
        for zones in ZONE_GROUPINGS[grouping]
    ]
