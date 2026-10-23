from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
import uuid

from homeassistant.components.light import ATTR_HS_COLOR
from homeassistant.const import SERVICE_TURN_OFF, SERVICE_TURN_ON, STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util, slugify
from homeassistant.util.color import color_hs_to_RGB

from .const import LOGGER, STORAGE_KEY, STORAGE_VERSION

RuleType = dict[str, Any]


class RuleManager:
    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._store = Store[dict[str, list[RuleType]]](hass, STORAGE_VERSION, STORAGE_KEY)
        self._rules: list[RuleType] = []
        self._unsub_tracker: Callable[[], None] | None = None
        self._target_light: str | None = None
        self._notification_devices: list[str] = []
        self._notification_services: list[str] = []
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
            self._unsub_tracker = async_track_state_change_event(self.hass, entity_ids, self._handle_state_change)

    @callback
    def _handle_state_change(self, event: Any) -> None:
        if self.debug:
            entity_id = event.data.get("entity_id", "?")
            new_state = event.data.get("new_state")
            state = new_state.state if new_state else "unknown"
            LOGGER.debug("State change: %s → %s, re-evaluating", entity_id, state)
        self.hass.async_create_task(self._evaluate())

    async def _evaluate(self) -> None:
        if not self._target_light:
            return

        active: list[RuleType] = []
        for rule in self._rules:
            if not rule.get("enabled", True):
                if self.debug:
                    LOGGER.debug("  Skip disabled: %s", rule["name"])
                continue
            state = self.hass.states.get(rule["entity_id"])
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
            await self._async_send_live_update(None)
            self._notify_update()
            return

        winner = min(active, key=lambda r: r["priority"])
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
        await self._async_send_live_update(winner)
        self._notify_update()

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
            if device and device.name:
                service_name = slugify(f"mobile_app_{device.name}")
                services.add(f"notify.{service_name}")

        for service in services:
            domain, service_name = service.split(".", 1)
            if not self.hass.services.has_service(domain, service_name):
                if self.debug:
                    LOGGER.debug("Notification service is unavailable: %s", service)
                continue
            await self.hass.services.async_call(domain, service_name, service_data, blocking=True)

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
