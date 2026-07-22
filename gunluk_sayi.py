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
# Her gun toplam hedefi bu aralikta RASTGELE secilir -> her gun farkli
# toplam ve farkli sayi adedi -> cikti tamamen rastgele gorunur.
DAILY_MIN = 455000                   # gunluk rastgele hedef alt (450k'yi rahat gecer)
DAILY_MAX = 545000                   # gunluk rastgele hedef ust (550k'nin altinda)
HARD_MIN = 450000                    # kesin alt sinir (altina asla dusmez)
HARD_MAX = 550000                    # kesin ust sinir (ustune asla cikmaz)
LEVELS = [300000, 400000, 450000]    # kademe gecis seviyeleri

LOW_POOL = list(range(LOW_MIN, LOW_MAX + 1, STEP))
HIGH_POOL = list(range(HIGH_MIN, HIGH_MAX + 1, STEP))

# Gecmis (arsiv + tekrar onleme) dosyasi. Depo kokunde tutulur.
HISTORY_FILE = os.environ.get("HISTORY_FILE", "gecmis.jsonl")


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


HIGH_AVG = sum(HIGH_POOL) / len(HIGH_POOL)   # ~11405


def build_candidate(target):
    """Toplami 'target'a yakin (450k-550k icinde) bir kombinasyon uret."""
    lows = random.sample(LOW_POOL, 2)
    low_sum = sum(lows)
    need = target - low_sum
    est = max(1, round(need / HIGH_AVG))
    # hedefe gore degisen sayi adedi -> her gun farkli adet
    for count in range(max(1, est - 2), min(est + 4, len(HIGH_POOL)) + 1):
        for _ in range(40):
            highs = random.sample(HIGH_POOL, count)
            total = low_sum + sum(highs)
            if not (HARD_MIN <= total <= HARD_MAX):
                continue
            if abs(total - target) > 7000:
                continue
            arranged = arrange(lows + highs, set(lows))
            if arranged is None:
                continue
            return arranged, set(lows), total
    return None


def generate(target, num_candidates=300):
    """Verilen hedefe yakin, en dengeli/rastgele gorunumlu adayi sec."""
    best = None
    best_key = None
    for _ in range(num_candidates):
        c = build_candidate(target)
        if c is None:
            continue
        arr, low_set, total = c
        sp = spread_score(arr)
        closeness = -abs(total - target) / 1000.0   # gunun hedefine yakinlik
        key = (round(sp + closeness, 3),)
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
    if total < HARD_MIN:
        errs.append(f"toplam < {HARD_MIN}")
    if total > HARD_MAX:
        errs.append(f"toplam > {HARD_MAX}")
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
        *[lvl_line(lvl) for lvl in LEVELS],
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


def signature(arr):
    """Ayni sayi kumesi ayni imzayi verir (sira onemsiz)."""
    return ",".join(str(x) for x in sorted(arr))


def load_history():
    """Gecmis imzalarini oku. Dosya yok/bozuksa bos don (sistemi bozmaz)."""
    sigs = set()
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        sigs.add(signature(rec["sayilar"]))
                    except Exception:
                        continue
    except Exception:
        pass
    return sigs


def append_history(arr, total):
    """Gunun sonucunu arsive ekle. Hata olursa sessizce gec (mesaj gitti)."""
    try:
        tr = timezone(timedelta(hours=3))
        rec = {
            "tarih": datetime.now(tr).strftime("%Y-%m-%d"),
            "toplam": total,
            "adet": len(arr),
            "sayilar": list(arr),
        }
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def produce(history_sigs, max_tries=50):
    """
    Gecerli VE gecmiste olmayan bir kombinasyon uret.
    Her denemede gunun hedefi 455k-545k arasinda RASTGELE secilir ->
    her gun farkli toplam ve farkli sayi adedi (tamamen rastgele gorunum).
    Benzersiz bulunamazsa son gecerli sonucu don (sistem asla bos kalmaz).
    """
    fallback = None
    for _ in range(max_tries):
        target = random.randint(DAILY_MIN, DAILY_MAX)
        best = generate(target)
        if best is None:
            continue
        arr, low_set, total = best
        if validate(arr, low_set, total):
            continue
        fallback = (arr, low_set, total)
        if signature(arr) not in history_sigs:
            return (arr, low_set, total), True
    return fallback, False


def build_message():
    """Test/onizleme icin: gecmis olmadan tek mesaj uretir."""
    res, _ = produce(set())
    if res is None:
        return "Uygun kombinasyon uretilemedi."
    arr, low_set, total = res
    return format_output(arr, low_set, total)


if __name__ == "__main__":
    history_sigs = load_history()
    res, unique = produce(history_sigs)
    if res is None:
        message = "Uygun kombinasyon uretilemedi, yarin tekrar denenecek."
        print(message)
        send_telegram(message)
    else:
        arr, low_set, total = res
        message = format_output(arr, low_set, total)
        print(message)
        if not unique:
            print("[UYARI] Benzersiz kombinasyon bulunamadi, gecerli sonuc gonderiliyor.")
        send_telegram(message)
        if append_history(arr, total):
            print("[OK] Arsive eklendi:", HISTORY_FILE)
    print("[OK] Telegram'a gonderildi.")
