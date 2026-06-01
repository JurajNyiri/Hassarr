import logging
import requests
from urllib.parse import urljoin, urlparse
from .const import DOMAIN
from homeassistant.core import HomeAssistant, ServiceCall

_LOGGER = logging.getLogger(__name__)
ATTR_INSTANCE = "instance"


def _get_matching_entries(
    hass: HomeAssistant,
    required_key: str,
) -> list[tuple[str, dict]]:
    """Return entries that include a required configuration key."""
    domain_data = hass.data.get(DOMAIN, {})
    entries = domain_data.get("entries", {})
    matches = []
    for entry_id, entry_info in entries.items():
        config_data = entry_info.get("data", {})
        if config_data.get(required_key):
            matches.append((entry_id, entry_info))
    return matches


def _resolve_entry_config(
    hass: HomeAssistant,
    call: ServiceCall,
    explicit_entry_id: str | None,
    required_key: str,
) -> tuple[str, dict] | tuple[None, None]:
    """Resolve which config entry should handle this service call."""
    matches = _get_matching_entries(hass, required_key)

    if explicit_entry_id:
        for entry_id, entry_info in matches:
            if entry_id == explicit_entry_id:
                return entry_id, entry_info.get("data", {})
        _LOGGER.error("Configured Hassarr instance '%s' is not available", explicit_entry_id)
        return None, None

    instance = call.data.get(ATTR_INSTANCE)
    if instance:
        for entry_id, entry_info in matches:
            if entry_id == instance or entry_info.get("suffix") == instance:
                return entry_id, entry_info.get("data", {})
        _LOGGER.error(
            "Unknown Hassarr instance '%s'. Use an entry_id or service suffix.",
            instance,
        )
        return None, None

    if len(matches) == 1:
        entry_id, entry_info = matches[0]
        return entry_id, entry_info.get("data", {})

    if not matches:
        _LOGGER.error("No Hassarr instances are configured for this service")
    else:
        available = ", ".join(entry_info.get("suffix", entry_id) for entry_id, entry_info in matches)
        _LOGGER.error(
            "Multiple Hassarr instances match this service. Use '%s' field or a per-instance service. Available: %s",
            ATTR_INSTANCE,
            available,
        )
    return None, None

def fetch_data(url: str, headers: dict) -> dict | None:
    """Fetch data from the given URL with headers.

    Args:
        url (str): The URL to fetch data from.
        headers (dict): The headers to include in the request.

    Returns:
        dict | None: The JSON response if successful, None otherwise.
    """
    response = requests.get(url, headers=headers)
    if response.status_code == requests.codes.ok:
        return response.json()
    else:
        _LOGGER.error(f"Failed to fetch data from {url}: {response.text}")
        return None

def get_root_folder_path(url: str, headers: dict) -> str | None:
    """Get root folder path from the given URL.

    Args:
        url (str): The URL to fetch the root folder path from.
        headers (dict): The headers to include in the request.

    Returns:
        str | None: The root folder path if successful, None otherwise.
    """
    data = fetch_data(url, headers)
    if data:
        return data[0].get("path")
    return None

def handle_add_media(
    hass: HomeAssistant,
    call: ServiceCall,
    media_type: str,
    service_name: str,
    entry_id: str | None = None,
) -> None:
    """Handle the service action to add a media (movie or TV show).

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        call (ServiceCall): The service call object.
        media_type (str): The type of media to add (e.g., "movie" or "series").
        service_name (str): The name of the service (e.g., "radarr" or "sonarr").
    """
    _LOGGER.info(f"Received call data: {call.data}")
    title = call.data.get("title")

    if not title:
        _LOGGER.error("Title is missing in the service call data")
        return

    _LOGGER.info(f"Title received: {title}")

    config_key = f"{service_name}_url"
    resolved_entry_id, config_data = _resolve_entry_config(hass, call, entry_id, config_key)
    if not config_data:
        return

    url = config_data.get(f"{service_name}_url")
    api_key = config_data.get(f"{service_name}_api_key")
    quality_profile_id = config_data.get(f"{service_name}_quality_profile_id")

    if not url or not api_key:
        _LOGGER.error(f"{service_name.capitalize()} URL or API key is missing")
        return

    headers = {'X-Api-Key': api_key}

    # Fetch media list
    search_url = urljoin(url, f"api/v3/{media_type}/lookup?term={title}")
    _LOGGER.info(f"Fetching media list from URL: {search_url}")
    media_list = fetch_data(search_url, headers)

    if media_list:
        media_data = media_list[0]

        # Get root folder path
        root_folder_url = urljoin(url, "api/v3/rootfolder")
        root_folder_path = get_root_folder_path(root_folder_url, headers)
        if not root_folder_path:
            return

        # Prepare payload
        payload = {
            'title': media_data['title'],
            'titleSlug': media_data['titleSlug'],
            'images': media_data['images'],
            'year': media_data['year'],
            'rootFolderPath': root_folder_path,
            'addOptions': {
                'searchForMovie' if media_type == 'movie' else 'searchForMissingEpisodes': True
            },
            'qualityProfileId': quality_profile_id,
        }
        if media_type == 'movie':
            payload['tmdbId'] = media_data['tmdbId']
        else:
            payload['tvdbId'] = media_data['tvdbId']

        # Add media
        add_url = urljoin(url, f"api/v3/{media_type}")
        _LOGGER.info(f"Adding media to URL: {add_url} with payload: {payload}")
        add_response = requests.post(add_url, json=payload, headers=headers)

        if add_response.status_code == requests.codes.created:
            _LOGGER.info(
                "Successfully added %s '%s' to %s (entry %s)",
                media_type,
                title,
                service_name.capitalize(),
                resolved_entry_id,
            )
        else:
            _LOGGER.error(
                "Failed to add %s '%s' to %s (entry %s): %s",
                media_type,
                title,
                service_name.capitalize(),
                resolved_entry_id,
                add_response.text,
            )
    else:
        _LOGGER.info(f"No results found for {media_type} '{title}'")

