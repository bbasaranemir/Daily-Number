#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gun ici 'damla damla' mod + Telegram komutlari.

Sayilari SIRAYLA tek tek Telegram'a gonderir (her mesajda kumulatif toplam
ve ilerleme). Gun sonunda ozet gonderir. Ayrica gelen komutlari isler:
  /bugun   -> bugunun tam listesi + toplam
  /kalan   -> kac sayi kaldi, sonraki gonderim, durum
  /simdi   -> sirdaki sayiyi HEMEN gonder
  /durdur  -> gun ici gonderimi duraklat
  /devam   -> gonderimi surdur
  /yardim  -> komut listesi

Gun tipine gore pencere:
  - Hafta ici: 08:10-08:15 (rastgele) baslar, ~18:15-18:20'ye kadar.
  - Cumartesi: 09:10 - 13:45.
  - Pazar: calismaz.
Sayilar arasi sure: rastgele 12-15 dk.

Not: Komutlar sadece calisma penceresinde (bu betigin tetiklendigi saatlerde,
08:00-18:59) yanitlanir.

Ortam degiskenleri: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import os
import json
import random
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

TR = timezone(timedelta(hours=3))
HISTORY_FILE = os.environ.get("HISTORY_FILE", "gecmis.jsonl")
STATE_FILE = os.environ.get("STATE_FILE", "damla_durum.json")
GAP_MIN, GAP_MAX = 12, 15


def now_tr():
    return datetime.now(TR)


def today_str():
    return now_tr().strftime("%Y-%m-%d")


def fmt(n):
    return f"{n:,}".replace(",", ".")


def day_window(n):
    wd = n.weekday()  # 0=Pzt .. 5=Cmt, 6=Paz
    if wd == 5:
        start = n.replace(hour=9, minute=10, second=0, microsecond=0)
        end = n.replace(hour=13, minute=45, second=0, microsecond=0)
    else:
        start = n.replace(hour=8, minute=random.randint(10, 15),
                          second=0, microsecond=0)
        end = n.replace(hour=18, minute=random.randint(15, 20),
                        second=0, microsecond=0)
    return start, end


def load_today_numbers():
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
    return found.get("sayilar") if found else None


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(st):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)


# ---------------- Telegram ----------------

def _token():
    t = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not t:
        raise RuntimeError("TELEGRAM_BOT_TOKEN tanimli degil.")
    return t


def send_telegram(text):
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID tanimli degil.")
    url = f"https://api.telegram.org/bot{_token()}/sendMessage"
    data = json.dumps(
        {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    ).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def get_updates(offset):
    q = urllib.parse.urlencode({"timeout": 0, "offset": offset})
    url = f"https://api.telegram.org/bot{_token()}/getUpdates?{q}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8")).get("result", [])
    except Exception:
        return []


# ---------------- yardimci metinler ----------------

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


def drip_text(numbers, idx):
    val = numbers[idx]
    cum = sum(numbers[: idx + 1])
    kalan = len(numbers) - (idx + 1)
    return (
        f"{idx + 1}. sayi: <b>{val}</b>\n"
        f"Buraya kadar toplam: <b>{fmt(cum)}</b>\n"
        f"Ilerleme: {idx + 1}/{len(numbers)} (kalan {kalan})"
    )


def closing_summary(numbers, sent_count):
    return "\n".join([
        f"<b>Gun sonu ozeti ({now_tr().strftime('%d.%m.%Y')})</b>",
        "",
        f"Gonderilen: {sent_count}/{len(numbers)} sayi",
        f"Gunun toplami: <b>{fmt(sum(numbers))}</b>",
        "",
        "Bugunku liste:",
        format_list_5x5(numbers),
    ])


def send_next(st, numbers, force=False):
    """Sirdaki sayiyi gonder, sirayi ilerlet. force: /simdi icin."""
    idx = int(st.get("index", 0))
    if idx >= len(numbers):
        if force:
            send_telegram("Bugun tum sayilar zaten gonderildi.")
        return False
    send_telegram(drip_text(numbers, idx))
    st["index"] = idx + 1
    st["next_iso"] = (now_tr() + timedelta(minutes=random.randint(GAP_MIN, GAP_MAX))).isoformat()
    return True


# ---------------- komut isleme ----------------

