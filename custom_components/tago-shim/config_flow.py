"""Config flow for Tago integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    CONF_NET_BRIDGE_URL
)

_LOGGER = logging.getLogger(__name__)

# TODO adjust the data schema to the data that you need
DATA_SCHEMA = vol.Schema(
    {vol.Required(CONF_NET_BRIDGE_URL, default=""): str}
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tago."""
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is None:
            _LOGGER.info('user input is none')
            return self.async_show_form(
                step_id="user", data_schema=DATA_SCHEMA, errors=errors
            )

        _LOGGER.info(f'user input is {user_input[CONF_NET_BRIDGE_URL]}')
        return self.async_create_entry(title="Tago Hub", data=user_input)
