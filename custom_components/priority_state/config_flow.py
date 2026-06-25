from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    ColorRGBSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)
from homeassistant.util.color import color_hs_to_RGB, color_RGB_to_hs

import logging

from .const import DOMAIN, LOGGER


class PriorityStateConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=user_input.get("name", "Priority State"),
                data={"target_light": user_input["target_light"]},
            )

        data_schema = vol.Schema(
            {
                vol.Optional("name", default="Priority State"): str,
                vol.Required("target_light"): EntitySelector(
                    EntitySelectorConfig(domain="light")
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            return self.async_update_entry(entry, data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(
                    "target_light", default=entry.data["target_light"]
                ): EntitySelector(EntitySelectorConfig(domain="light")),
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PriorityStateOptionsFlowHandler(config_entry)


class PriorityStateOptionsFlowHandler(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._rule_id: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        manager = self.hass.data[DOMAIN][self._config_entry.entry_id]

        if user_input is not None:
            action = user_input.get("next_step_id")
            if action == "change_light":
                return await self.async_step_change_light()
            if action == "add_rule":
                return await self.async_step_add_rule()
            if action == "select_edit_rule":
                return await self.async_step_select_edit_rule()
            if action == "clear_rules":
                return await self.async_step_clear_rules()
            if action == "debug_mode":
                return await self.async_step_debug_mode()
            return self.async_abort(reason="unknown_action")

        menu_options: dict[str, str] = {
            "change_light": "Change target light",
            "add_rule": "Add a new rule",
        }
        if manager.rules:
            menu_options["select_edit_rule"] = "Edit rules"
            menu_options["clear_rules"] = "Clear all rules"

        debug_on = self._config_entry.data.get("debug", False)
        menu_options["debug_mode"] = (
            "Disable debug mode" if debug_on else "Enable debug mode"
        )

        return self.async_show_menu(
            step_id="init",
            menu_options=menu_options,
            description_placeholders={
                "target_light": self._config_entry.data.get("target_light", "Not set"),
                "rule_count": str(len(manager.rules)),
            },
        )

    def _rule_label(self, rule: dict[str, Any]) -> str:
        rgb = color_hs_to_RGB(*rule["hs_color"])
        hex_color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        priority = int(rule["priority"])
        disabled = "" if rule.get("enabled", True) else " [DISABLED]"
        return (
            f"[{hex_color}] {rule['name']}"
            f"{disabled}"
            f" (P{priority}) - {rule['entity_id']}"
        )

    async def async_step_select_edit_rule(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        manager = self.hass.data[DOMAIN][self._config_entry.entry_id]

        if user_input is not None:
            self._rule_id = user_input["rule_id"]
            return await self.async_step_edit_rule()

        rules_sorted = sorted(
            manager.rules, key=lambda r: r["priority"]
        )
        return self.async_show_form(
            step_id="select_edit_rule",
            data_schema=vol.Schema(
                {
                    vol.Required("rule_id"): vol.In(
                        {r["id"]: self._rule_label(r) for r in rules_sorted}
                    )
                }
            ),
        )

    async def async_step_debug_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            new_data = {
                **self._config_entry.data,
                "debug": user_input["debug"],
            }
            self.hass.config_entries.async_update_entry(
                self._config_entry, data=new_data
            )
            manager = self.hass.data[DOMAIN][self._config_entry.entry_id]
            if user_input["debug"]:
                LOGGER.setLevel(logging.DEBUG)
            else:
                LOGGER.setLevel(logging.INFO)
            manager.async_debug_updated()
            return await self.async_step_init()

        current = self._config_entry.data.get("debug", False)
        return self.async_show_form(
            step_id="debug_mode",
            data_schema=vol.Schema(
                {
                    vol.Required("debug", default=current): BooleanSelector(),
                }
            ),
        )

    async def async_step_change_light(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            new_data = {
                **self._config_entry.data,
                "target_light": user_input["target_light"],
            }
            self.hass.config_entries.async_update_entry(
                self._config_entry, data=new_data
            )
            manager = self.hass.data[DOMAIN][self._config_entry.entry_id]
            manager.target_light = user_input["target_light"]
            return await self.async_step_init()

        return self.async_show_form(
            step_id="change_light",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "target_light",
                        default=self._config_entry.data.get("target_light"),
                    ): EntitySelector(EntitySelectorConfig(domain="light")),
                }
            ),
        )

    async def async_step_add_rule(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            manager = self.hass.data[DOMAIN][self._config_entry.entry_id]
            if manager.is_entity_id_used(user_input["entity_id"]):
                return self.async_show_form(
                    step_id="add_rule",
                    data_schema=self._add_rule_schema(),
                    errors={"entity_id": "duplicate_entity"},
                )
            hs = color_RGB_to_hs(*user_input["rgb_color"])
            await manager.async_add_rule(
                name=user_input["name"],
                entity_id=user_input["entity_id"],
                priority=user_input["priority"],
                hue=hs[0],
                saturation=hs[1],
                enabled=user_input.get("enabled", True),
            )
            return await self.async_step_init()

        return self.async_show_form(
            step_id="add_rule",
            data_schema=self._add_rule_schema(),
        )

    @staticmethod
    def _add_rule_schema() -> vol.Schema:
        return vol.Schema(
            {
                vol.Required("name"): TextSelector(),
                vol.Required("entity_id"): EntitySelector(),
                vol.Required("priority"): NumberSelector(
                    NumberSelectorConfig(
                        min=0, max=100, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required("rgb_color", default=[255, 255, 255]): ColorRGBSelector(),
                vol.Optional("enabled", default=True): BooleanSelector(),
            }
        )

    async def async_step_edit_rule(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        manager = self.hass.data[DOMAIN][self._config_entry.entry_id]
        rule = next(
            (r for r in manager.rules if r["id"] == self._rule_id), None
        )
        if not rule:
            LOGGER.warning("Rule %s not found for editing", self._rule_id)
            return await self.async_step_init()

        if user_input is not None:
            if user_input.get("delete_this_rule"):
                await manager.async_remove_rule(self._rule_id)
            else:
                if manager.is_entity_id_used(
                    user_input["entity_id"], exclude_rule_id=self._rule_id
                ):
                    return self.async_show_form(
                        step_id="edit_rule",
                        data_schema=self._edit_rule_schema(rule),
                        errors={"entity_id": "duplicate_entity"},
                    )
                hs = color_RGB_to_hs(*user_input["rgb_color"])
                await manager.async_update_rule(
                    self._rule_id,
                    name=user_input["name"],
                    entity_id=user_input["entity_id"],
                    priority=user_input["priority"],
                    hue=hs[0],
                    saturation=hs[1],
                    enabled=user_input.get("enabled", True),
                )
            return await self.async_step_init()

        return self.async_show_form(
            step_id="edit_rule",
            data_schema=self._edit_rule_schema(rule),
        )

    def _edit_rule_schema(self, rule: dict[str, Any]) -> vol.Schema:
        default_rgb = list(color_hs_to_RGB(*rule["hs_color"]))
        return vol.Schema(
            {
                vol.Required("name", default=rule["name"]): TextSelector(),
                vol.Required(
                    "entity_id", default=rule["entity_id"]
                ): EntitySelector(),
                vol.Required(
                    "priority", default=rule["priority"]
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0, max=100, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required("rgb_color", default=default_rgb): ColorRGBSelector(),
                vol.Optional(
                    "enabled", default=rule.get("enabled", True)
                ): BooleanSelector(),
                vol.Optional("delete_this_rule", default=False): BooleanSelector(),
            }
        )

    async def async_step_clear_rules(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            manager = self.hass.data[DOMAIN][self._config_entry.entry_id]
            await manager.async_clear_rules()
            return await self.async_step_init()

        return self.async_show_form(
            step_id="clear_rules",
            data_schema=vol.Schema({}),
        )
