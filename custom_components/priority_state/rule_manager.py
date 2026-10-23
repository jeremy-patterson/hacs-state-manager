from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import inspect
from typing import Any
import uuid

from homeassistant.components.light import ATTR_HS_COLOR
from homeassistant.const import SERVICE_TURN_OFF, SERVICE_TURN_ON, STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util, slugify
from homeassistant.util.color import color_hs_to_RGB

from .const import LOGGER, STORAGE_KEY, STORAGE_LOCK_KEY, STORAGE_VERSION

RuleType = dict[str, Any]


class RuleManager:
    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._store = Store[dict[str, Any]](hass, STORAGE_VERSION, STORAGE_KEY)
        self._rules: list[RuleType] = []
        self._unsub_tracker: Callable[[], None] | None = None
        self._unsub_notification_refresh: Callable[[], None] | None = None
        self._target_light: str | None = None
        self._target_light_expectation: tuple[str, list[float] | None] | None = None
        self._notification_devices: list[str] = []
        self._notification_services: list[str] = []
        self._update_callbacks: list[Callable[[], None]] = []
        self._evaluation_generation = 0
        self._evaluation_lock = asyncio.Lock()
        self._storage_lock = hass.data.setdefault(STORAGE_LOCK_KEY, asyncio.Lock())

    @property
    def rules(self) -> list[RuleType]:
        return list(self._rules)

    @property
    def target_light(self) -> str | None:
        return self._target_light

    @target_light.setter
    def target_light(self, value: str) -> None:
        self._target_light = value
        self._target_light_expectation = None
        self._update_tracking()

    @property
    def notification_services(self) -> list[str]:
        return list(self._notification_services)

    @notification_services.setter
    def notification_services(self, value: list[str]) -> None:
        self._notification_services = [
            service if service.startswith("notify.") else f"notify.{service}" for service in value if service
        ]

    @property
    def notification_devices(self) -> list[str]:
        return list(self._notification_devices)

    @notification_devices.setter
    def notification_devices(self, value: list[str]) -> None:
        self._notification_devices = list(value)

    @property
    def debug(self) -> bool:
        entry = self.hass.config_entries.async_get_entry(self.entry_id)
        return bool(entry and entry.data.get("debug", False))

    def async_debug_updated(self) -> None:
        self._notify_update()

    def is_entity_id_used(self, entity_id: str, exclude_rule_id: str | None = None) -> bool:
        return any(r["entity_id"] == entity_id and r["id"] != exclude_rule_id for r in self._rules)

    def register_update_callback(self, callback: Callable[[], None]) -> None:
        self._update_callbacks.append(callback)

    @callback
    def _notify_update(self) -> None:
        for cb in self._update_callbacks:
            cb()

    async def async_load(self) -> None:
        async with self._storage_lock:
            data = await self._async_load_store()
            if not data:
                return

            entries = data.get("entries")
            migrate_storage = False
            if isinstance(entries, dict):
                stored_rules = entries.get(self.entry_id, [])
                self._rules = stored_rules if isinstance(stored_rules, list) else []
            elif "rules" in data:
                # Migrate the original single-entry storage format on the next save.
                stored_rules = data["rules"]
                self._rules = stored_rules if isinstance(stored_rules, list) else []
                migrate_storage = True

            migrated_rules = False
            for rule in self._rules:
                if "enabled" not in rule or rule["enabled"] is None:
                    rule["enabled"] = True
                    migrated_rules = True
            if migrate_storage or migrated_rules:
                await self._async_save_locked(data)

    async def async_save(self) -> None:
        async with self._storage_lock:
            data = await self._async_load_store() or {}
            await self._async_save_locked(data)

    async def _async_load_store(self) -> dict[str, Any] | None:
        result = self._store.async_load()
        if inspect.isawaitable(result):
            return await result
        return result

    async def _async_save_locked(self, data: dict[str, Any]) -> None:
        entries = data.get("entries")
        if not isinstance(entries, dict):
            entries = {}
            if isinstance(data.get("rules"), list):
                entries[self.entry_id] = data["rules"]
        entries[self.entry_id] = self._rules
        await self._store.async_save({"entries": entries})

    async def async_start(self) -> None:
        self._update_tracking()
        self._unsub_notification_refresh = async_track_time_interval(
            self.hass,
            self._handle_notification_refresh,
            timedelta(minutes=1),
        )
        await self._evaluate()
        self._notify_update()

    async def async_stop(self) -> None:
        if self._unsub_tracker:
            self._unsub_tracker()
            self._unsub_tracker = None
        if self._unsub_notification_refresh:
            self._unsub_notification_refresh()
            self._unsub_notification_refresh = None

    def _update_tracking(self) -> None:
        if self._unsub_tracker:
            self._unsub_tracker()
            self._unsub_tracker = None

        entity_ids = {r["entity_id"] for r in self._rules if r.get("entity_id")}
        if self._target_light:
            entity_ids.add(self._target_light)
        if entity_ids:
            self._unsub_tracker = async_track_state_change_event(self.hass, list(entity_ids), self._handle_state_change)

    @callback
    def _handle_state_change(self, event: Any) -> None:
        entity_id = event.data.get("entity_id")
        rule_entity_ids = {r["entity_id"] for r in self._rules if r.get("entity_id")}
        if (
            entity_id == self._target_light
            and entity_id not in rule_entity_ids
            and self._target_light_state_matches(event.data.get("new_state"))
        ):
            return

        if self.debug:
            entity_id = entity_id or "?"
            new_state = event.data.get("new_state")
            state = new_state.state if new_state else "unknown"
            LOGGER.debug("State change: %s → %s, re-evaluating", entity_id, state)
        self._evaluation_generation += 1
        self.hass.async_create_task(self._evaluate(self._evaluation_generation, notify=entity_id != self._target_light))

    @callback
    def _handle_notification_refresh(self, _now: datetime) -> None:
        self.hass.async_create_task(self._async_refresh_notification())

    async def _evaluate(self, generation: int | None = None, notify: bool = True) -> None:
        if generation is None:
            self._evaluation_generation += 1
            generation = self._evaluation_generation

        async with self._evaluation_lock:
            await self._async_evaluate(generation, notify)

    async def _async_evaluate(self, generation: int, notify: bool = True) -> None:
        if not self._target_light or generation != self._evaluation_generation:
            return

        active: list[RuleType] = []
        for rule in self._rules:
            if not rule.get("enabled", True):
                if self.debug:
                    LOGGER.debug("  Skip disabled: %s", rule["name"])
                continue
            state = self.hass.states.get(rule["entity_id"])
            if state and state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                if self.debug:
                    LOGGER.debug("Rule %s is temporarily unavailable; retaining current output", rule["name"])
                return
            is_on = state and state.state == STATE_ON
            if self.debug:
                LOGGER.debug(
                    "  Rule %s (P%d): %s = %s",
                    rule["name"],
                    int(rule["priority"]),
                    rule["entity_id"],
                    "on" if is_on else "off",
                )
            if is_on:
                active.append(rule)

        if not active:
            self._target_light_expectation = (STATE_OFF, None)
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
            if generation != self._evaluation_generation:
                return
            if notify:
                await self._async_send_live_update(None)
            self._notify_update()
            return

        winner = min(active, key=lambda r: r["priority"])
        tied_rules = [rule for rule in active if rule["priority"] == winner["priority"]]
        if len(tied_rules) > 1:
            LOGGER.warning(
                "Rules %s share priority %s; using the first configured rule: %s",
                ", ".join(rule["name"] for rule in tied_rules),
                winner["priority"],
                winner["name"],
            )
        self._target_light_expectation = (STATE_ON, list(winner["hs_color"]))
        if self.debug:
            LOGGER.debug(
                "Winner: %s (P%d, HS=%s) → %s",
                winner["name"],
                int(winner["priority"]),
                winner["hs_color"],
                self._target_light,
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
        if generation != self._evaluation_generation:
            return
        if notify:
            await self._async_send_live_update(winner)
        self._notify_update()

    async def _async_refresh_notification(self) -> None:
        async with self._evaluation_lock:
            if not self._target_light:
                return

            active: list[RuleType] = []
            for rule in self._rules:
                if not rule.get("enabled", True):
                    continue
                state = self.hass.states.get(rule["entity_id"])
                if state and state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    return
                if state and state.state == STATE_ON:
                    active.append(rule)

            winner = min(active, key=lambda r: r["priority"]) if active else None
            await self._async_send_live_update(winner)

    def _target_light_state_matches(self, state: Any | None) -> bool:
        if state is None or self._target_light_expectation is None:
            return False

        expected_state, expected_color = self._target_light_expectation
        if state.state != expected_state:
            return False
        if expected_color is None:
            return True

        actual_color = state.attributes.get(ATTR_HS_COLOR)
        return actual_color == expected_color

    async def _async_send_live_update(self, winner: RuleType | None) -> None:
        if not self._target_light:
            return

        light_state = self.hass.states.get(self._target_light)
        light_name = light_state.name if light_state else self._target_light.split(".", 1)[-1].replace("_", " ").title()
        tag = f"priority-state-{self.entry_id}"
        if winner:
            active_state = self.hass.states.get(winner["entity_id"])
            duration = self._format_active_duration(active_state.last_changed if active_state else None)
            message = f"{winner['name']} · active for {duration}"
            rgb = color_hs_to_RGB(*winner["hs_color"])
            color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            notification_icon = self._entity_notification_icon(active_state)
        else:
            message = "No active rules"
            color = "#808080"
            notification_icon = self._entity_notification_icon(light_state)

        service_data = (
            {
                "title": f"Priority State · {light_name}",
                "message": message,
                "data": {
                    "tag": tag,
                    "live_update": True,
                    # Android supports persistent notifications; iOS may still allow dismissal.
                    "persistent": True,
                    "alert_once": True,
                    "notification_icon": notification_icon,
                    "notification_icon_color": color,
                    "color": color,
                },
            }
            if winner
            else {
                "message": "clear_notification",
                "data": {"tag": tag},
            }
        )
        services = set(self._notification_services)
        device_registry = dr.async_get(self.hass)
        for device_id in self._notification_devices:
            device = device_registry.async_get(device_id)
            if not device:
                LOGGER.warning("Configured notification device is unavailable: %s", device_id)
                continue

            mobile_app_id = next(
                (identifier for integration, identifier in device.identifiers if integration == "mobile_app"),
                None,
            )
            if device.name:
                # Mobile App notification services are based on the device name.
                service_name = slugify(f"mobile_app_{device.name}")
                services.add(f"notify.{service_name}")
            elif mobile_app_id:
                service_name = f"mobile_app_{mobile_app_id}"
                services.add(f"notify.{service_name}")

        for service in services:
            domain, service_name = service.split(".", 1)
            if not self.hass.services.has_service(domain, service_name):
                if self.debug:
                    LOGGER.debug("Notification service is unavailable: %s", service)
                continue
            try:
                await self.hass.services.async_call(domain, service_name, service_data, blocking=True)
            except HomeAssistantError:
                LOGGER.warning("Failed to deliver notification using %s", service, exc_info=True)

    @staticmethod
    def _format_active_duration(started: datetime | None) -> str:
        if started is None:
            return "an unknown amount of time"

        seconds = max(0, int((dt_util.utcnow() - started).total_seconds()))
        if seconds < 60:
            return "less than a minute"
        minutes = seconds // 60
        if minutes < 60:
            unit = "minute" if minutes == 1 else "minutes"
            return f"{minutes} {unit}"
        hours, remaining_minutes = divmod(minutes, 60)
        if hours < 24:
            unit = "hour" if hours == 1 else "hours"
            if remaining_minutes:
                minute_unit = "minute" if remaining_minutes == 1 else "minutes"
                return f"{hours} {unit} {remaining_minutes} {minute_unit}"
            return f"{hours} {unit}"
        days, remaining_hours = divmod(hours, 24)
        day_unit = "day" if days == 1 else "days"
        if remaining_hours:
            hour_unit = "hour" if remaining_hours == 1 else "hours"
            return f"{days} {day_unit} {remaining_hours} {hour_unit}"
        return f"{days} {day_unit}"

    @staticmethod
    def _entity_notification_icon(state: Any | None) -> str:
        if state is None:
            return "mdi:lightbulb"

        icon = state.attributes.get("icon")
        if icon:
            return icon

        device_class_icons = {
            "battery": "mdi:battery",
            "carbon_monoxide": "mdi:smoke-detector-alert",
            "connectivity": "mdi:connection",
            "door": "mdi:door",
            "garage_door": "mdi:garage",
            "humidity": "mdi:water-percent",
            "light": "mdi:lightbulb",
            "lock": "mdi:lock",
            "motion": "mdi:motion-sensor",
            "moisture": "mdi:water-alert",
            "occupancy": "mdi:account-check",
            "opening": "mdi:door-open",
            "plug": "mdi:power-plug",
            "power": "mdi:flash",
            "presence": "mdi:account-check",
            "problem": "mdi:alert-circle",
            "running": "mdi:play-circle",
            "safety": "mdi:shield-check",
            "smoke": "mdi:smoke-detector-alert",
            "sound": "mdi:volume-high",
            "temperature": "mdi:thermometer",
            "update": "mdi:package-up",
            "vibration": "mdi:vibrate",
            "window": "mdi:window-open",
        }
        device_class = state.attributes.get("device_class")
        if device_class in device_class_icons:
            return device_class_icons[device_class]

        domain = state.entity_id.split(".", 1)[0]
        return {
            "binary_sensor": "mdi:checkbox-marked-circle",
            "cover": "mdi:window-shutter",
            "fan": "mdi:fan",
            "light": "mdi:lightbulb",
            "media_player": "mdi:play-circle",
            "sensor": "mdi:gauge",
            "switch": "mdi:toggle-switch",
        }.get(domain, "mdi:lightbulb")

    async def async_refresh(self) -> None:
        await self._evaluate()

    async def async_add_rule(
        self,
        name: str,
        entity_id: str,
        priority: int,
        hue: float,
        saturation: float,
        enabled: bool = True,
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
        original_count = len(self._rules)
        self._rules = [r for r in self._rules if r["id"] != rule_id]
        if len(self._rules) == original_count:
            LOGGER.warning("Rule not found for removal: %s", rule_id)
            return
        await self.async_save()
        self._update_tracking()
        if self.debug:
            LOGGER.debug("Rule removed: id=%s", rule_id)
        await self._evaluate()
        self._notify_update()

    async def async_update_rule(self, rule_id: str, **kwargs: Any) -> None:
        found = False
        for rule in self._rules:
            if rule["id"] != rule_id:
                continue
            found = True
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
        if not found:
            LOGGER.warning("Rule not found for update: %s", rule_id)
            return
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
