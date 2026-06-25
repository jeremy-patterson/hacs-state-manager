from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.color import color_RGB_to_hs

from .const import DOMAIN, LOGGER
from .rule_manager import RuleManager


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = RuleManager(hass, entry.entry_id)
    await manager.async_load()
    manager.target_light = entry.data["target_light"]

    if entry.data.get("debug", False):
        LOGGER.setLevel(logging.DEBUG)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = manager

    await manager.async_start()

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    async def async_handle_add_rule(call: Any) -> None:
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

    async def async_handle_remove_rule(call: Any) -> None:
        await manager.async_remove_rule(call.data["rule_id"])

    async def async_handle_update_rule(call: Any) -> None:
        data = dict(call.data)
        rule_id = data.pop("rule_id")
        if "entity_id" in data and manager.is_entity_id_used(
            data["entity_id"], exclude_rule_id=rule_id
        ):
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

    async def async_handle_clear_rules(call: Any) -> None:
        await manager.async_clear_rules()

    hass.services.async_register(
        DOMAIN, "add_rule", async_handle_add_rule
    )
    hass.services.async_register(
        DOMAIN, "remove_rule", async_handle_remove_rule
    )
    hass.services.async_register(
        DOMAIN, "update_rule", async_handle_update_rule
    )
    hass.services.async_register(
        DOMAIN, "clear_rules", async_handle_clear_rules
    )

    await hass.http.async_register_static_paths([
        StaticPathConfig(
            f"/{DOMAIN}/priority-state-card.js",
            hass.config.path("custom_components", DOMAIN, "www", "priority-state-card.js"),
            cache_headers=False,
        ),
    ])

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = hass.data[DOMAIN].pop(entry.entry_id, None)
    if manager:
        await manager.async_stop()
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True
