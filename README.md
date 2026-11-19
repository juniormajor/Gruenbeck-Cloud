# Grünbeck for Home Assistant

Custom integration for **Grünbeck softliQ SD** water softeners (SD18, SD21, SD23) through the Grünbeck cloud, the same service the *Grünbeck myProduct* app uses. The SD series has no local interface; all data comes from the cloud.

The integration was written to be robust against the cloud's habit of changing its payloads: every value is parsed on its own, so a changed date format or a new field turns one entity `unknown` instead of taking the whole integration down.

## Features

| Area | What you get |
|---|---|
| Live values | Flow rate, remaining capacity (m³ and %), regeneration step, counters – pushed over the cloud's SignalR channel, or polled if you switch the channel off |
| Soft water meter | `Soft Water Quantity` in litres, guaranteed monotonic (drops reported by the cloud are ignored), ready for the energy dashboard's water section |
| Daily usage | Finished days of water (l) and salt (kg) imported as long-term statistics `gruenbeck:<serial>_water_daily` / `_salt_daily`; last day as sensors |
| Salt | Salt consumption, salt range (hidden when the SD18 reports 999), a calculated **salt level** with a *Salt refilled* button and a configurable refill amount |
| Parameters | All device parameters as select, number, switch, time and text entities (operation mode, hardness, regeneration schedule, LED ring, notifications, installer contact …); rarely used ones are disabled by default |
| Events | `event` entities for regeneration started/finished and device error raised/resolved |
| Health | Binary sensors for cloud and realtime connection, last update timestamps, repair issues for long outages and for fields the cloud suddenly sends in a different form, diagnostics download |
| Actions | `gruenbeck.regenerate`, `gruenbeck.set_parameters`, `gruenbeck.get_measurements`, `gruenbeck.set_salt_level` |
| Accounts | One entry per Grünbeck account; all softeners of the account share one login and one realtime connection |

## Installation

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/juniormajor/Gruenbeck-Cloud` as type **Integration**.
2. Install **Grünbeck**, restart Home Assistant.
3. *Settings → Devices & services → Add integration → Grünbeck*.

Requires Home Assistant 2026.2 or newer.

## Switching from "Grünbeck Cloud" (hagruenbeck_cloud)

If the integration `gruenbeck_cloud` is set up, the config flow offers **Take over existing setup**. It reuses the stored credentials, removes the old config entry and creates the new entities **under the same entity ids**, carrying over names, areas, labels, icons, display units and the device name. Long-term statistics, the energy dashboard, dashboards and automations keep working.

Recommended order: keep the old integration installed, add *Grünbeck* with the takeover option, check the entities, then remove *Grünbeck Cloud* from HACS. Make a backup first.

States of select entities and of `Regeneration step` are now translated keys (`comfort`, `inactive` …) instead of English display texts; automations comparing against the old texts need an update.

## Options

| Option | Default | Meaning |
|---|---|---|
| Polling interval | 360 s | Minimum 360 s. Shorter intervals can get the account blocked (the ioBroker adapter enforces the same limit). After server errors or HTTP 429 the interval doubles up to one hour and returns to normal after the next success. |
| Realtime channel | on | Keeps one SignalR connection per account for live values, reconnecting with backoff (30 s … 15 min). When off, live values are requested over HTTP on every poll. |

## Data updates and limitations

- Device info and parameters are polled; daily measurements every 6 hours; live values are pushed.
- Up to two failed polls keep the last values; afterwards entities become unavailable. A repair issue appears after two hours without answer.
- The cloud API is unofficial and undocumented. Grünbeck can change or block it at any time.
- Only the softliQ SD series is tested. softliQ SE devices are listed but have a different payload and are not supported yet.
- The calculated salt level is an estimate based on the consumption counter; set it after refilling.

## Troubleshooting

- Enable debug logging for `custom_components.gruenbeck` and download the diagnostics (credentials, serial numbers and installer contact are redacted).
- *Grünbeck cloud sends changed values* lists the fields that could not be read; please open an issue with the diagnostics.

## Removal

Delete the entry under *Settings → Devices & services*, then remove the repository in HACS.

## Credits

Login flow, endpoints and parameter names are based on [pygruenbeck_cloud](https://github.com/p0l0/pygruenbeck_cloud) and [hagruenbeck_cloud](https://github.com/p0l0/hagruenbeck_cloud) by Marco Neumann (MIT) and [ioBroker.gruenbeck](https://github.com/TA2k/ioBroker.gruenbeck) by tombox (MIT). Test fixtures come from pygruenbeck_cloud. Feature ideas (salt level, regeneration events) from the Homey app by Ronny Winkler; no code taken.

This project is not affiliated with Grünbeck Wasseraufbereitung GmbH.
