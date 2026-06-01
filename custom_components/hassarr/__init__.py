from __future__ import annotations

import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    SERVICE_ADD_OVERSEERR_MOVIE,
    SERVICE_ADD_OVERSEERR_TV_SHOW,
    SERVICE_ADD_RADARR_MOVIE,
    SERVICE_ADD_SONARR_TV_SHOW,
)
from .services import handle_add_media, handle_add_overseerr_media

_LOGGER = logging.getLogger(__name__)

ATTR_INSTANCE = "instance"
DATA_BASE_SERVICES_REGISTERED = "base_services_registered"
DATA_ENTRIES = "entries"
DATA_ENTRY_SERVICES = "entry_services"

ADD_RADARR_MOVIE_SCHEMA = vol.Schema(
    {
        vol.Required("title"): cv.string,
        vol.Optional(ATTR_INSTANCE): cv.string,
    }
)

ADD_SONARR_TV_SHOW_SCHEMA = vol.Schema(
    {
        vol.Required("title"): cv.string,
        vol.Optional(ATTR_INSTANCE): cv.string,
    }
)

ADD_OVERSEERR_MOVIE_SCHEMA = vol.Schema(
    {
        vol.Required("title"): cv.string,
        vol.Optional(ATTR_INSTANCE): cv.string,
    }
)

ADD_OVERSEERR_TV_SHOW_SCHEMA = vol.Schema(
    {
        vol.Required("title"): cv.string,
        vol.Optional(ATTR_INSTANCE): cv.string,
    }
)


def _get_domain_data(hass: HomeAssistant) -> dict[str, Any]:
    """Get integration runtime storage."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data.setdefault(DATA_BASE_SERVICES_REGISTERED, False)
    domain_data.setdefault(DATA_ENTRIES, {})
    domain_data.setdefault(DATA_ENTRY_SERVICES, {})
    return domain_data


def _entry_service_suffix(config_entry: ConfigEntry) -> str:
    """Build a deterministic suffix for per-instance service names."""
    return config_entry.entry_id[:8]


def _register_service(
    hass: HomeAssistant,
    service_name: str,
    handler,
    schema: vol.Schema,
) -> None:
    """Register or replace one service."""
    if hass.services.has_service(DOMAIN, service_name):
        hass.services.async_remove(DOMAIN, service_name)
    hass.services.async_register(DOMAIN, service_name, handler, schema=schema)


def _register_base_services(hass: HomeAssistant) -> None:
    """Register backward-compatible shared service names."""
    domain_data = _get_domain_data(hass)
    if domain_data[DATA_BASE_SERVICES_REGISTERED]:
        return

    _register_service(
        hass,
        SERVICE_ADD_RADARR_MOVIE,
        lambda call: handle_add_movie(hass, call),
        ADD_RADARR_MOVIE_SCHEMA,
    )
    _register_service(
        hass,
        SERVICE_ADD_SONARR_TV_SHOW,
        lambda call: handle_add_tv_show(hass, call),
        ADD_SONARR_TV_SHOW_SCHEMA,
    )
    _register_service(
        hass,
        SERVICE_ADD_OVERSEERR_MOVIE,
        lambda call: handle_add_overseerr_movie(hass, call),
        ADD_OVERSEERR_MOVIE_SCHEMA,
    )
    _register_service(
        hass,
        SERVICE_ADD_OVERSEERR_TV_SHOW,
        lambda call: handle_add_overseerr_tv_show(hass, call),
        ADD_OVERSEERR_TV_SHOW_SCHEMA,
    )

    domain_data[DATA_BASE_SERVICES_REGISTERED] = True


def _register_entry_service(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    service_name: str,
    handler,
    schema: vol.Schema,
) -> None:
    """Register one per-entry service and track it for cleanup."""
    _register_service(hass, service_name, handler, schema)
    domain_data = _get_domain_data(hass)
    domain_data[DATA_ENTRY_SERVICES].setdefault(config_entry.entry_id, set()).add(service_name)


def handle_add_movie(
    hass: HomeAssistant,
    call: ServiceCall,
    entry_id: str | None = None,
) -> None:
    """Handle add movie action."""
    handle_add_media(hass, call, "movie", "radarr", entry_id=entry_id)


def handle_add_tv_show(
    hass: HomeAssistant,
    call: ServiceCall,
    entry_id: str | None = None,
) -> None:
    """Handle add TV show action."""
    handle_add_media(hass, call, "series", "sonarr", entry_id=entry_id)


def handle_add_overseerr_movie(
    hass: HomeAssistant,
    call: ServiceCall,
    entry_id: str | None = None,
) -> None:
    """Handle add movie through Overseerr action."""
    handle_add_overseerr_media(hass, call, "movie", entry_id=entry_id)


def handle_add_overseerr_tv_show(
    hass: HomeAssistant,
    call: ServiceCall,
    entry_id: str | None = None,
) -> None:
    """Handle add TV show through Overseerr action."""
    handle_add_overseerr_media(hass, call, "tv", entry_id=entry_id)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Hassarr and register shared services."""
    _get_domain_data(hass)
    _register_base_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up Hassarr from one config entry."""
    domain_data = _get_domain_data(hass)
    _register_base_services(hass)

    suffix = _entry_service_suffix(config_entry)
    domain_data[DATA_ENTRIES][config_entry.entry_id] = {
        "data": config_entry.data,
        "suffix": suffix,
        "title": config_entry.title,
    }

    if config_entry.data.get("radarr_url"):
        _register_entry_service(
            hass,
            config_entry,
            f"{SERVICE_ADD_RADARR_MOVIE}_{suffix}",
            lambda call, entry_id=config_entry.entry_id: handle_add_movie(hass, call, entry_id),
            ADD_RADARR_MOVIE_SCHEMA,
        )
    if config_entry.data.get("sonarr_url"):
        _register_entry_service(
            hass,
            config_entry,
            f"{SERVICE_ADD_SONARR_TV_SHOW}_{suffix}",
            lambda call, entry_id=config_entry.entry_id: handle_add_tv_show(hass, call, entry_id),
            ADD_SONARR_TV_SHOW_SCHEMA,
        )
    if config_entry.data.get("overseerr_url"):
        _register_entry_service(
            hass,
            config_entry,
            f"{SERVICE_ADD_OVERSEERR_MOVIE}_{suffix}",
            lambda call, entry_id=config_entry.entry_id: handle_add_overseerr_movie(hass, call, entry_id),
            ADD_OVERSEERR_MOVIE_SCHEMA,
        )
        _register_entry_service(
            hass,
            config_entry,
            f"{SERVICE_ADD_OVERSEERR_TV_SHOW}_{suffix}",
            lambda call, entry_id=config_entry.entry_id: handle_add_overseerr_tv_show(hass, call, entry_id),
            ADD_OVERSEERR_TV_SHOW_SCHEMA,
        )

    _LOGGER.info(
        "Hassarr entry '%s' loaded. Per-instance service suffix: %s",
        config_entry.title,
        suffix,
    )

    config_entry.async_on_unload(config_entry.add_update_listener(update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload one Hassarr config entry."""
    domain_data = _get_domain_data(hass)

    for service_name in domain_data[DATA_ENTRY_SERVICES].pop(config_entry.entry_id, set()):
        if hass.services.has_service(DOMAIN, service_name):
            hass.services.async_remove(DOMAIN, service_name)

    domain_data[DATA_ENTRIES].pop(config_entry.entry_id, None)
    return True


async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle config entry updates by reloading the entry."""
    await hass.config_entries.async_reload(config_entry.entry_id)
