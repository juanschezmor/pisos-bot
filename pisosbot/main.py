"""Punto de entrada: sondea, filtra, puntua y avisa.

    python -m pisosbot.main            # ejecucion normal
    python -m pisosbot.main --dry-run  # sin enviar nada ni tocar el estado
"""
from __future__ import annotations

import argparse
import logging
import os
import pathlib
import sys

from . import config, dedupe, filters, llm, scoring, shared_rental
from .http import Fetcher
from .llm import Classifier
from .models import Listing
from .notify import Telegram
from .portals import ALL
from .state import State

log = logging.getLogger("pisosbot")
ROOT = pathlib.Path(__file__).resolve().parent.parent


def collect_all(cfg: config.Config, only: set[str] | None = None) -> list[Listing]:
    fetcher = Fetcher(min_delay=cfg.min_delay)
    found: list[Listing] = []
    for key, cls in ALL.items():
        if only is not None and key not in only:
            continue
        if not cfg.portals.get(key, True):
            log.info("[%s] desactivado en config", key)
            continue
        portal = cls(fetcher, cfg)
        try:
            rows = portal.collect()
        except Exception:
            log.exception("[%s] fallo completo, se ignora este portal", key)
            continue
        found.extend(rows)
    return found


def run(args: argparse.Namespace) -> int:
    cfg = config.load(args.config)
    state = State(pathlib.Path(args.state))
    first_run = state.is_first_run

    only = None
    if args.portals:
        only = {p.strip() for p in args.portals.split(",") if p.strip()}
        desconocidos = only - set(ALL)
        if desconocidos:
            log.error("portales desconocidos: %s (válidos: %s)",
                      ", ".join(sorted(desconocidos)), ", ".join(ALL))
            return 2
        log.info("solo estos portales: %s", ", ".join(sorted(only)))

    raw = collect_all(cfg, only)
    log.info("recogidos %d anuncios en bruto", len(raw))

    kept, rejected = filters.apply(raw, cfg)
    log.info("tras filtros: %d (descartados: %s)", len(kept), rejected or "ninguno")

    # Marcar antes de fundir duplicados, descartar despues: si una sola copia
    # del anuncio delata que se alquila por habitaciones, cae el grupo entero.
    for x in kept:
        x.shared_hint = shared_rental.detect(x.title, x.description) or ""

    unique = dedupe.collapse(kept)
    log.info("tras dedup entre portales: %d", len(unique))

    por_habitaciones = [x for x in unique if x.shared_hint]
    if por_habitaciones:
        unique = [x for x in unique if not x.shared_hint]
        motivos: dict[str, int] = {}
        for x in por_habitaciones:
            motivos[x.shared_hint] = motivos.get(x.shared_hint, 0) + 1
        log.info("descartados %d por alquiler por habitaciones: %s",
                 len(por_habitaciones), motivos)

    scored = scoring.enrich(unique, cfg)

    # Nuevos = ni el id ni la huella del piso se han visto antes.
    fresh = [
        x for x in scored
        if state.is_new(x.uid) and not state.fingerprint_seen(x.fingerprint())
    ]
    log.info("nuevos para ti: %d", len(fresh))

    if args.seed:
        # Marca todo lo visible como ya visto, sin avisar. Util para arrancar
        # sin inundar y despues de tocar los filtros de config.yaml.
        for x in fresh:
            state.remember(x.uid, x.fingerprint())
        state.save()
        log.info("marcados %d anuncios como vistos, sin enviar nada", len(fresh))
        return 0

    fresh = _classify(fresh, cfg, state)

    if args.dry_run:
        _report(scored, fresh, cfg, first_run)
        return 0

    tg = Telegram()
    if not tg.enabled:
        log.error("faltan TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID; no se envia nada")
        return 1

    to_send = fresh
    suppressed = 0
    if first_run or len(fresh) > cfg.flood_guard:
        to_send = fresh[: cfg.flood_guard]
        suppressed = len(fresh) - len(to_send)

    if first_run and fresh:
        tg.send_text(
            f"🏠 <b>pisos-bot en marcha</b>\n"
            f"{len(scored)} anuncios vigentes en tu zona por menos de {cfg.max_price} €.\n"
            f"Te mando los {len(to_send)} mejores ahora; a partir de aquí solo lo nuevo."
        )

    sent = 0
    for x in to_send:
        if tg.send_listing(x, hot=x.score >= cfg.hot_threshold):
            sent += 1
        state.remember(x.uid, x.fingerprint())

    # Los que no se envian tambien se marcan: son antiguos, no queremos que
    # aparezcan como novedad en la siguiente ronda.
    for x in fresh[len(to_send):]:
        state.remember(x.uid, x.fingerprint())

    if suppressed and not first_run:
        tg.send_text(f"…y {suppressed} anuncios más de menor nota, no enviados.")

    state.save()
    log.info("enviados %d avisos (%d silenciados)", sent, suppressed)
    return 0


