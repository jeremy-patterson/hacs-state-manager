# Priority State Configuration

Priority State controls one light from a set of on/off entities. Lower priority numbers win when multiple rules are active.

## Initial setup

Add **Priority State** from **Settings → Devices & services → Add integration** and select:

- A target light.
- Optional Home Assistant Companion devices for live notifications.

Rules are managed from the integration’s **Configure** menu or the bundled Lovelace card.

## Rules

Each rule contains a name, watched entity, priority, color, and enabled flag. A rule is active when its watched entity is `on`; lower priority numbers win. If multiple rules have the same priority, the first configured rule wins and a warning is logged. If no enabled rule is active, Priority State turns the target light off and clears its live notification.

Unavailable watched entities are treated as temporarily unknown; the current light output is retained until Home Assistant receives a usable state again.

## Multiple instances

Multiple Priority State entries are supported. Each entry has its own rules and target light.

Service calls without `entry_id` work when only one entry is configured. When multiple entries exist, include the desired config entry ID:

```yaml
action: priority_state.add_rule
data:
  entry_id: 01JEXAMPLEENTRYID
  name: Door open
  entity_id: binary_sensor.front_door
  priority: 1
  rgb_color: [255, 0, 0]
```

The entry ID is exposed as the `entry_id` attribute on the Priority State sensor.

For the Lovelace card, use the same ID when more than one instance exists:

```yaml
type: custom:priority-state-card
entry_id: 01JEXAMPLEENTRYID
```

## Services

- `priority_state.add_rule`
- `priority_state.update_rule`
- `priority_state.remove_rule`
- `priority_state.clear_rules`

All services accept the optional `entry_id` field.

## Notifications

Active rules are sent to selected Home Assistant Companion devices using a stable notification tag. The notification is refreshed periodically so elapsed time stays current and temporary delivery failures can recover. Android notifications are marked persistent and are cleared by the integration when no rule is active. iOS may still allow users to dismiss notifications because that behavior is controlled by Apple.

## Debugging

Enable **Debug mode** from the integration’s Configure menu, then inspect `home-assistant.log` for rule evaluation, target-light, and notification messages.
