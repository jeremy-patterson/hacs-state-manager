from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.core import HomeAssistant

from custom_components.priority_state.const import DOMAIN
from custom_components.priority_state.rule_manager import RuleManager


@pytest.fixture
def mock_config_entry() -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {"target_light": "light.test", "debug": False}
    entry.options = {}
    return entry


@pytest.fixture
def manager(
    hass: HomeAssistant, mock_config_entry: MagicMock
) -> RuleManager:
    with (
        patch.object(RuleManager, "async_load"),
        patch(
            "custom_components.priority_state.rule_manager.Store"
        ) as mock_store,
    ):
        mgr = RuleManager(hass, mock_config_entry.entry_id)
        mgr.target_light = "light.test"
        mgr._started = False

        mock_store_instance = MagicMock()
        mock_store_instance.async_load.return_value = None
        mock_store_instance.async_save = AsyncMock()
        mock_store.return_value = mock_store_instance
        mgr._store = mock_store_instance

        async def mock_light_service(call):
            pass

        hass.services.async_register("light", "turn_on", mock_light_service)
        hass.services.async_register("light", "turn_off", mock_light_service)

        hass.data[DOMAIN] = {mock_config_entry.entry_id: mgr}
        yield mgr