def handle_add_overseerr_media(
    hass: HomeAssistant,
    call: ServiceCall,
    media_type: str,
    entry_id: str | None = None,
) -> None:
    """Handle the service action to add a media (movie or TV show) using Overseerr.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        call (ServiceCall): The service call object.
        media_type (str): The type of media to add (e.g., "movie" or "tv").
    """
    _LOGGER.info(f"Received call data: {call.data}")
    title = call.data.get("title")

    if not title:
        _LOGGER.error("Title is missing in the service call data")
        return

    _LOGGER.info(f"Title received: {title}")

    resolved_entry_id, config_data = _resolve_entry_config(hass, call, entry_id, "overseerr_url")
    if not config_data:
        return

    url = config_data.get("overseerr_url")
    api_key = config_data.get("overseerr_api_key")

    if not url or not api_key:
        _LOGGER.error("Overseerr URL or API key is missing")
        return

    # Ensure the URL has a scheme
    parsed_url = urlparse(url)
    if not parsed_url.scheme:
        url_https = f"https://{url}"
        url_http = f"http://{url}"
    else:
        url_https = url
        url_http = url

    headers = {'X-Api-Key': api_key}

    # Try https first
    search_url = urljoin(url_https, f"api/v1/search?query={title}")
    _LOGGER.info(f"Searching for media with URL: {search_url}")
    search_results = fetch_data(search_url, headers)

    if not search_results or not search_results.get("results"):
        # Try with http if https fails
        search_url = urljoin(url_http, f"api/v1/search?query={title}")
        _LOGGER.error(f"Retrying search for media with URL: {search_url}")
        _LOGGER.info(f"Retrying search for media with URL: {search_url}")
        search_results = fetch_data(search_url, headers)

    if search_results and search_results.get("results"):
        media_data = search_results["results"][0]
        _LOGGER.error(f"Media data: {media_data}")

        # Prepare payload
        payload = {
            "mediaType": media_type,
            "mediaId": media_data["id"],
            "is4k": False,
            "serverId": 0,
            "profileId": 0,
            "rootFolder": "",
            "languageProfileId": 0,
            "userId": config_data.get("overseerr_user_id"),
            "seasons": "all" if media_type == "tv" else []
        }
        if media_type == "tv":
            tvdb_id = media_data.get("tvdbId")
            if tvdb_id is not None:
                payload["tvdbId"] = tvdb_id

        # Create request
        request_url = urljoin(url_https, "api/v1/request")
        _LOGGER.info(f"Creating request with URL: {request_url} and payload: {payload}")

        request_response = requests.post(request_url, json=payload, headers=headers)

        if request_response.status_code == requests.codes.created:
            _LOGGER.info(
                "Successfully created request for %s '%s' in Overseerr (entry %s)",
                media_type,
                title,
                resolved_entry_id,
            )
        else:
            _LOGGER.error(
                "Failed to create request for %s '%s' in Overseerr (entry %s): %s",
                media_type,
                title,
                resolved_entry_id,
                request_response.text,
            )
    else:
        _LOGGER.info(f"No results found for {media_type} '{title}'")
