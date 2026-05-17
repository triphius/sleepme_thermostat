APP_API_URL = "https://api.developer.sleep.me/v1"

DEFAULT_API_HEADERS = {"Content-Type": "application/json"}

API_URL = APP_API_URL  # Optional: Alias for APP_API_URL for consistency

DOMAIN = "sleepme_thermostat"

PRESET_MAX_COOL = "Max Cool"
PRESET_MAX_HEAT = "Max Heat"

PRESET_TEMPERATURES = {PRESET_MAX_COOL: -1, PRESET_MAX_HEAT: 999}

# Options flow
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 20
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 300
