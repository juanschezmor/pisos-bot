"""Averigua tu TELEGRAM_CHAT_ID.

    1. Habla con @BotFather en Telegram y manda /newbot. Te dara un token.
    2. Abre un chat con TU bot recien creado y mandale cualquier mensaje.
    3. python3 scripts/telegram_setup.py <TOKEN>
"""
import json
import sys
import urllib.request


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    token = sys.argv[1].strip()

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.load(r)
    except Exception as exc:
        print(f"No se pudo consultar la API de Telegram: {exc}")
        return 1

    if not data.get("ok"):
        print(f"Telegram rechaza el token: {data}")
        return 1

    chats = {}
    for update in data.get("result", []):
        msg = update.get("message") or update.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if chat.get("id"):
            name = chat.get("username") or chat.get("first_name") or chat.get("title") or "?"
            chats[chat["id"]] = name

    if not chats:
        print("Sin mensajes recientes. Manda algo a tu bot desde Telegram y repite.")
        return 1

    print("Chats encontrados:")
    for chat_id, name in chats.items():
        print(f"  TELEGRAM_CHAT_ID = {chat_id}   ({name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
