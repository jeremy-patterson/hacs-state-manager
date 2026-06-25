from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "priority_state"
STORAGE_KEY = f"{DOMAIN}.rules"
STORAGE_VERSION = 1
