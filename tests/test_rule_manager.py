from __future__ import annotations

from unittest.mock import patch

import pytest

from homeassistant.core import HomeAssistant

from custom_components.priority_state.rule_manager import RuleManager


async def test_add_rule(manager: RuleManager) -> None:
    rule = await manager.async_add_rule(
        name="Test Rule",
        entity_id="binary_sensor.test",
        priority=5,
        hue=120.0,
        saturation=80.0,
        enabled=True,
    )

    assert rule["name"] == "Test Rule"
    assert rule["entity_id"] == "binary_sensor.test"
    assert rule["priority"] == 5
    assert rule["hs_color"] == [120.0, 80.0]
    assert rule.get("enabled", True) is True
    assert "id" in rule
    assert len(manager.rules) == 1


async def test_add_rule_coerces_priority(manager: RuleManager) -> None:
    rule = await manager.async_add_rule(
        name="Coerce",
        entity_id="binary_sensor.test",
        priority=5.7,
        hue=0.0,
        saturation=0.0,
    )
    assert rule["priority"] == 5


async def test_add_rule_defaults_enabled(manager: RuleManager) -> None:
    rule = await manager.async_add_rule(
        name="Defaults",
        entity_id="binary_sensor.test",
        priority=1,
        hue=0.0,
        saturation=0.0,
    )
    assert rule.get("enabled", True) is True


async def test_add_rule_disabled(manager: RuleManager) -> None:
    rule = await manager.async_add_rule(
        name="Disabled",
        entity_id="binary_sensor.test",
        priority=1,
        hue=0.0,
        saturation=0.0,
        enabled=False,
    )
    assert rule.get("enabled") is False


async def test_remove_rule(manager: RuleManager) -> None:
    rule = await manager.async_add_rule(
        name="To Remove",
        entity_id="binary_sensor.test",
        priority=1,
        hue=0.0,
        saturation=0.0,
    )
    assert len(manager.rules) == 1

    await manager.async_remove_rule(rule["id"])
    assert len(manager.rules) == 0


async def test_remove_nonexistent_rule(manager: RuleManager) -> None:
    await manager.async_remove_rule("nonexistent_id")
    assert len(manager.rules) == 0


async def test_update_rule(manager: RuleManager) -> None:
    rule = await manager.async_add_rule(
        name="Original",
        entity_id="binary_sensor.test",
        priority=1,
        hue=0.0,
        saturation=0.0,
    )

    await manager.async_update_rule(
        rule["id"],
        name="Updated",
        entity_id="binary_sensor.test",
        priority=10,
        hue=200.0,
        saturation=50.0,
        enabled=False,
    )

    updated = manager.rules[0]
    assert updated["name"] == "Updated"
    assert updated["priority"] == 10
    assert updated["hs_color"] == [200.0, 50.0]
    assert updated.get("enabled") is False


async def test_update_rule_partial(manager: RuleManager) -> None:
    rule = await manager.async_add_rule(
        name="Partial",
        entity_id="binary_sensor.test",
        priority=1,
        hue=0.0,
        saturation=0.0,
    )

    await manager.async_update_rule(
        rule["id"],
        name="Partially Updated",
    )

    updated = manager.rules[0]
    assert updated["name"] == "Partially Updated"
    assert updated["priority"] == 1
    assert updated["hs_color"] == [0.0, 0.0]


async def test_clear_rules(manager: RuleManager) -> None:
    await manager.async_add_rule(
        name="Rule 1",
        entity_id="binary_sensor.one",
        priority=1,
        hue=0.0,
        saturation=0.0,
    )
    await manager.async_add_rule(
        name="Rule 2",
        entity_id="binary_sensor.two",
        priority=2,
        hue=0.0,
        saturation=0.0,
    )
    assert len(manager.rules) == 2

    await manager.async_clear_rules()
    assert len(manager.rules) == 0


async def test_is_entity_id_used(manager: RuleManager) -> None:
    await manager.async_add_rule(
        name="Exists",
        entity_id="binary_sensor.test",
        priority=1,
        hue=0.0,
        saturation=0.0,
    )

    assert manager.is_entity_id_used("binary_sensor.test") is True
    assert manager.is_entity_id_used("binary_sensor.other") is False


async def test_is_entity_id_used_excludes_rule_id(manager: RuleManager) -> None:
    rule = await manager.async_add_rule(
        name="Exclude Me",
        entity_id="binary_sensor.test",
        priority=1,
        hue=0.0,
        saturation=0.0,
    )

    assert (
        manager.is_entity_id_used(
            "binary_sensor.test", exclude_rule_id=rule["id"]
        )
        is False
    )


