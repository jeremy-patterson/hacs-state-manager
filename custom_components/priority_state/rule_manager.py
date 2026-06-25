from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any, Dict

from homeassistant.components.light import ATTR_HS_COLOR
from homeassistant.const import SERVICE_TURN_OFF, SERVICE_TURN_ON, STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from .const import DOMAIN, LOGGER, STORAGE_KEY, STORAGE_VERSION


RuleType = Dict[str, Any]


class RuleManager:
    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._store = Store[dict[str, list[RuleType]]](
            hass, STORAGE_VERSION, STORAGE_KEY
        )
        self._rules: list[RuleType] = []
        self._unsub_tracker: Callable[[], None] | None = None
        self._target_light: str | None = None
        self._update_callbacks: list[Callable[[], None]] = []

    @property
    def rules(self) -> list[RuleType]:
        return list(self._rules)

    @property
    def target_light(self) -> str | None:
        return self._target_light

    @target_light.setter
    def target_light(self, value: str) -> None:
        self._target_light = value

    @property
    def debug(self) -> bool:
        entry = self.hass.config_entries.async_get_entry(self.entry_id)
        return bool(entry and entry.data.get("debug", False))

    def async_debug_updated(self) -> None:
        self._notify_update()

    def is_entity_id_used(
        self, entity_id: str, exclude_rule_id: str | None = None
    ) -> bool:
        return any(
            r["entity_id"] == entity_id
            and r["id"] != exclude_rule_id
            for r in self._rules
        )

    def register_update_callback(
        self, callback: Callable[[], None]
    ) -> None:
        self._update_callbacks.append(callback)

    @callback
    def _notify_update(self) -> None:
        for cb in self._update_callbacks:
            cb()

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if data and "rules" in data:
            self._rules = data["rules"]
            migrated = False
            for rule in self._rules:
                if "enabled" not in rule or rule["enabled"] is None:
                    rule["enabled"] = True
                    migrated = True
            if migrated:
                await self.async_save()

    async def async_save(self) -> None:
        await self._store.async_save({"rules": self._rules})

    async def async_start(self) -> None:
        self._update_tracking()
        await self._evaluate()
        self._notify_update()

    async def async_stop(self) -> None:
        if self._unsub_tracker:
            self._unsub_tracker()
            self._unsub_tracker = None

    def _update_tracking(self) -> None:
        if self._unsub_tracker:
            self._unsub_tracker()
            self._unsub_tracker = None

        entity_ids = [r["entity_id"] for r in self._rules if r.get("entity_id")]
        if entity_ids:
            self._unsub_tracker = async_track_state_change_event(
                self.hass, entity_ids, self._handle_state_change
            )

    @callback
    def _handle_state_change(self, event: Any) -> None:
        if self.debug:
            entity_id = event.data.get("entity_id", "?")
            new_state = event.data.get("new_state")
            state = new_state.state if new_state else "unknown"
            LOGGER.debug(
                "State change: %s → %s, re-evaluating", entity_id, state
            )
        self.hass.async_create_task(self._evaluate())

    async def _evaluate(self) -> None:
        if not self._target_light:
            return

        active: list[RuleType] = []
        for rule in self._rules:
            if not rule.get("enabled", True):
                if self.debug:
                    LOGGER.debug(
                        "  Skip disabled: %s", rule["name"]
                    )
                continue
            state = self.hass.states.get(rule["entity_id"])
            is_on = state and state.state == STATE_ON
            if self.debug:
                LOGGER.debug(
                    "  Rule %s (P%d): %s = %s",
                    rule["name"], int(rule["priority"]),
                    rule["entity_id"], "on" if is_on else "off",
                )
            if is_on:
                active.append(rule)

        if not active:
            if self.debug:
                LOGGER.debug(
                    "No active rules → turning off %s",
                    self._target_light,
                )
            await self.hass.services.async_call(
                "light",
                SERVICE_TURN_OFF,
                {"entity_id": self._target_light},
                blocking=True,
            )
            self._notify_update()
            return

        winner = min(active, key=lambda r: r["priority"])
        if self.debug:
            LOGGER.debug(
                "Winner: %s (P%d, HS=%s) → %s",
                winner["name"], int(winner["priority"]),
                winner["hs_color"], self._target_light,
            )
        await self.hass.services.async_call(
            "light",
            SERVICE_TURN_ON,
            {
                "entity_id": self._target_light,
                ATTR_HS_COLOR: winner["hs_color"],
            },
            blocking=True,
        )
        self._notify_update()

    async def async_add_rule(
        self, name: str, entity_id: str, priority: int,
        hue: float, saturation: float, enabled: bool = True,
    ) -> RuleType:
        rule: RuleType = {
            "id": str(uuid.uuid4()),
            "name": name,
            "entity_id": entity_id,
            "priority": int(priority),
            "hs_color": [hue, saturation],
            "enabled": enabled,
        }
        self._rules.append(rule)
        await self.async_save()
        self._update_tracking()
        if self.debug:
            LOGGER.debug("Rule added: %s (entity=%s, P%d)", name, entity_id, int(priority))
        await self._evaluate()
        self._notify_update()
        return rule

    async def async_remove_rule(self, rule_id: str) -> None:
        self._rules = [r for r in self._rules if r["id"] != rule_id]
        await self.async_save()
        self._update_tracking()
        if self.debug:
            LOGGER.debug("Rule removed: id=%s", rule_id)
        await self._evaluate()
        self._notify_update()

    async def async_update_rule(self, rule_id: str, **kwargs: Any) -> None:
        for rule in self._rules:
            if rule["id"] != rule_id:
                continue
            if "name" in kwargs:
                rule["name"] = kwargs["name"]
            if "entity_id" in kwargs:
                rule["entity_id"] = kwargs["entity_id"]
            if "priority" in kwargs:
                rule["priority"] = int(kwargs["priority"])
            if "hue" in kwargs and "saturation" in kwargs:
                rule["hs_color"] = [kwargs["hue"], kwargs["saturation"]]
            if "enabled" in kwargs:
                rule["enabled"] = kwargs["enabled"]
            break
        await self.async_save()
        self._update_tracking()
        if self.debug:
            LOGGER.debug("Rule updated: id=%s", rule_id)
        await self._evaluate()
        self._notify_update()

    async def async_clear_rules(self) -> None:
        self._rules = []
        await self.async_save()
        self._update_tracking()
        if self.debug:
            LOGGER.debug("All rules cleared")
        await self._evaluate()
