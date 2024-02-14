"""The Tago integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_HOST, ATTR_ID
import homeassistant.helpers.config_validation as cv

import logging
import threading
import time
import os
from .tagoserver import run_server
from .const import DOMAIN, CONF_NET_BRIDGE_URL
import voluptuous as vol


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(
            cv.ensure_list,
            [
                {
                    vol.Required(CONF_NET_BRIDGE_URL): cv.string,
                }
            ],
        )
    },
    extra=vol.ALLOW_EXTRA,
)

stop_event = threading.Event()

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
  hass.data.setdefault(DOMAIN, {})
  logging.info('Tago Shim Setup')

  cfg = config.get(DOMAIN)
  logging.info(f'Host cfg {cfg}')
  return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
  config = entry.data
  url = config[CONF_NET_BRIDGE_URL]
  logging.info(f'Bridge URL {url}')

  global stop_event
  run_server(bridge_url=url, 
             db_path=os.path.abspath(os.path.dirname(__file__)) + '/data',
             stop_event=stop_event)

  return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    global stop_event
    if stop_event:
      logging.info('requesting stop')
      stop_event.set()
      time.sleep(2)

    return True
