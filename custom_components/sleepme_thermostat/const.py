API_URL = "https://api.developer.sleep.me/v1"

DOMAIN = "sleepme_thermostat"

DEVICE_TYPE_DOCK_PRO = "dock_pro"
DEVICE_TYPE_TRACKER = "tracker"

DOCK_PRO_MODELS = {"Dock Pro", "DP999NA"}
TRACKER_MODELS = {"Tracker", "Sleep Tracker", "Sleepme Tracker", "ST501NA"}

PRESET_MAX_COOL = "Max Cool"
PRESET_MAX_HEAT = "Max Heat"

# Sentinel values documented by the SleepMe API:
#   set_temperature_c == -1.0  -> MAX COLD
#   set_temperature_c == 999.0 -> MAX HEAT
PRESET_TEMPERATURES = {PRESET_MAX_COOL: -1, PRESET_MAX_HEAT: 999}

# Documented temperature range for set_temperature_c (half-degree increments).
MIN_TEMP_C = 13.0
MAX_TEMP_C = 48.0

# Options flow
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 20
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 300
