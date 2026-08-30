# pisos-bot

Alertas de alquiler para Sevilla y su área metropolitana, agregando varios
portales en un único canal de Telegram y ordenando por lo que realmente
importa: **conexión con Sevilla en transporte público y precio/m² frente a la
zona**.

Corre solo en GitHub Actions cada 10 minutos. No hay que tener el ordenador
encendido.

---

## Qué busca

| Criterio | Valor |
|---|---|
| Precio | 280 – 700 €/mes |
| Zona | Sevilla capital, Aljarafe hasta Coria del Río, Dos Hermanas (incl. Montequinto) y Alcalá de Guadaíra |
| Tipo | Vivienda completa (se excluyen habitaciones, pisos compartidos y alquiler de temporada) |
| Superficie | ≥ 25 m² |

Todo esto se cambia en [`config.yaml`](config.yaml). Un `git push` basta: la
siguiente ronda ya usa la configuración nueva.

## Portales

| Portal | Cobertura | Datos que aporta | ¿Desde GitHub Actions? |
|---|---|---|---|
| **Fotocasa** | Provincia entera, filtrada y ordenada por fecha | JSON embebido: coordenadas GPS, hora exacta de publicación, particular/agencia | ❌ 403 |
| **pisos.com** | Comarcas Sevilla capital, Aljarafe y Área de Sevilla | Coordenadas vía `ld+json` | ✅ |
| **Habitaclia** | 6 municipios principales | Particular/agencia | ✅ |
| **Milanuncios** | Provincia, ordenado por fecha | Muchos particulares | ❌ 403 |

**Fotocasa y Milanuncios bloquean las IPs de centro de datos**, así que desde
los runners de GitHub devuelven 403; desde una conexión doméstica funcionan sin
problema. Por eso el workflow de la nube corre solo con `PISOS_PORTALS=pisos_com,habitaclia`.
Para recuperar los otros dos hay que ejecutar desde una IP residencial
(`--portals fotocasa,milanuncios` en el Mac, o un runner self-hosted).

**Idealista no está**, y conviene saber por qué: bloquea el acceso automatizado
con DataDome y devuelve 403 a cualquier petición. Su API oficial son 100
llamadas al mes, insuficiente. La vía practicable es reenviar sus alertas de
correo a un buzón y leerlo por IMAP; el código está preparado para añadir esa
fuente como un portal más sin tocar el resto.

Fotocasa, Habitaclia y Milanuncios son del mismo grupo (Scout24) y comparten
inventario, así que el bot deduplica entre portales antes de avisar.

## Filtro de alquiler por habitaciones

El falso positivo más caro del bot: un anuncio que dice "piso de 3 habitaciones"
pero que en la descripción alquila **por habitaciones**. Lleva el precio de una
habitación sobre la superficie del piso entero, así que su €/m² sale ridículo y
el detector de chollos lo manda a lo más alto de la lista. Se filtra en dos
capas:

**1. Reglas** ([`shared_rental.py`](pisosbot/shared_rental.py)) — patrones de
alta precisión: `300€/habitación`, `busco compañera de piso`, `se alquilan
habitaciones`, `quedan 2 habitaciones libres`. No usa `slugify()` a propósito,
porque borra el símbolo de moneda y entonces `300€/habitación` y `consta de 1
habitación` quedan idénticos. Cubierto por 17 pruebas en las dos direcciones.

**2. Clasificador** ([`llm.py`](pisosbot/llm.py)) — Gemini juzga lo que las
reglas no pueden, del tipo *"piso exclusivo para estudiantes curso 2026-2027"*,
donde hace falta entender la intención. Devuelve `completa`, `compartida` o
`dudoso`: los `compartida` se descartan y los `dudoso` **sí se envían**, con un
⚠️ en el mensaje. No perder un piso pesa más que ahorrarte un aviso.

Es opcional: sin `GEMINI_API_KEY` el bot funciona igual, solo con las reglas.

### Orden de las operaciones

Marcar → deduplicar → descartar, y todo antes de calcular medianas. Importa:

- Un mismo piso se publica dos veces con la descripción **cortada en distinto
  sitio**, y solo una copia enseña el `300€/habitación`. Si se descarta antes de
  deduplicar, muere la copia delatora y sobrevive la limpia. Marcando primero,
  el indicio de una copia tumba al grupo entero.
- Si un anuncio de habitación llega al cálculo de medianas, hunde el €/m² de
  referencia de toda la zona y estropea la detección de chollos del resto.

### Gasto

Una sola petición por ronda con todos los anuncios nuevos juntos, y ninguna
cuando no hay novedades: como mucho ~144 llamadas al día. Los veredictos se
cachean en `state/seen.json`, así que un anuncio nunca se pregunta dos veces.

Si Gemini falla, agota cuota o responde algo raro, **pasan todos los anuncios**.
Perder un piso por una caída de terceros sería peor que un aviso de más.

