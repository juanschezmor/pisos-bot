"""Interfaz comun a todos los portales."""
from __future__ import annotations

import logging

from ..config import Config
from ..http import Fetcher
from ..models import Listing

log = logging.getLogger(__name__)


class Portal:
    name: str = "base"

    def __init__(self, fetcher: Fetcher, cfg: Config):
        self.fetcher = fetcher
        self.cfg = cfg

    def search_urls(self) -> list[str]:
        """URLs a sondear, ya ordenadas por 'mas reciente primero'."""
        raise NotImplementedError

    def parse(self, html: str) -> list[Listing]:
        """Extrae los anuncios de una pagina de resultados."""
        raise NotImplementedError

    def collect(self) -> list[Listing]:
        """Sondea todas sus URLs. Un portal caido no tumba la ejecucion."""
        out: list[Listing] = []
        for url in self.search_urls():
            html = self.fetcher.get(url)
            if not html:
                log.warning("[%s] sin respuesta: %s", self.name, url)
                continue
            try:
                found = self.parse(html)
            except Exception:
                log.exception("[%s] fallo al parsear %s", self.name, url)
                continue
            log.info("[%s] %d anuncios en %s", self.name, len(found), url)
            out.extend(found)
        return out
