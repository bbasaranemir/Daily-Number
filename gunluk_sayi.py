#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Her sabah kurallara uyan optimize sayi kombinasyonu uretir ve
sonucu Telegram uzerinden mesaj olarak gonderir.

Gerekli ortam degiskenleri (GitHub Secrets):
  TELEGRAM_BOT_TOKEN  -> BotFather'dan alinan bot token
  TELEGRAM_CHAT_ID    -> mesajin gonderilecegi chat id

Ek bagimlilik yok; sadece Python standart kutuphanesi kullanilir.
"""
import os
import json
import random
import urllib.request
from datetime import datetime, timezone, timedelta

STEP = 10
LOW_MIN, LOW_MAX = 10000, 10900      # ozel aralik (tam 2 sayi)
HIGH_MIN, HIGH_MAX = 10910, 11900    # geri kalan
TARGET_MIN, TARGET_MAX = 400000, 452000

LOW_POOL = list(range(LOW_MIN, LOW_MAX + 1, STEP))
HIGH_POOL = list(range(HIGH_MIN, HIGH_MAX + 1, STEP))


def hundred_bucket(n):
    return n // 100


def try_arrange(numbers, low_set, attempts=800):
    n = len(numbers)
    for _ in range(attempts):
        arr = numbers[:]
        random.shuffle(arr)
        if arr[0] in low_set or arr[-1] in low_set:
            continue
        ok = True
        for i in range(1, n):
            if hundred_bucket(arr[i - 1]) == hundred_bucket(arr[i]):
                ok = False
                break
        if not ok:
            continue
        return arr
    return None


def score(arr):
    s = 0
    total = sum(arr)
    if TARGET_MIN <= total <= TARGET_MAX:
        s += 40
    buckets = set(hundred_bucket(x) for x in arr)
    s += min(20, int(len(buckets) / len(arr) * 25))
    small = sum(1 for i in range(1, len(arr)) if abs(arr[i] - arr[i - 1]) < 100)
    s += 20 if small == 0 else max(0, 20 - small * 4)
    ups = sum(1 for i in range(1, len(arr)) if arr[i] > arr[i - 1])
    ratio = ups / (len(arr) - 1)
    s += 10 if 0.35 <= ratio <= 0.65 else 5
    s += 10
    return s


def build_candidate():
    lows = random.sample(LOW_POOL, 2)
    low_sum = sum(lows)
    remaining_target = random.randint(400000, 418000) - low_sum
    est_count = max(1, round(remaining_target / 11700))
    for count in range(est_count, est_count + 12):
        if count > len(HIGH_POOL):
            break
        for _ in range(60):
            highs = random.sample(HIGH_POOL, count)
            total = low_sum + sum(highs)
            if total < TARGET_MIN or total > TARGET_MAX:
                continue
            arranged = try_arrange(lows + highs, set(lows))
            if arranged is None:
                continue
            return arranged, set(lows), total
    return None


def generate(num_candidates=600):
    best = None
    best_key = None
    for _ in range(num_candidates):
        c = build_candidate()
        if c is None:
            continue
        arr, low_set, total = c
        sc = score(arr)
        key = (sc, -len(arr), -(total - TARGET_MIN))
        if best_key is None or key > best_key:
            best_key = key
            best = (arr, low_set, total, sc)
    return best


def validate(arr, low_set, total):
    errs = []
    if any(x % 10 != 0 for x in arr):
        errs.append("10'un kati degil")
    if any(not (10000 <= x <= 11900) for x in arr):
        errs.append("aralik disi")
    if len(set(arr)) != len(arr):
        errs.append("tekrar var")
    if len([x for x in arr if 10000 <= x <= 10900]) != 2:
        errs.append("ozel aralik sayisi != 2")
    if arr[0] in low_set or arr[-1] in low_set:
        errs.append("ozel sayi ilk/son sirada")
    if total < 400000:
        errs.append("toplam < 400000")
    for i in range(1, len(arr)):
        if hundred_bucket(arr[i]) == hundred_bucket(arr[i - 1]):
            errs.append("ayni yuzluk dilim ardisik")
            break
    return errs


def format_output(arr, low_set, total):
    lows = sorted(x for x in arr if x in low_set)
    running = 0
    cross = {300000: None, 350000: None, 400000: None}
    for idx, v in enumerate(arr, start=1):
        running += v
        for lvl in cross:
            if cross[lvl] is None and running >= lvl:
                cross[lvl] = idx
    tr = timezone(timedelta(hours=3))
    tarih = datetime.now(tr).strftime("%d.%m.%Y")
    total_str = f"{total:,}".replace(",", ".")

    # Sayilari 5'er 5'er satirlara bol.
    row = []
    number_lines = []
    for v in arr:
        row.append(str(v))
        if len(row) == 5:
            number_lines.append(", ".join(row))
            row = []
    if row:
        number_lines.append(", ".join(row))

    lines = [
        f"Gunluk Sayi Kombinasyonu ({tarih})",
        "",
        "Sayi listesi:",
        "\n".join(number_lines),
        "",
        f"Toplam deger: {total_str}",
        f"Kullanilan sayi adedi: {len(arr)}",
        "",
        "Kademe gecis siralari:",
        f"  <b>300.000 -> {cross[300000]}. sayida</b>",
        f"  <b>350.000 -> {cross[350000]}. sayida</b>",
        f"  <b>400.000 -> {cross[400000]}. sayida</b>",
        "",
        f"Ozel 10.000-10.900 araligindaki iki sayi: {lows[0]}, {lows[1]}",
    ]
    return "\n".join(lines)


def send_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID tanimli degil.")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps(
        {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    ).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def build_message():
    best = generate()
    if best is None:
        return "Uygun kombinasyon uretilemedi."
    arr, low_set, total, _ = best
    errs = validate(arr, low_set, total)
    if errs:
        return "DOGRULAMA HATASI: " + "; ".join(errs)
    return format_output(arr, low_set, total)


if __name__ == "__main__":
    message = build_message()
    print(message)
    send_telegram(message)
    print("\n[OK] Telegram'a gonderildi.")
