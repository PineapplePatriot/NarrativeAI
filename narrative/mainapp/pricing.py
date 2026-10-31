"""Per-token prices from OpenRouter's public model list, for cost estimates before something runs (Bulba's setup
form). Cached for a few hours; when the list can't be read there is simply no estimate, never a guessed one."""
import logging

import requests
from django.core.cache import cache

log = logging.getLogger(__name__)

MODELS_URL = "https://openrouter.ai/api/v1/models"
CACHE_KEY = "openrouter-prices"


def table():
    """{model id: (USD per input token, USD per output token)}; {} when OpenRouter can't be reached."""
    data = cache.get(CACHE_KEY)
    if data is not None:
        return data
    data = {}
    try:
        resp = requests.get(MODELS_URL, timeout=8)
        resp.raise_for_status()
        for m in resp.json().get("data", []):
            p = m.get("pricing") or {}
            try:
                data[m["id"]] = (float(p.get("prompt") or 0), float(p.get("completion") or 0))
            except (KeyError, TypeError, ValueError):
                continue
        cache.set(CACHE_KEY, data, 6 * 3600)
    except (requests.RequestException, ValueError) as e:
        log.warning("OpenRouter's price list couldn't be read: %s", e)
        cache.set(CACHE_KEY, data, 300)  # try again in a few minutes
    return data


def per_token(model):
    """(input, output) USD per token for an OpenRouter model id, or None."""
    return table().get(model or "")
