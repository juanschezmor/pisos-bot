"""Cliente HTTP educado: un unico User-Agent honesto, reintentos y pausas."""
from __future__ import annotations

import logging
import random
import time

import requests

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}


class Fetcher:
    """Sesion compartida con pausa minima entre peticiones al mismo dominio."""

    def __init__(self, min_delay: float = 1.5, timeout: int = 25, retries: int = 2):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.min_delay = min_delay
        self.timeout = timeout
        self.retries = retries
        self._last_call: dict[str, float] = {}

    def get(self, url: str, **kwargs) -> str | None:
        """Devuelve el HTML, o None si el portal no responde. Nunca lanza."""
        host = url.split("/")[2] if "//" in url else url
        last = self._last_call.get(host, 0.0)
        wait = self.min_delay - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait + random.uniform(0, 0.4))

        for attempt in range(self.retries + 1):
            try:
                r = self.session.get(url, timeout=self.timeout, **kwargs)
                self._last_call[host] = time.monotonic()
                if r.status_code == 200:
                    return r.text
                log.warning("%s -> HTTP %s", url, r.status_code)
                if r.status_code in (403, 429):
                    # Bloqueo o limite de ritmo: no insistimos, es contraproducente.
                    return None
            except requests.RequestException as exc:
                log.warning("%s -> %s", url, exc)
            if attempt < self.retries:
                time.sleep(2 ** attempt + random.uniform(0, 1))
        return None