## Cómo puntúa

Nota de 0 a 100 por anuncio:

- **Transporte (40 %)** — distancia real a la estación más cercana, calculada
  sobre las coordenadas del anuncio y los datos de estaciones de OpenStreetMap
  ([`data/stations.json`](data/stations.json)). Metro puntúa por encima de
  Cercanías; los municipios sin ferrocarril parten de una nota base según lo
  bien conectados que estén por autobús.
- **Precio (35 %)** — €/m² del piso frente a la mediana de su municipio,
  calculada con todos los anuncios vigentes de esa ronda. Así el baremo es el
  mercado de esta semana, no una cifra fija.
- **Frescura (10 %)** — cuánto hace que se publicó.
- **Particular (15 %)** — sin honorarios de agencia y suelen responder antes.

Por encima de 78 el aviso llega marcado con 🔥.

## Puesta en marcha

**1. Crear el bot de Telegram**

Habla con [@BotFather](https://t.me/BotFather), manda `/newbot` y guarda el
token. Abre un chat con tu bot nuevo, mándale cualquier mensaje y luego:

```bash
python3 scripts/telegram_setup.py <TU_TOKEN>
```

Te imprime el `chat_id`.

**2. Guardar las credenciales como secretos del repo**

```bash
gh secret set TELEGRAM_BOT_TOKEN --body '<TU_TOKEN>'
gh secret set TELEGRAM_CHAT_ID  --body '<TU_CHAT_ID>'
```

**Opcional — clasificador de anuncios.** Saca una clave gratuita en
[Google AI Studio](https://aistudio.google.com/apikey) y añádela:

```bash
gh secret set GEMINI_API_KEY --body '<TU_CLAVE>'
```

Sin ella el bot funciona igual, solo con la capa de reglas. Ten en cuenta que
en el tier gratuito Google puede usar lo que se le manda para entrenar; aquí
son descripciones públicas de anuncios de alquiler.

Los secretos no son visibles aunque el repositorio sea público.

**3. Ya está.** El workflow arranca solo. Para lanzarlo a mano:

```bash
gh workflow run "Buscar pisos"
```

### Por qué el repositorio es público

GitHub da minutos de Actions **ilimitados y gratis en repos públicos**. En uno
privado son 2.000 minutos al mes y cada ejecución redondea a 1 minuto, así que
un cron de 10 minutos (≈4.300 al mes) se saldría del plan gratuito. En el repo
solo queda la configuración de búsqueda; el token va en *Secrets*.

## Uso en local

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m pisosbot.main --dry-run   # simula, no envía ni guarda
for f in tests/test_*.py; do ./.venv/bin/python "$f"; done   # pruebas
```

`--dry-run` imprime los mejores anuncios con su nota y el desglose, sin tocar
Telegram ni el estado.

### Mirar Fotocasa y Milanuncios a mano

Son los dos que GitHub no puede ver, pero desde tu conexión sí responden. Este
comando no necesita credenciales y no toca el estado ni Telegram:

```bash
./.venv/bin/python -m pisosbot.main --portals fotocasa,milanuncios --dry-run
```

Útil cuando quieras barrer a fondo antes de una tanda de visitas.

### Después de cambiar los filtros

Si tocas `config.yaml` y se amplía la búsqueda, `--seed` marca todo lo visible
como visto para que la siguiente ronda no te mande 40 avisos de golpe:

```bash
./.venv/bin/python -m pisosbot.main --seed
```

## Cómo está montado

```
pisosbot/
├── portals/      un módulo por portal, todos devuelven el mismo modelo
├── filters.py    descartes duros (precio, zona, habitaciones, temporada)
├── dedupe.py     colapsa el mismo piso publicado en varios portales
├── scoring.py    nota 0-100 y detección de chollos
├── transport.py  distancia a metro/Cercanías
├── notify.py     mensajes de Telegram
└── main.py       orquestador
```

Añadir un portal es crear un módulo en `portals/` que devuelva `list[Listing]`
y registrarlo en `portals/__init__.py`.

### Estado

`state/seen.json` guarda los anuncios ya avisados y se commitea al repo (en
Actions no hay disco persistente). Se limpia solo a los 45 días. Guarda también
una huella `precio+superficie+municipio` para no repetir un piso que reaparece
en otro portal o vuelve a publicarse.

En la primera ejecución no inunda: manda los mejores y marca el resto como
vistos.

## Notas

- El sondeo es de uso personal y a bajo volumen, con pausa entre peticiones.
  Subir la frecuencia o quitar las pausas es mala idea.
- Si un portal cambia su HTML, ese portal deja de aportar anuncios pero el
  resto sigue funcionando: los fallos de parseo se registran y se ignoran.
- Los datos de estaciones se regeneran con
  `python3 scripts/build_stations.py` si cambia la red de transporte.
