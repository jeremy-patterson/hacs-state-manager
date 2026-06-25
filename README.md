# Priority State

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jeremy-patterson&repository=hacs-state-manager&category=integration)

A Home Assistant custom integration that controls a light's color based on priority rules. When a watched entity turns on, its assigned rule fires and sets the target light to that rule's color. If multiple entities are on simultaneously, the lowest priority number wins. If no entities are active, the light turns off.

## Features

- **Priority-based rules** — assign each entity a priority; lower number = higher priority
- **RGB color control** — pick any color per rule; the light changes instantly when a rule activates
- **Rich entity selectors** — configure rules with HA's standard entity picker and color selector
- **Config flow UI** — all rule management happens through the integration's Configure dialog
- **Lovelace card** — visual dashboard showing all rules, their states, and the active winner
- **Debug mode** — toggle verbose logging and per-rule entity toggle buttons on the card
- **Services** — add, update, and remove rules programmatically via Developer Tools

## Installation

### HACS (recommended)

1. Click the badge above or go to **HACS → Integrations → three dots → Custom repositories**
2. Add `https://github.com/jeremy-patterson/hacs-state-manager` with category **Integration**
3. Click **Install** on Priority State
4. Restart Home Assistant

### Manual

Copy the `custom_components/priority_state/` directory into your Home Assistant's `custom_components/` directory and restart.

## Usage

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Priority State** and select your target light
3. Click **Configure** to add rules:
   - **Name** — a friendly label for the rule
   - **Entity** — the binary sensor, switch, or other on/off entity to watch
   - **Priority** — lower number = higher priority (wins when multiple rules are active)
   - **Color** — the RGB color the light should show when this rule wins
   - **Enabled** — toggle a rule on/off without deleting it
4. Add the **Priority State** card to a Lovelace dashboard for a live view

### Lovelace Card

The card is bundled and auto-registered with Lovelace on restart. No manual resource setup needed — it just appears in the card picker.

1. Edit a dashboard, click **Add Card**
2. Search for **Priority State**
3. The card auto-detects the integration's sensor entity — no configuration required.

The card shows:
- Target light status (on/off + current color dot)
- All rules sorted by priority with color swatches
- ON/OFF indicators per entity
- Active winner highlighted in blue
- Edit/delete/add buttons for rule management
- Debug toggle buttons when debug mode is enabled

### Services

- `priority_state.add_rule` — add a new rule
- `priority_state.update_rule` — update an existing rule
- `priority_state.remove_rule` — remove a rule by ID
- `priority_state.clear_rules` — remove all rules

## Development

This integration was built with the [integration blueprint](https://github.com/jpawlowski/hacs.integration_blueprint) template.

### Scripts

```bash
script/develop      # Start local HA instance
script/check        # Full validation suite
script/lint         # Auto-fix formatting
script/type-check   # Pyright type checking
```

## License

MIT
