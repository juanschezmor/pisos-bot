"""Estado persistente entre ejecuciones.

En GitHub Actions no hay disco persistente, asi que el estado se commitea al
propio repo. Por eso es un JSON pequeno y ordenado: diffs legibles y sin ruido.
"""
from __future__ import annotations

import json
import pathlib
import time

RETENTION_DAYS = 45


class State:
    def __init__(self, path: pathlib.Path):
        self.path = path
        self.seen: dict[str, float] = {}
        self.fingerprints: dict[str, float] = {}
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8") or "{}")
            self.seen = raw.get("seen", {})
            self.fingerprints = raw.get("fingerprints", {})

    def is_new(self, uid: str) -> bool:
        return uid not in self.seen

    def fingerprint_seen(self, fp: str) -> bool:
        return fp in self.fingerprints

    def remember(self, uid: str, fingerprint: str) -> None:
        now = time.time()
        self.seen[uid] = now
        self.fingerprints[fingerprint] = now

    def prune(self) -> None:
        cutoff = time.time() - RETENTION_DAYS * 86400
        self.seen = {k: v for k, v in self.seen.items() if v >= cutoff}
        self.fingerprints = {k: v for k, v in self.fingerprints.items() if v >= cutoff}

    def save(self) -> None:
        self.prune()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Sin marca de tiempo global: asi el fichero solo cambia cuando cambia
        # el contenido, y GitHub Actions no commitea en cada ronda vacia.
        payload = {
            "seen": dict(sorted(self.seen.items())),
            "fingerprints": dict(sorted(self.fingerprints.items())),
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=0, sort_keys=False),
            encoding="utf-8",
        )

    @property
    def is_first_run(self) -> bool:
        return not self.seen
