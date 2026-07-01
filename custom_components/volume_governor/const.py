"""Volume Governor - Keep audio devices at civilized levels."""

DOMAIN = "volume_governor"

# Platforms to set up
PLATFORMS = ["switch", "number", "sensor"]

# Config keys
CONF_DEVICES = "devices"
CONF_DEVICE_ENTITY_ID = "entity_id"
CONF_DEVICE_NAME = "name"
CONF_ADHOC_CAP = "adhoc_cap"
CONF_ADHOC_LIFT_TIME = "adhoc_lift_time"
CONF_SCHEDULE_ENABLED = "schedule_enabled"
CONF_SCHEDULE_START = "schedule_start"
CONF_SCHEDULE_END = "schedule_end"
CONF_SCHEDULE_CAP = "schedule_cap"
CONF_CAP_FLOOR = "cap_floor"

# Defaults
DEFAULT_ADHOC_CAP = 0.30
DEFAULT_ADHOC_LIFT_TIME = "07:00"
DEFAULT_SCHEDULE_CAP = 0.30
DEFAULT_SCHEDULE_START = "22:00"
DEFAULT_SCHEDULE_END = "07:00"
DEFAULT_CAP_FLOOR = 0.10
