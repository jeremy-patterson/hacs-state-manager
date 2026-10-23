# Priority State Examples

## Add a rule

```yaml
action: priority_state.add_rule
data:
  name: Front door open
  entity_id: binary_sensor.front_door
  priority: 1
  rgb_color: [255, 0, 0]
```

For multiple Priority State entries, include `entry_id`:

```yaml
action: priority_state.add_rule
data:
  entry_id: 01JEXAMPLEENTRYID
  name: Motion detected
  entity_id: binary_sensor.hall_motion
  priority: 10
  rgb_color: [255, 165, 0]
```

## Update a rule

```yaml
action: priority_state.update_rule
data:
  rule_id: 12345678-1234-1234-1234-123456789abc
  priority: 2
  rgb_color: [0, 128, 255]
```

## Clear all rules

```yaml
action: priority_state.clear_rules
data:
  entry_id: 01JEXAMPLEENTRYID
```

## Lovelace card

```yaml
type: custom:priority-state-card
entry_id: 01JEXAMPLEENTRYID
```

Omit `entry_id` when only one Priority State entry is configured.