async def test_evaluate_lowest_priority_wins(
    hass: HomeAssistant, manager: RuleManager
) -> None:
    await manager.async_add_rule(
        name="High Priority",
        entity_id="binary_sensor.high",
        priority=1,
        hue=0.0,
        saturation=100.0,
    )
    await manager.async_add_rule(
        name="Low Priority",
        entity_id="binary_sensor.low",
        priority=10,
        hue=240.0,
        saturation=100.0,
    )

    hass.states.async_set("binary_sensor.high", "on")
    hass.states.async_set("binary_sensor.low", "on")

    with (
        patch.object(manager, "_notify_update"),
        patch(
            "homeassistant.core.ServiceRegistry.async_call"
        ) as mock_service_call,
    ):
        await manager._evaluate()

    mock_service_call.assert_any_call(
        "light",
        "turn_on",
        {
            "entity_id": "light.test",
            "hs_color": [0.0, 100.0],
        },
        blocking=True,
    )


async def test_disabled_rules_skipped(
    hass: HomeAssistant, manager: RuleManager
) -> None:
    await manager.async_add_rule(
        name="Disabled",
        entity_id="binary_sensor.disabled",
        priority=1,
        hue=0.0,
        saturation=100.0,
        enabled=False,
    )
    await manager.async_add_rule(
        name="Enabled",
        entity_id="binary_sensor.enabled",
        priority=10,
        hue=240.0,
        saturation=100.0,
    )

    hass.states.async_set("binary_sensor.disabled", "on")
    hass.states.async_set("binary_sensor.enabled", "on")

    with (
        patch.object(manager, "_notify_update"),
        patch(
            "homeassistant.core.ServiceRegistry.async_call"
        ) as mock_service_call,
    ):
        await manager._evaluate()

    mock_service_call.assert_any_call(
        "light",
        "turn_on",
        {
            "entity_id": "light.test",
            "hs_color": [240.0, 100.0],
        },
        blocking=True,
    )


async def test_no_active_rules_turns_light_off(
    hass: HomeAssistant, manager: RuleManager
) -> None:
    await manager.async_add_rule(
        name="Inactive",
        entity_id="binary_sensor.test",
        priority=1,
        hue=0.0,
        saturation=0.0,
    )

    hass.states.async_set("binary_sensor.test", "off")

    with (
        patch.object(manager, "_notify_update"),
        patch(
            "homeassistant.core.ServiceRegistry.async_call"
        ) as mock_service_call,
    ):
        await manager._evaluate()

    mock_service_call.assert_any_call(
        "light",
        "turn_off",
        {"entity_id": "light.test"},
        blocking=True,
    )


async def test_active_rule_turns_light_on(
    hass: HomeAssistant, manager: RuleManager
) -> None:
    await manager.async_add_rule(
        name="Active",
        entity_id="binary_sensor.test",
        priority=1,
        hue=120.0,
        saturation=80.0,
    )

    hass.states.async_set("binary_sensor.test", "on")

    with (
        patch.object(manager, "_notify_update"),
        patch(
            "homeassistant.core.ServiceRegistry.async_call"
        ) as mock_service_call,
    ):
        await manager._evaluate()

    mock_service_call.assert_any_call(
        "light",
        "turn_on",
        {
            "entity_id": "light.test",
            "hs_color": [120.0, 80.0],
        },
        blocking=True,
    )


async def test_save_persists_rules(manager: RuleManager) -> None:
    with patch.object(manager, "async_save") as mock_save:
        await manager.async_add_rule(
            name="Persist",
            entity_id="binary_sensor.test",
            priority=1,
            hue=0.0,
            saturation=0.0,
        )
        mock_save.assert_called_once()

    with patch.object(manager, "async_save") as mock_save:
        rule = manager.rules[0]
        await manager.async_remove_rule(rule["id"])
        mock_save.assert_called_once()


async def test_rules_property_returns_copy(manager: RuleManager) -> None:
    await manager.async_add_rule(
        name="Copy Test",
        entity_id="binary_sensor.test",
        priority=1,
        hue=0.0,
        saturation=0.0,
    )

    rules_copy = manager.rules
    rules_copy.clear()

    assert len(manager.rules) == 1


async def test_update_tracking(manager: RuleManager) -> None:
    await manager.async_add_rule(
        name="Tracked",
        entity_id="binary_sensor.test",
        priority=1,
        hue=0.0,
        saturation=0.0,
    )

    await manager.async_remove_rule(manager.rules[0]["id"])

    assert len(manager.rules) == 0


async def test_register_update_callback(manager: RuleManager) -> None:
    callback_called = False

    def callback() -> None:
        nonlocal callback_called
        callback_called = True

    manager.register_update_callback(callback)

    with patch.object(manager, "_evaluate"):
        await manager.async_add_rule(
            name="Callback Test",
            entity_id="binary_sensor.test",
            priority=1,
            hue=0.0,
            saturation=0.0,
        )

    assert callback_called is True


async def test_multiple_callbacks(manager: RuleManager) -> None:
    calls: list[str] = []

    def cb1() -> None:
        calls.append("cb1")

    def cb2() -> None:
        calls.append("cb2")

    manager.register_update_callback(cb1)
    manager.register_update_callback(cb2)

    with patch.object(manager, "_evaluate"):
        await manager.async_add_rule(
            name="Multi",
            entity_id="binary_sensor.test",
            priority=1,
            hue=0.0,
            saturation=0.0,
        )

    assert calls == ["cb1", "cb2"]
