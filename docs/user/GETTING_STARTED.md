# Getting Started with Priority State

## Installation

Install **Priority State** through HACS, or copy `custom_components/priority_state/` into your Home Assistant `custom_components` directory. Restart Home Assistant after installation.

## Initial setup

1. Open **Settings → Devices & services**.
2. Select **Add integration** and search for **Priority State**.
3. Choose the light to control.
4. Optionally select Home Assistant Companion devices for live notifications.

Open the integration’s **Configure** action to add rules. A rule activates when its watched entity is `on`; the lowest active priority controls the light.

## Lovelace card

The card is registered automatically. Add it from the card picker as **Priority State**.

With one Priority State entry, no configuration is needed:

```yaml
type: custom:priority-state-card
```

With multiple entries, select one explicitly:

```yaml
type: custom:priority-state-card
entry_id: 01JEXAMPLEENTRYID
```

## Notifications

When a rule is active, selected mobile devices receive a tagged live notification showing the winning rule and elapsed active time. The notification is refreshed periodically, and when no rule is active Priority State sends the clear command for that tag.

On iOS, notification dismissal and background delivery are controlled by the operating system. Keep Background App Refresh enabled for reliable clearing.

## Troubleshooting

- Enable **Debug mode** in the integration Configure menu.
- Confirm the watched entity exists and has a usable state.
- Confirm the target light is available.
- For multiple entries, include the correct `entry_id` in service calls and the Lovelace card.
- Check **Settings → System → Logs** for `custom_components.priority_state` messages.