def _classify(fresh: list[Listing], cfg: config.Config, state: State) -> list[Listing]:
    """Descarta los anuncios de habitacion que las reglas no pudieron ver.

    Solo se pregunta por los anuncios nuevos y sin veredicto previo, en una
    unica peticion. Si no hay clave o el servicio falla, pasan todos: perder un
    piso por una caida de terceros seria peor que un aviso de mas.
    """
    if not fresh or not cfg.llm_enabled:
        return fresh

    clasificador = Classifier(cfg.llm_model)
    if not clasificador.enabled:
        log.info("sin GEMINI_API_KEY: solo actúa la capa de reglas")
        return fresh

    pendientes = [x for x in fresh if state.verdict(x.uid) is None][: cfg.llm_max_batch]
    if pendientes:
        for uid, (veredicto, _motivo) in clasificador.classify(pendientes).items():
            state.set_verdict(uid, veredicto)
        log.info("clasificados %d anuncios con %s", len(pendientes), cfg.llm_model)

    salen: list[Listing] = []
    for x in fresh:
        veredicto = state.verdict(x.uid) or llm.COMPLETA
        if veredicto == llm.COMPARTIDA:
            # Se marca como visto para no volver a evaluarlo cada ronda.
            state.remember(x.uid, x.fingerprint())
            log.info("descartado por el clasificador: %s %s€ %s", x.portal, x.price, x.url)
            continue
        if veredicto == llm.DUDOSO:
            x.warning = "podría ser alquiler por habitaciones"
        salen.append(x)

    descartados = len(fresh) - len(salen)
    if descartados:
        log.info("el clasificador descartó %d anuncios de habitación", descartados)
    return salen


def _report(scored: list[Listing], fresh: list[Listing], cfg, first_run: bool) -> None:
    print(f"\n{'='*74}")
    print(f"SIMULACIÓN — {len(scored)} anuncios válidos, {len(fresh)} serían nuevos"
          f"{' (primera ejecución)' if first_run else ''}")
    print("=" * 74)
    for x in scored[:15]:
        hot = "🔥" if x.score >= cfg.hot_threshold else "  "
        ppm = f"{x.price_per_m2:.1f}€/m²" if x.price_per_m2 else "—"
        print(f"{hot} {x.score:5.1f} | {x.price:>4}€ {str(x.surface or '?'):>3}m² {ppm:>9} | "
              f"{(x.municipality or '?')[:20]:<20} | {x.transport.get('label','')[:34]:<34} | {x.portal}")
        if x.reasons:
            print(f"          └─ {' · '.join(x.reasons[:3])}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Alertas de alquiler en Sevilla y área metropolitana")
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--state", default=str(ROOT / "state" / "seen.json"))
    ap.add_argument("--dry-run", action="store_true", help="no envía nada ni guarda estado")
    ap.add_argument("--portals", default=os.environ.get("PISOS_PORTALS", ""),
                    help="lista separada por comas; por defecto, todos")
    ap.add_argument("--seed", action="store_true",
                    help="marca lo visible como visto sin enviar avisos")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
