"""Pruebas del clasificador sin tocar la red.

Lo importante no es el camino feliz, sino que ningun fallo de Gemini pueda
hacer que se pierda un piso: cuota agotada, timeout, JSON invalido o un indice
que no existe tienen que acabar en "pasan todos".
"""
import json
import pathlib
import sys
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from pisosbot.llm import COMPARTIDA, COMPLETA, DUDOSO, Classifier  # noqa: E402
from pisosbot.models import Listing  # noqa: E402


def anuncios():
    return [
        Listing(portal="p", portal_id="1", url="u1", title="Piso entero", price=700),
        Listing(portal="p", portal_id="2", url="u2", title="Exclusivo estudiantes", price=300),
        Listing(portal="p", portal_id="3", url="u3", title="Dudoso", price=500),
    ]


def respuesta(payload, status=200):
    r = mock.Mock()
    r.status_code = status
    r.text = json.dumps(payload)
    r.json.return_value = payload
    return r


def gemini_dice(veredictos):
    return respuesta({"candidates": [{"content": {"parts": [
        {"text": json.dumps({"anuncios": veredictos})}
    ]}}]})


def main() -> int:
    fallos = []

    def check(nombre, cond):
        if not cond:
            fallos.append(nombre)

    clf = Classifier(model="m", api_key="fake")

    # 1. Camino normal: cada veredicto llega a su anuncio.
    with mock.patch("pisosbot.llm.requests.post", return_value=gemini_dice([
        {"indice": 0, "veredicto": COMPLETA},
        {"indice": 1, "veredicto": COMPARTIDA, "motivo": "precio por habitación"},
        {"indice": 2, "veredicto": DUDOSO},
    ])):
        r = clf.classify(anuncios())
    check("veredicto completa", r["p:1"][0] == COMPLETA)
    check("veredicto compartida", r["p:2"][0] == COMPARTIDA)
    check("motivo conservado", r["p:2"][1] == "precio por habitación")
    check("veredicto dudoso", r["p:3"][0] == DUDOSO)

    # 2. Cuota agotada (429): no puede descartar nada.
    with mock.patch("pisosbot.llm.requests.post", return_value=respuesta({}, status=429)):
        r = clf.classify(anuncios())
    check("429 abre la mano", all(v[0] == COMPLETA for v in r.values()))

    # 3. Excepcion de red: idem.
    with mock.patch("pisosbot.llm.requests.post", side_effect=Exception("timeout")):
        try:
            r = clf.classify(anuncios())
            check("excepción abre la mano", all(v[0] == COMPLETA for v in r.values()))
        except Exception:
            fallos.append("excepción de red no capturada")

    # 4. JSON corrupto en la respuesta.
    with mock.patch("pisosbot.llm.requests.post", return_value=respuesta(
        {"candidates": [{"content": {"parts": [{"text": "esto no es json"}]}}]}
    )):
        r = clf.classify(anuncios())
    check("json inválido abre la mano", all(v[0] == COMPLETA for v in r.values()))

    # 5. Indice inexistente o veredicto inventado: se ignoran sin romper.
    with mock.patch("pisosbot.llm.requests.post", return_value=gemini_dice([
        {"indice": 99, "veredicto": COMPARTIDA},
        {"indice": 0, "veredicto": "otra_cosa"},
        {"indice": 1, "veredicto": COMPARTIDA},
    ])):
        r = clf.classify(anuncios())
    check("índice fuera de rango ignorado", len(r) == 3)
    check("veredicto inválido ignorado", r["p:1"][0] == COMPLETA)
    check("el válido sí se aplica", r["p:2"][0] == COMPARTIDA)

    # 6. Sin clave: ni siquiera se llama a la red.
    sin_clave = Classifier(model="m", api_key="")
    check("sin clave está deshabilitado", not sin_clave.enabled)
    with mock.patch("pisosbot.llm.requests.post", side_effect=AssertionError("no debe llamar")):
        r = sin_clave.classify(anuncios())
    check("sin clave pasan todos", all(v[0] == COMPLETA for v in r.values()))

    if fallos:
        print(f"{len(fallos)} FALLOS:")
        for f in fallos:
            print(f"  - {f}")
        return 1
    print("14/14 pruebas OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
