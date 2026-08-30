"""Envio a Telegram.

Un anuncio = un mensaje con foto y boton directo. El objetivo es poder decidir
desde la notificacion del movil sin abrir nada mas.
"""
from __future__ import annotations

import html
import logging
import os
import time

import requests

from .models import Listing

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"
CAPTION_LIMIT = 1024


class Telegram:
    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def _call(self, method: str, payload: dict) -> bool:
        try:
            r = requests.post(
                API.format(token=self.token, method=method), json=payload, timeout=20
            )
            if r.status_code == 429:
                retry = r.json().get("parameters", {}).get("retry_after", 3)
                time.sleep(retry + 1)
                r = requests.post(
                    API.format(token=self.token, method=method), json=payload, timeout=20
                )
            if r.status_code != 200:
                log.error("Telegram %s -> %s %s", method, r.status_code, r.text[:200])
                return False
            return True
        except requests.RequestException as exc:
            log.error("Telegram %s -> %s", method, exc)
            return False

    def send_listing(self, x: Listing, hot: bool) -> bool:
        text = render(x, hot)
        keyboard = {"inline_keyboard": [[{"text": "Ver anuncio ↗", "url": x.url}]]}

        if x.image:
            ok = self._call(
                "sendPhoto",
                {
                    "chat_id": self.chat_id,
                    "photo": x.image,
                    "caption": text[:CAPTION_LIMIT],
                    "parse_mode": "HTML",
                    "reply_markup": keyboard,
                },
            )
            if ok:
                return True
            # Si la foto falla (URL caducada, formato raro) mandamos solo texto.

        return self._call(
            "sendMessage",
            {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": keyboard,
                "link_preview_options": {"is_disabled": True},
            },
        )

    def send_text(self, text: str) -> bool:
        return self._call(
            "sendMessage",
            {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "link_preview_options": {"is_disabled": True},
            },
        )


def _age(ts: float | None) -> str:
    if not ts:
        return ""
    minutes = (time.time() - ts) / 60
    if minutes < 60:
        return f"hace {int(minutes)} min"
    if minutes < 1440:
        return f"hace {int(minutes // 60)} h"
    return f"hace {int(minutes // 1440)} d"


def render(x: Listing, hot: bool) -> str:
    e = html.escape
    head_bits = [f"<b>{x.price} €</b>"]
    if x.surface:
        head_bits.append(f"{x.surface} m²")
    if x.rooms is not None:
        head_bits.append(f"{x.rooms} hab")
    if x.price_per_m2:
        head_bits.append(f"{x.price_per_m2:.1f} €/m²".replace(".", ","))

    lines = [("🔥 " if hot else "") + " · ".join(head_bits)]

    place = x.municipality
    if x.neighborhood and x.neighborhood.lower() not in place.lower():
        place = f"{place} — {x.neighborhood}"
    lines.append(e(place[:90]))

    if x.transport.get("label"):
        lines.append(e(x.transport["label"]))

    if x.reasons:
        lines.append("✅ " + e(" · ".join(x.reasons[:3])))

    if x.warning:
        lines.append("⚠️ " + e(x.warning))

    footer = [x.portal]
    age = _age(x.published_ts)
    if age:
        footer.append(age)
    footer.append(f"nota {x.score:.0f}")
    lines.append("<i>" + e(" · ".join(footer)) + "</i>")

    return "\n".join(lines)
