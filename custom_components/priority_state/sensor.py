from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .rule_manager import RuleManager


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    manager: RuleManager = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([PriorityStateSensor(manager)])


class PriorityStateSensor(SensorEntity):
    _attr_name = "Priority State Rules"
    _attr_icon = "mdi:lightbulb-group-outline"

    def __init__(self, manager: RuleManager) -> None:
        self._manager = manager
        self._attr_unique_id = f"{manager.entry_id}_rules"
        self._manager.register_update_callback(self._handle_update)

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def state(self) -> str:
        enabled = [r for r in self._manager.rules if r.get("enabled", True)]
        return str(len(enabled))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        target_light = self._manager.target_light
        light_state = (
            self.hass.states.get(target_light) if target_light else None
        )
        winner = self._get_winner()

        return {
            "rules": [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "entity_id": r["entity_id"],
                    "priority": r["priority"],
                    "hs_color": r["hs_color"],
                    "enabled": r.get("enabled", True),
                }
                for r in self._manager.rules
            ],
            "target_light": target_light,
            "light_state": light_state.state if light_state else None,
            "light_color": light_state.attributes.get("hs_color")
            if light_state and light_state.attributes
            else None,
            "winner": winner["id"] if winner else None,
            "winner_name": winner["name"] if winner else None,
            "debug": self._manager.debug,
        }

    def _get_winner(self) -> dict[str, Any] | None:
        if not self._manager.target_light:
            return None
        active: list[dict[str, Any]] = []
        for rule in self._manager.rules:
            if not rule.get("enabled", True):
                continue
            state = self.hass.states.get(rule["entity_id"])
            if state and state.state == "on":
                active.append(rule)
        if not active:
            return None
        return min(active, key=lambda r: r["priority"])
