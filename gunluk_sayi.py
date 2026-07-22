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
TARGET = 500000                      # hedef toplam (altina dusmez)
TARGET_MAX = 560000                  # ustunde kalabilecegi tavan
LEVELS = [300000, 400000, 500000]    # kademe gecis seviyeleri

LOW_POOL = list(range(LOW_MIN, LOW_MAX + 1, STEP))
HIGH_POOL = list(range(HIGH_MIN, HIGH_MAX + 1, STEP))


def hundred_bucket(n):
    return n // 100


def arrange(nums, low_set, tries=40):
    """
    Sayilari kurallara gore diz:
    - ayni yuzluk dilimden ardisik iki sayi gelmesin,
    - ozel (baraj) 2 sayi ilk/son sirada olmasin.
    Yuzluk dilimlere gore acgozlu (greedy) yerlestirme; en dolu dilimden
    baslayarak bir onceki dilimle ayni olmayan sayiyi koyar.
    """
    for _ in range(tries):
        buckets = {}
        for x in nums:
            buckets.setdefault(hundred_bucket(x), []).append(x)
        for b in buckets:
            random.shuffle(buckets[b])
        result = []
        last_b = None
        ok = True
        total_left = len(nums)
        while total_left > 0:
            cand = [b for b in buckets if buckets[b] and b != last_b]
            if not cand:
                ok = False
                break
            maxlen = max(len(buckets[b]) for b in cand)
            choice = random.choice([b for b in cand if len(buckets[b]) == maxlen])
            result.append(buckets[choice].pop())
            last_b = choice
            total_left -= 1
        if not ok or len(result) != len(nums):
            continue
        if result[0] in low_set or result[-1] in low_set:
            # ozel sayilari uclardan ic tarafa tasi
            fixed = _keep_lows_inside(result, low_set)
            if fixed is None:
                continue
            result = fixed
        return result
    return None


def _keep_lows_inside(arr, low_set):
    n = len(arr)
    arr = arr[:]
    for end in (0, n - 1):
        if arr[end] in low_set:
            swapped = False
            for j in range(2, n - 2):
                if arr[j] in low_set:
                    continue
                a = arr[j]
                # takas sonrasi yuzluk dilim kurali bozulmasin
                if _bucket_ok_after_swap(arr, end, j):
                    arr[end], arr[j] = arr[j], arr[end]
                    swapped = True
                    break
            if not swapped:
                return None
    if arr[0] in low_set or arr[-1] in low_set:
        return None
    return arr


def _bucket_ok_after_swap(arr, i, j):
    n = len(arr)
    tmp = arr[:]
    tmp[i], tmp[j] = tmp[j], tmp[i]
    for k in (i, j):
        if k > 0 and hundred_bucket(tmp[k]) == hundred_bucket(tmp[k - 1]):
            return False
        if k < n - 1 and hundred_bucket(tmp[k]) == hundred_bucket(tmp[k + 1]):
            return False
    return True


def spread_score(arr):
    """Dagilim/cesitlilik puani: genis aralik + buyuk komsu farklari."""
    buckets = len(set(hundred_bucket(x) for x in arr))
    value_range = max(arr) - min(arr)
    diffs = [abs(arr[i] - arr[i - 1]) for i in range(1, len(arr))]
    avg_diff = sum(diffs) / len(diffs)
    small = sum(1 for d in diffs if d < 100)
    # normalize edilmis bilesenler
    s = 0.0
    s += buckets * 6.0                       # ne kadar cok dilim o kadar iyi
    s += (value_range / 1900.0) * 20.0       # genis aralik
    s += min(avg_diff / 10.0, 40.0)          # buyuk komsu farklari
    s -= small * 5.0                          # kucuk farklar cezasi
    return s


def build_candidate():
    lows = random.sample(LOW_POOL, 2)
    low_sum = sum(lows)
    need_min = TARGET - low_sum
    # highs icin gereken en az adet (buyuk sayilarla)
    sorted_desc = sorted(HIGH_POOL, reverse=True)
    k = 1
    running = 0
    for i, v in enumerate(sorted_desc, start=1):
        running += v
        if running >= need_min:
            k = i
            break
    # min adet ve birkac fazlasini dene (dagilim icin biraz esneklik)
    for count in range(k, min(k + 6, len(HIGH_POOL)) + 1):
        for _ in range(40):
            highs = random.sample(HIGH_POOL, count)
            total = low_sum + sum(highs)
            if total < TARGET or total > TARGET_MAX:
                continue
            arranged = arrange(lows + highs, set(lows))
            if arranged is None:
                continue
            return arranged, set(lows), total
    return None


def generate(num_candidates=700):
    best = None
    best_key = None
    for _ in range(num_candidates):
        c = build_candidate()
        if c is None:
            continue
        arr, low_set, total = c
        sp = spread_score(arr)
        closeness = -(total - TARGET) / 1000.0   # 500.000'e yakinlik
        count_pen = -len(arr) * 0.8              # az adet hafif tercih
        key = (round(sp + closeness + count_pen, 3),)
        if best_key is None or key > best_key:
            best_key = key
            best = (arr, low_set, total)
    return best


def level_positions(arr):
    """Her seviye icin (sira, sayi) don."""
    running = 0
    res = {lvl: None for lvl in LEVELS}
    for idx, v in enumerate(arr, start=1):
        running += v
        for lvl in LEVELS:
            if res[lvl] is None and running >= lvl:
                res[lvl] = (idx, v)
    return res


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
    if total < TARGET:
        errs.append(f"toplam < {TARGET}")
    for i in range(1, len(arr)):
        if hundred_bucket(arr[i]) == hundred_bucket(arr[i - 1]):
            errs.append("ayni yuzluk dilim ardisik")
            break
    return errs


def format_output(arr, low_set, total):
    lows = sorted(x for x in arr if x in low_set)
    lv = level_positions(arr)
    # kademe gecisinin gerceklestigi 1-indeksli siralar (listede kalin olacak)
    bold_idx = set(pos[0] for pos in lv.values() if pos is not None)

    tr = timezone(timedelta(hours=3))
    tarih = datetime.now(tr).strftime("%d.%m.%Y")
    total_str = f"{total:,}".replace(",", ".")

    # Sayilari 5'er 5'er; kademe gecis sayilari kalin.
    row = []
    number_lines = []
    for i, v in enumerate(arr, start=1):
        cell = f"<b>{v}</b>" if i in bold_idx else str(v)
        row.append(cell)
        if len(row) == 5:
            number_lines.append(", ".join(row))
            row = []
    if row:
        number_lines.append(", ".join(row))

    def lvl_line(lvl):
        p = lv[lvl]
        lvl_str = f"{lvl:,}".replace(",", ".")
        if p is None:
            return f"  {lvl_str} -> asilmadi"
        idx, val = p
        return f"  {lvl_str} -> {idx}. sayida: <b>{val}</b>"

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
        lvl_line(300000),
        lvl_line(400000),
        lvl_line(500000),
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
    best = None
    for _ in range(5):  # gecerli sonuc gelene kadar yeniden uret
        best = generate()
        if best is None:
            continue
        arr, low_set, total = best
        if not validate(arr, low_set, total):
            return format_output(arr, low_set, total)
    return "Uygun kombinasyon uretilemedi, tekrar denenecek."


if __name__ == "__main__":
    message = build_message()
    print(message)
    send_telegram(message)
    print("\n[OK] Telegram'a gonderildi.")
