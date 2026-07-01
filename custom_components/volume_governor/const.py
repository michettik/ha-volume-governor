"""Volume Governor constants."""

DOMAIN = "volume_governor"

# Platforms to set up
PLATFORMS = ["switch", "number", "sensor"]

# Config keys
CONF_DEVICES = "devices"
CONF_DEVICE_ENTITY_ID = "entity_id"
CONF_DEVICE_NAME = "name"
CONF_DEVICE_CAP = "cap"
CONF_DEVICE_PERSISTENT = "persistent"

CONF_SCHEDULE_DAYS = "schedule_days"
CONF_SCHEDULE_START = "schedule_start"
CONF_SCHEDULE_END = "schedule_end"
CONF_DEFAULT_CAP = "default_cap"
CONF_CAP_FLOOR = "cap_floor"

# Defaults
DEFAULT_SCHEDULE_DAYS = [0, 1, 2, 3, 4]  # Mon-Fri (Python weekday())
DEFAULT_SCHEDULE_START = "22:00"
DEFAULT_SCHEDULE_END = "07:00"
DEFAULT_CAP = 0.30
DEFAULT_CAP_FLOOR = 0.10

# Day names for UI
DAY_NAMES = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}
