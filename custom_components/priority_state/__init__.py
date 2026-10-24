from __future__ import annotations

import logging

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.color import color_RGB_to_hs

from .const import DOMAIN, LOGGER
from .rule_manager import RuleManager

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})

    async def async_handle_add_rule(call: ServiceCall) -> None:
        manager = _manager_for_call(hass, call)
        if manager is None:
            return
        if manager.is_entity_id_used(call.data["entity_id"]):
            LOGGER.warning(
                "Rule for %s already exists — ignoring add_rule call",
                call.data["entity_id"],
            )
            return
        hs = color_RGB_to_hs(*call.data["rgb_color"])
        await manager.async_add_rule(
            name=call.data["name"],
            entity_id=call.data["entity_id"],
            priority=int(call.data["priority"]),
            hue=hs[0],
            saturation=hs[1],
            enabled=call.data.get("enabled", True),
        )

    async def async_handle_remove_rule(call: ServiceCall) -> None:
        manager = _manager_for_call(hass, call)
        if manager:
            await manager.async_remove_rule(call.data["rule_id"])

    async def async_handle_update_rule(call: ServiceCall) -> None:
        manager = _manager_for_call(hass, call)
        if manager is None:
            return
        data = dict(call.data)
        data.pop("entry_id", None)
        rule_id = data.pop("rule_id")
        if "entity_id" in data and manager.is_entity_id_used(data["entity_id"], exclude_rule_id=rule_id):
            LOGGER.warning(
                "Rule for %s already exists — ignoring update_rule call",
                data["entity_id"],
            )
            return
        if "rgb_color" in data:
            hs = color_RGB_to_hs(*data.pop("rgb_color"))
            data["hue"] = hs[0]
            data["saturation"] = hs[1]
        await manager.async_update_rule(rule_id, **data)

    async def async_handle_clear_rules(call: ServiceCall) -> None:
        manager = _manager_for_call(hass, call)
        if manager:
            await manager.async_clear_rules()

    hass.services.async_register(DOMAIN, "add_rule", async_handle_add_rule)
    hass.services.async_register(DOMAIN, "remove_rule", async_handle_remove_rule)
    hass.services.async_register(DOMAIN, "update_rule", async_handle_update_rule)
    hass.services.async_register(DOMAIN, "clear_rules", async_handle_clear_rules)

    if hass.http:
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    f"/{DOMAIN}/priority-state-card.js",
                    hass.config.path("custom_components", DOMAIN, "www", "priority-state-card.js"),
                    cache_headers=False,
                ),
            ]
        )
    return True


def _manager_for_call(hass: HomeAssistant, call: ServiceCall) -> RuleManager | None:
    managers: dict[str, RuleManager] = hass.data.get(DOMAIN, {})
    entry_id = call.data.get("entry_id")
    if entry_id:
        manager = managers.get(entry_id)
        if manager is None:
            LOGGER.warning("Unknown Priority State config entry: %s", entry_id)
        return manager
    if len(managers) == 1:
        return next(iter(managers.values()))
    LOGGER.error("Service call requires entry_id when multiple Priority State entries are configured")
    return None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = RuleManager(hass, entry.entry_id)
    await manager.async_load()
    manager.target_light = entry.data["target_light"]
    manager.notification_devices = entry.data.get("notification_devices", [])
    manager.notification_services = entry.data.get("notification_services", [])

    if entry.data.get("debug", False):
        LOGGER.setLevel(logging.DEBUG)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = manager

    await manager.async_start()

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    if "lovelace" in hass.data:
        await _async_register_card(hass)

    return True


async def _async_register_card(hass: HomeAssistant) -> None:
    try:
        resources = hass.data["lovelace"].resources
        existing = any(r.get("url", "").startswith(f"/{DOMAIN}/priority-state-card") for r in resources.async_items())
        if not existing:
            await resources.async_create_item(
                {
                    "res_type": "module",
                    "url": f"/{DOMAIN}/priority-state-card.js",
                }
            )
    except KeyError, TypeError, ValueError:
        pass


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = hass.data[DOMAIN].pop(entry.entry_id, None)
    if manager:
        await manager.async_stop()
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True
