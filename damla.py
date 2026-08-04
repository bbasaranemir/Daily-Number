#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gun ici 'damla damla' mod:
08:00-18:00 (TR) arasinda, her ~13-15 dakikada bir, O GUNUN listesindeki
sayilari SIRAYLA tek tek Telegram'a gonderir.

- Gunun listesi sabah (07:30) uretilip gecmis.jsonl'e yazilan son kayittir.
- Durum (kacinci sayidayiz, sonraki gonderim ne zaman) damla_durum.json'da tutulur.
- Bu betik dakikada bir tetiklenir; sadece vakti geldiyse bir sayi gonderir.

Ortam degiskenleri: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import os
import json
import random
import urllib.request
from datetime import datetime, timezone, timedelta

TR = timezone(timedelta(hours=3))
HISTORY_FILE = os.environ.get("HISTORY_FILE", "gecmis.jsonl")
STATE_FILE = os.environ.get("STATE_FILE", "damla_durum.json")
START_HOUR = 8       # 08:00
END_HOUR = 18        # 18:00 (bu saatte artik gonderilmez)
GAP_MIN, GAP_MAX = 13, 15   # dakika araligi


def now_tr():
    return datetime.now(TR)


def today_str():
    return now_tr().strftime("%Y-%m-%d")


def load_today_numbers():
    """gecmis.jsonl icinde bugune ait son kaydin sayilarini don."""
    if not os.path.exists(HISTORY_FILE):
        return None
    found = None
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("tarih") == today_str():
                    found = rec
    except Exception:
        return None
    if found:
        return found.get("sayilar")
    return None


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(st):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)


def send_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID tanimli degil.")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps(
        {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    ).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def run():
    n = now_tr()
    # Calisma penceresi disindaysa hicbir sey yapma.
    if not (START_HOUR <= n.hour < END_HOUR):
        return "pencere disi"

    numbers = load_today_numbers()
    if not numbers:
        return "bugunun listesi henuz yok"

    st = load_state()
    if st.get("date") != today_str():
        # Yeni gun: bastan basla, ilk sayiyi hemen gonderilebilir yap.
        st = {"date": today_str(), "index": 0, "next_iso": n.isoformat()}

    idx = int(st.get("index", 0))
    if idx >= len(numbers):
        save_state(st)
        return "bugun tum sayilar gonderildi"

    next_time = datetime.fromisoformat(st.get("next_iso"))
    if n < next_time:
        return "henuz vakit yok"

    # Sirdaki sayiyi gonder.
    val = numbers[idx]
    text = f"{idx + 1}. sayi: <b>{val}</b>"
    send_telegram(text)

    gap = random.randint(GAP_MIN, GAP_MAX)
    st["index"] = idx + 1
    st["next_iso"] = (n + timedelta(minutes=gap)).isoformat()
    save_state(st)
    return f"gonderildi: {val} (sira {idx + 1}/{len(numbers)}), sonraki ~{gap} dk sonra"


if __name__ == "__main__":
    print(run())