HELP = (
    "Komutlar:\n"
    "/bugun - bugunun tam listesi\n"
    "/kalan - kac sayi kaldi + sonraki gonderim\n"
    "/simdi - sirdaki sayiyi hemen gonder\n"
    "/durdur - gonderimi duraklat\n"
    "/devam - gonderimi surdur"
)


def handle_kalan(st, numbers):
    idx = int(st.get("index", 0))
    kalan = len(numbers) - idx
    if kalan <= 0:
        send_telegram("Bugun tum sayilar gonderildi.")
        return
    parca = [f"Kalan: <b>{kalan}</b>/{len(numbers)} sayi."]
    try:
        nt = datetime.fromisoformat(st["next_iso"])
        parca.append(f"Sonraki gonderim ~{nt.strftime('%H:%M')}.")
    except Exception:
        pass
    if st.get("paused"):
        parca.append("Durum: DURAKLATILDI (/devam ile surdur).")
    send_telegram(" ".join(parca))


def process_commands(st, numbers):
    """Gelen /komutlari isle. numbers bos olabilir."""
    chat_id = str(os.environ.get("TELEGRAM_CHAT_ID", ""))
    last = int(st.get("last_update_id", 0))
    offset = last + 1 if last else 0
    updates = get_updates(offset)
    for u in updates:
        st["last_update_id"] = u.get("update_id", last)
        msg = u.get("message") or u.get("edited_message")
        if not msg:
            continue
        if str(msg.get("chat", {}).get("id")) != chat_id:
            continue
        text = (msg.get("text") or "").strip()
        if not text.startswith("/"):
            continue
        cmd = text.split()[0].lstrip("/").split("@")[0].lower()

        if cmd == "bugun":
            if numbers:
                send_telegram(
                    f"<b>Bugunku liste ({now_tr().strftime('%d.%m.%Y')})</b>\n\n"
                    + format_list_5x5(numbers)
                    + f"\n\nToplam: <b>{fmt(sum(numbers))}</b>  ·  Adet: {len(numbers)}"
                )
            else:
                send_telegram("Bugunku liste henuz hazir degil.")
        elif cmd == "kalan":
            if numbers:
                handle_kalan(st, numbers)
            else:
                send_telegram("Bugunku liste henuz hazir degil.")
        elif cmd == "simdi":
            if numbers:
                send_next(st, numbers, force=True)
            else:
                send_telegram("Bugunku liste henuz hazir degil.")
        elif cmd == "durdur":
            st["paused"] = True
            send_telegram("Gonderim duraklatildi. /devam ile surdurebilirsin.")
        elif cmd == "devam":
            st["paused"] = False
            send_telegram("Gonderim devam ediyor.")
        elif cmd in ("yardim", "help", "start", "komut", "komutlar"):
            send_telegram(HELP)


# ---------------- ana akis ----------------

def run():
    n = now_tr()
    st = load_state()
    # Yeni gun VEYA eski/eksik formatli durum -> gunu bastan kur (cokme olmaz).
    if st.get("date") != today_str() or "end_iso" not in st:
        start, end = day_window(n)
        st = {
            "date": today_str(),
            "index": 0,
            "next_iso": start.isoformat(),
            "end_iso": end.isoformat(),
            "closed": False,
            "paused": False,
            "last_update_id": int(st.get("last_update_id", 0)),  # gunler arasi tasi
        }

    numbers = load_today_numbers()

    # 1) Komutlari her zaman isle (liste yoksa bile).
    process_commands(st, numbers or [])

    if not numbers:
        save_state(st)
        return "liste yok (komutlar islendi)"

    end_dt = datetime.fromisoformat(st["end_iso"])

    # 2) Pencere bitti -> gun sonu ozeti (bir kez).
    if n >= end_dt:
        if not st.get("closed"):
            send_telegram(closing_summary(numbers, int(st.get("index", 0))))
            st["closed"] = True
        save_state(st)
        return "kapanis / bekleme"

    # 3) Pencere icinde -> vakti geldiyse ve duraklatilmadiysa sirdakini gonder.
    idx = int(st.get("index", 0))
    result = "islem yok"
    if idx < len(numbers) and not st.get("paused"):
        try:
            next_time = datetime.fromisoformat(st["next_iso"])
        except Exception:
            next_time = n
        if n >= next_time:
            send_next(st, numbers)
            result = f"gonderildi (sira {st['index']}/{len(numbers)})"

    save_state(st)
    return result


if __name__ == "__main__":
    print(run())
