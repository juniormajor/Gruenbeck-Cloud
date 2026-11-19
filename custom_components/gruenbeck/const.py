"""Constants for the Grünbeck integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "gruenbeck"
LEGACY_DOMAIN: Final = "gruenbeck_cloud"
MANUFACTURER: Final = "Grünbeck Wasseraufbereitung GmbH"

CONF_DEVICES: Final = "devices"
CONF_MIGRATE_LEGACY: Final = "migrate_legacy"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_REALTIME: Final = "realtime"

# The cloud blocks accounts that poll too often; ioBroker.gruenbeck enforces
# 360 s as the minimum (main.js, "Interval ist zu niedrig").
MIN_SCAN_INTERVAL: Final = 360
DEFAULT_SCAN_INTERVAL: Final = 360
MAX_BACKOFF: Final = timedelta(hours=1)
MEASUREMENT_INTERVAL: Final = timedelta(hours=6)
FAILURE_GRACE: Final = 3
OUTAGE_ISSUE_AFTER: Final = timedelta(hours=2)

UNIT_DH: Final = "°dH"
UNIT_MA_MIN: Final = "mAmin"
UNIT_L_IMP: Final = "l/Imp"
UNIT_M3_X_DH: Final = "m³x°dH"
UNIT_L_H: Final = "l/h"

OPERATION_MODES: Final = {1: "eco", 2: "comfort", 3: "power", 4: "individual"}
REGENERATION_MODES: Final = {0: "automatic", 1: "fixed"}
WATER_HARDNESS_UNITS: Final = {1: "dh", 2: "fh", 3: "e", 4: "mol_m3", 5: "ppm"}
LANGUAGES: Final = {
    1: "german",
    2: "english",
    3: "french",
    4: "italian",
    5: "dutch",
    6: "spanish",
    7: "russian",
    9: "danish",
}
LED_MODES: Final = {
    0: "deactivated",
    1: "permanent",
    2: "failure",
    3: "user_failure",
    4: "treatment_user_failure",
}
REGENERATION_STEPS: Final = {
    0: "inactive",
    10: "fill_salt_tank",
    20: "salting",
    30: "displacement",
    40: "backwashing",
    50: "backwashing",
    60: "washing_out",
}

EVENT_REGENERATION_STARTED: Final = "regeneration_started"
EVENT_REGENERATION_FINISHED: Final = "regeneration_finished"
EVENT_ERROR_RAISED: Final = "error_raised"
EVENT_ERROR_RESOLVED: Final = "error_resolved"

DEFAULT_SALT_REFILL_KG: Final = 25.0
