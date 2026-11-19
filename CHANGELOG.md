# Changelog

## 0.1.2

- New sensors: extent of the last regeneration per exchanger in % (`mregpercent1`/`mregpercent2`), as in the Homey app.
- New time entities: period in which the audio signal is allowed (`pbuzzfrom`/`pbuzzto`).

## 0.1.1

- Do not close the HTTP session created by Home Assistant (frame helper warning during setup).
- Brand icon included in the release.

## 0.1.0

First release.

- Cloud login (Azure AD B2C with PKCE), device list, info, parameters, daily measurements, regeneration, parameter writes.
- Tolerant field parsing: unreadable values become `unknown` and raise a repair issue instead of breaking the setup.
- One entry per account, one coordinator per softener, shared SignalR realtime channel with reconnect and backoff.
- Grace period and exponential backoff on cloud errors; outage repair issue after two hours.
- Monotonic soft water meter, calculated salt level with refill button, last-day usage sensors, daily long-term statistics.
- Regeneration and device error events; cloud and realtime connection sensors; diagnostics.
- Takeover of an existing `gruenbeck_cloud` setup keeping entity ids, options and statistics.
- Reauthentication, reconfiguration and options flows; English and German translations.
