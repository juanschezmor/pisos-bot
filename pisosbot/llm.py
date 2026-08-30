"""Segunda capa: clasificar con Gemini lo que las reglas no pueden juzgar.

Las reglas de shared_rental.py cogen lo explicito ("300€/habitacion"). Quedan
anuncios genuinamente ambiguos, del tipo "piso exclusivo para estudiantes curso
2026-2027", donde hace falta entender la intencion y no buscar cadenas.

Frugalidad deliberada: se manda UNA sola peticion por ronda con todos los
anuncios nuevos juntos, y ninguna cuando no hay novedades. Con el cron cada 10
minutos son como mucho ~144 llamadas al dia, muy por debajo de cualquier limite
del tier gratuito.

Ante el fallo, se abre la mano: si Gemini no contesta, agota cuota o responde
algo raro, los anuncios pasan. Es preferible un aviso de mas que perder un piso
por una caida de un servicio de terceros.
"""
from __future__ import annotations

import json
import logging
import os

import requests

from .models import Listing

log = logging.getLogger(__name__)

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

COMPLETA = "completa"
COMPARTIDA = "compartida"
DUDOSO = "dudoso"

PROMPT = """Filtras anuncios para alguien que busca alquilar una VIVIENDA COMPLETA \
para vivir SOLO en Sevilla. No quiere alquilar una habitación en un piso compartido.

Para cada anuncio decide qué se está alquilando en realidad:

- "compartida": se alquila una habitación o una plaza dentro de un piso, no la \
vivienda entera. Señales: precio referido a la habitación, se busca compañero de \
piso, quedan plazas libres, el precio es muy bajo para el tamaño porque es el de \
una sola habitación.
- "completa": se alquila la vivienda entera. Que mencione cuántas habitaciones \
tiene, o que vaya dirigida a estudiantes, NO la convierte en compartida.
- "dudoso": el texto no da para decidirlo.

El texto puede venir cortado a mitad de frase; juzga con lo que haya y usa \
"dudoso" si no alcanza.

Anuncios:
{anuncios}"""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "anuncios": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "indice": {"type": "INTEGER"},
                    "veredicto": {"type": "STRING", "enum": [COMPLETA, COMPARTIDA, DUDOSO]},
                    "motivo": {"type": "STRING"},
                },
                "required": ["indice", "veredicto"],
            },
        }
    },
    "required": ["anuncios"],
}


class Classifier:
    def __init__(self, model: str, api_key: str | None = None, timeout: int = 30):
        self.model = model
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def classify(self, listings: list[Listing]) -> dict[str, tuple[str, str]]:
        """{uid: (veredicto, motivo)}. Los que no se puedan juzgar salen 'completa'."""
        fallback = {x.uid: (COMPLETA, "") for x in listings}
        if not listings or not self.enabled:
            return fallback

        bloques = []
        for i, x in enumerate(listings):
            datos = f"[{i}] {x.price} €"
            if x.surface:
                datos += f", {x.surface} m²"
            if x.rooms is not None:
                datos += f", {x.rooms} hab"
            texto = " ".join(t for t in (x.title, x.description) if t)
            bloques.append(f"{datos}\n{texto[:600]}")

        payload = {
            "contents": [{"role": "user", "parts": [
                {"text": PROMPT.format(anuncios="\n\n".join(bloques))}
            ]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": SCHEMA,
            },
        }

        try:
            r = requests.post(
                ENDPOINT.format(model=self.model),
                headers={"x-goog-api-key": self.api_key},
                json=payload,
                timeout=self.timeout,
            )
            if r.status_code != 200:
                log.warning("Gemini HTTP %s: %s — pasan todos", r.status_code, r.text[:180])
                return fallback
            raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            veredictos = json.loads(raw)["anuncios"]
        # Captura amplia a proposito: este filtro solo puede quitar anuncios,
        # nunca tumbar la ronda. Cualquier sorpresa del cliente HTTP o de la
        # forma de la respuesta tiene que acabar dejando pasar los anuncios.
        except Exception as exc:  # noqa: BLE001
            log.warning("Gemini no utilizable (%s: %s) — pasan todos",
                        type(exc).__name__, exc)
            return fallback

        out = dict(fallback)
        for item in veredictos:
            try:
                listing = listings[int(item["indice"])]
            except (KeyError, ValueError, IndexError):
                continue
            veredicto = item.get("veredicto", COMPLETA)
            if veredicto in (COMPLETA, COMPARTIDA, DUDOSO):
                out[listing.uid] = (veredicto, (item.get("motivo") or "").strip())
        return out
