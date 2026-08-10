#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Haftalik / aylik ozet raporu uretip Telegram'a gonderir.

Kullanim:
  python rapor.py hafta   -> son 7 gunun ozeti
  python rapor.py ay      -> son 30 gunun ozeti

gecmis.jsonl'i okur (her tarih icin son kayit = o gunun cekilisi).
Ortam degiskenleri: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import os
import sys
import json
import urllib.request
from datetime import datetime, timezone, timedelta

TR = timezone(timedelta(hours=3))
HISTORY_FILE = os.environ.get("HISTORY_FILE", "gecmis.jsonl")


def fmt(n):
    return f"{n:,}".replace(",", ".")


def load_days():
    """Her tarih icin son kaydi al -> gunluk cekilis listesi (tarih sirali)."""
    by_date = {}
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if "tarih" in rec and "sayilar" in rec:
                by_date[rec["tarih"]] = rec
    return [by_date[d] for d in sorted(by_date)]


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


def build_report(mode):
    gun = 30 if mode == "ay" else 7
    baslik = "Aylik Rapor" if mode == "ay" else "Haftalik Rapor"
    now = datetime.now(TR)
    cutoff = (now - timedelta(days=gun)).strftime("%Y-%m-%d")
    bugun = now.strftime("%Y-%m-%d")

    days = [d for d in load_days() if d["tarih"] >= cutoff]
    if not days:
        return f"<b>{baslik}</b>\n\nBu donemde kayit bulunamadi."

    totals = [d["toplam"] for d in days]
    counts = [d["adet"] for d in days]
    ort_top = round(sum(totals) / len(totals))
    ort_adet = round(sum(counts) / len(counts))
    hi = max(days, key=lambda d: d["toplam"])
    lo = min(days, key=lambda d: d["toplam"])

    # sayi frekanslari
    freq = {}
    for d in days:
        for n in d["sayilar"]:
            freq[n] = freq.get(n, 0) + 1
    en_cok = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    toplam_olasi = len(range(10000, 11901, 10))
    hic = sum(1 for n in range(10000, 11901, 10) if n not in freq)

    def d2(s):  # 2026-08-10 -> 10.08
        p = s.split("-")
        return f"{p[2]}.{p[1]}"

    en_cok_str = ", ".join(f"{n} ({c}x)" for n, c in en_cok)

    lines = [
        f"<b>{baslik}</b>",
        f"Donem: {d2(cutoff)} - {d2(bugun)} (son {gun} gun)",
        "",
        f"Oynanan gun: <b>{len(days)}</b>",
        f"Ortalama toplam: <b>{fmt(ort_top)}</b>",
        f"En yuksek: {fmt(hi['toplam'])} ({d2(hi['tarih'])})",
        f"En dusuk: {fmt(lo['toplam'])} ({d2(lo['tarih'])})",
        f"Ortalama sayi adedi: <b>{ort_adet}</b>",
        "",
        "En cok cikan sayilar:",
        en_cok_str,
        "",
        f"Hic cikmayan sayi: {hic}/{toplam_olasi}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "hafta"
    if mode not in ("hafta", "ay"):
        mode = "hafta"
    msg = build_report(mode)
    print(msg)
    send_telegram(msg)
    print("\n[OK] Rapor Telegram'a gonderildi.")
