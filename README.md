# Volume Governor

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Home Assistant custom integration that enforces volume limits on audio devices. Because sometimes your kids (or your own drunk self) don't understand what "reasonable volume" means.

## Features

- **Auto-discovery** of all media players in Home Assistant that support volume control
- **Ad-hoc mode**: One-click volume cap — activate it when things get too loud, auto-lifts at a configured time (default: 7am next morning)
- **Scheduled mode**: Define quiet hours with automatic enforcement during those windows every day
- **Both modes simultaneously**: Lowest cap wins. Schedule runs nightly, ad-hoc available anytime on top
- **Instant enforcement**: Uses state change listeners, not polling. Volume is corrected within milliseconds of someone trying to crank it
- **Cap floor**: Prevents accidentally setting the limit so low the device becomes unusable

## Installation

### HACS (recommended)

1. Open HACS in your Home Assistant instance
2. Click the three dots menu → **Custom repositories**
3. Add this repository URL as an **Integration**
4. Search for "Volume Governor" and install
5. Restart Home Assistant
6. Go to **Settings → Devices & Services → Add Integration → Volume Governor**

### Manual

1. Copy the `custom_components/volume_governor` directory to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Go to **Settings → Devices & Services → Add Integration → Volume Governor**

## Configuration

The setup wizard guides you through:

1. **Device selection** — All media players with volume control are listed. Pick the ones you want governed.
2. **Per-device configuration** — For each device:
   - **Ad-hoc cap level** (5-100%): The volume limit when ad-hoc mode is activated
   - **Ad-hoc lift time** (HH:MM): When the ad-hoc cap automatically deactivates
   - **Schedule enabled**: Whether to enforce a cap during specific hours
   - **Schedule start/end** (HH:MM): The quiet hours window (supports overnight, e.g. 22:00-07:00)
   - **Schedule cap level** (5-100%): Volume limit during scheduled hours
   - **Cap floor** (1-50%): Minimum allowed cap value (prevents accidental muting)

## Entities Created

For each governed device, the integration creates:

| Entity | Type | Purpose |
|--------|------|---------|
| `switch.volume_governor_<device>` | Switch | Toggle ad-hoc mode on/off |
| `number.volume_governor_<device>_adhoc_cap` | Number | Adjust ad-hoc cap level (slider) |
| `number.volume_governor_<device>_schedule_cap` | Number | Adjust schedule cap level (slider) |
| `sensor.volume_governor_<device>_status` | Sensor | Shows current enforcement status |

## Dashboard Card Example

```yaml
type: entities
title: Volume Governor
entities:
  - entity: switch.volume_governor_media_player_denon_avr_x1400h
    name: Ad-hoc Cap
  - entity: number.volume_governor_media_player_denon_avr_x1400h_adhoc_cap
    name: Ad-hoc Level
  - entity: number.volume_governor_media_player_denon_avr_x1400h_schedule_cap
    name: Schedule Level
  - entity: sensor.volume_governor_media_player_denon_avr_x1400h_status
    name: Status
```

## How Enforcement Works

1. Volume Governor registers a state change listener on each governed media player
2. When a volume change is detected, it checks whether any cap is active (ad-hoc, schedule, or both)
3. If current volume exceeds the effective cap (lowest of all active caps), it immediately calls `media_player.volume_set` to enforce the limit
4. Re-entrancy is handled — the enforcement call's own state change doesn't trigger another enforcement loop
5. Devices that are off/unavailable are ignored; enforcement kicks in when they power back on

## Reconfiguration

Go to **Settings → Devices & Services → Volume Governor → Configure** to:
- Add/remove governed devices
- Change cap levels, schedules, or lift times

Changes take effect immediately after saving (integration reloads automatically).

## License

MIT
