#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gun ici 'damla damla' mod:
O GUNUN listesindeki sayilari SIRAYLA tek tek Telegram'a gonderir.
Her mesajda o ana kadarki kumulatif toplam ve ilerleme de yazar.
Gun sonunda gun sonu ozeti gonderir.

Gun tipine gore calisma penceresi:
  - Hafta ici (Pzt-Cuma): ilk sayi 08:10-08:15 arasi RASTGELE bir dakikada
    baslar, son sayi ~18:15-18:20'ye kadar gelir.
  - Cumartesi: 09:10 - 13:45 arasi calisir (o gun daha az sayi uretilir).
  - Pazar: calismaz (cron zaten tetiklemez).

Sayilar arasi sure her seferinde RASTGELE 12-15 dakikadir.

- Gunun listesi sabah (07:30) uretilip gecmis.jsonl'e yazilan son kayittir.
- Durum damla_durum.json'da tutulur (sira, sonraki gonderim, pencere, kapanis).
- Bu betik dakikada bir tetiklenir; sadece vakti geldiyse islem yapar.

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
GAP_MIN, GAP_MAX = 12, 15   # sayilar arasi dakika (rastgele)


def now_tr():
    return datetime.now(TR)


def today_str():
    return now_tr().strftime("%Y-%m-%d")


def fmt(n):
    return f"{n:,}".replace(",", ".")


def day_window(n):
    """Gun tipine gore (baslangic, bitis) datetime. Hafta ici rastgele dakikali."""
    wd = n.weekday()  # 0=Pzt .. 5=Cmt, 6=Paz
    if wd == 5:  # Cumartesi
        start = n.replace(hour=9, minute=10, second=0, microsecond=0)
        end = n.replace(hour=13, minute=45, second=0, microsecond=0)
    else:        # Hafta ici
        start = n.replace(hour=8, minute=random.randint(10, 15),
                          second=0, microsecond=0)
        end = n.replace(hour=18, minute=random.randint(15, 20),
                        second=0, microsecond=0)
    return start, end


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


def format_list_5x5(numbers):
    rows, row = [], []
    for v in numbers:
        row.append(str(v))
        if len(row) == 5:
            rows.append(", ".join(row))
            row = []
    if row:
        rows.append(", ".join(row))
    return "\n".join(rows)


def closing_summary(numbers, sent_count):
    total = sum(numbers)
    lines = [
        f"<b>Gun sonu ozeti ({now_tr().strftime('%d.%m.%Y')})</b>",
        "",
        f"Gonderilen: {sent_count}/{len(numbers)} sayi",
        f"Gunun toplami: <b>{fmt(total)}</b>",
        "",
        "Bugunku liste:",
        format_list_5x5(numbers),
    ]
    return "\n".join(lines)


def run():
    n = now_tr()
    numbers = load_today_numbers()
    if not numbers:
        return "bugunun listesi henuz yok"

    st = load_state()
    if st.get("date") != today_str():
        start, end = day_window(n)
        st = {
            "date": today_str(),
            "index": 0,
            "next_iso": start.isoformat(),
            "end_iso": end.isoformat(),
            "closed": False,
        }
        save_state(st)

    end_dt = datetime.fromisoformat(st["end_iso"])

    # ---- Pencere bitti: gun sonu ozeti (bir kez) ----
    if n >= end_dt:
        if not st.get("closed"):
            send_telegram(closing_summary(numbers, int(st.get("index", 0))))
            st["closed"] = True
            save_state(st)
            return "kapanis ozeti gonderildi"
        return "zaten kapatildi"

    # ---- Pencere icinde: sayilari sirayla gonder ----
    idx = int(st.get("index", 0))
    if idx >= len(numbers):
        return "bugun tum sayilar gonderildi (kapanis pencere sonunda)"

    next_time = datetime.fromisoformat(st["next_iso"])
    if n < next_time:
        return "henuz vakit yok / baslamadi"

    val = numbers[idx]
    cum = sum(numbers[: idx + 1])
    kalan = len(numbers) - (idx + 1)
    text = (
        f"{idx + 1}. sayi: <b>{val}</b>\n"
        f"Buraya kadar toplam: <b>{fmt(cum)}</b>\n"
        f"Ilerleme: {idx + 1}/{len(numbers)} (kalan {kalan})"
    )
    send_telegram(text)

    gap = random.randint(GAP_MIN, GAP_MAX)
    st["index"] = idx + 1
    st["next_iso"] = (n + timedelta(minutes=gap)).isoformat()
    save_state(st)
    return f"gonderildi: {val} (sira {idx + 1}/{len(numbers)}), sonraki ~{gap} dk sonra"


if __name__ == "__main__":
    print(run())
