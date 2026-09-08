"""
Optional reverse-geocoding for incident reports: turns a camera's lat/lon into a
readable address via the Google Maps Geocoding API. Purely for labeling reports —
not used for detection (see conversation: Maps API has no vision capability).

Set GOOGLE_MAPS_API_KEY to enable; without it, reports fall back to raw coordinates.
"""
import os
import requests

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


def reverse_geocode(lat: float, lon: float) -> str | None:
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return None

    try:
        resp = requests.get(
            GEOCODE_URL,
            params={"latlng": f"{lat},{lon}", "key": api_key},
            timeout=5,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0]["formatted_address"] if results else None
    except requests.RequestException:
        return None
