from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.priority_state.const import DOMAIN

SOURCE_USER = config_entries.SOURCE_USER


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def register_light_services(hass: HomeAssistant):
    hass.states.async_set("light.test", "off")
    hass.states.async_set("light.other", "off")

    async def mock_turn_on(call):
        pass

    async def mock_turn_off(call):
        pass

    hass.services.async_register("light", "turn_on", mock_turn_on)
    hass.services.async_register("light", "turn_off", mock_turn_off)
    yield


async def test_user_step_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"target_light": "light.test"},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Priority State"
    assert result["data"]["target_light"] == "light.test"


async def test_reconfigure_step(hass: HomeAssistant) -> None:
    """Test the reconfigure flow changes the target light."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"target_light": "light.test"}
    )
    entry = result["result"]
    entry_id = entry.entry_id

    assert entry.data["target_light"] == "light.test"

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"target_light": "light.other"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


async def test_options_flow_init_shows_menu(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"target_light": "light.test"}
    )
    entry = result["result"]
    entry_id = entry.entry_id

    mock_manager = MagicMock()
    mock_manager.rules = []
    mock_manager.target_light = "light.test"
    mock_manager.is_entity_id_used.return_value = False
    mock_manager.async_add_rule = AsyncMock()
    mock_manager.async_update_rule = AsyncMock()
    mock_manager.async_remove_rule = AsyncMock()
    mock_manager.async_clear_rules = AsyncMock()
    mock_manager.async_debug_updated = MagicMock()
    mock_manager.async_load = AsyncMock()
    mock_manager.async_start = AsyncMock()
    mock_manager.async_stop = AsyncMock()
    mock_manager.unload = MagicMock(return_value=True)

    hass.data[DOMAIN] = {entry_id: mock_manager}

    result = await hass.config_entries.options.async_init(
        entry_id,
    )

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "init"
    assert "change_light" in result["menu_options"]
    assert "add_rule" in result["menu_options"]
    assert "debug_mode" in result["menu_options"]
