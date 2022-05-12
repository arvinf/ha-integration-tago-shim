"""The Tago integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_HOST, ATTR_ID

import logging
import threading
import time
import os
from .tagoserver import run_server
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_thread = None

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    _LOGGER.info('Tago Shim Setup')

    cfg = config.get(DOMAIN)
    _LOGGER.info('Host cfg {}'.format(cfg))
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    config = entry.data
    host = config[CONF_HOST]
    
    _LOGGER.info('Bridge URL {}'.format(host))

    global _thread
    _thread = ApiServerThread(hass, host)
    _thread.start()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    global _thread
    if _thread:
      _thread.stop()
      _thread.join()

    return True

class ApiServerThread(threading.Thread):
  def __init__(self, hass, url):
    threading.Thread.__init__(self)

    self.run_thread = True
    self.hass = hass
    self.bridge_url = url
    self.api_server = None

  def stop(self):
    self.run_thread = False
    self.api_server.stop()

  def run(self):
    while self.run_thread:
      time.sleep(1)
      self.api_server = run_server(bridge_url=self.bridge_url, 
                 db_path=os.path.abspath(os.path.dirname(__file__)) + '/data')
    logging.warning('Exiting')
