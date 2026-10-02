# Local city gazetteer: GeoNames cities15000 (every city above ~15 000 people, 34k rows) with its
# coordinates and its timezone, kept under geo/. Searching it is instant and needs no network, and it
# is typo-tolerant ("chaing mai" -> Chiang Mai), which the Open-Meteo geocoder is not. Open-Meteo stays
# as the fallback for the small places the dump does not carry.
#
#   python geolocal.py --build      # once, after geo/cities15000.txt is refreshed
#   python geolocal.py Алматы "chaing mai"
#
# Data: https://download.geonames.org/export/dump/ (CC BY 4.0); country names from CLDR.
import os
import re
import sys
import json
import pickle
import difflib
import unicodedata

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geo")
CITIES = os.path.join(DIR, "cities15000.txt")
ADMIN1 = os.path.join(DIR, "admin1.txt")
COUNTRIES = os.path.join(DIR, "countries.json")
INDEX = os.path.join(DIR, "gazetteer.pkl")

CYRILLIC = re.compile(r"[А-Яа-яЁёІіЇїЄєҐґ]")
_gazetteer = None


def normalize(s: str) -> str:
    """'Chiang Mai' -> 'chiangmai', 'Алматы' -> 'алматы': case, accents and punctuation are not part of a
    name, and neither is the space in it, so the same city is found by any spelling of it."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    if CYRILLIC.search(s):
        s = s.replace("ё", "е").replace("ї", "и").replace("і", "и").replace("ґ", "г").replace("є", "е")
    return re.sub(r"[^0-9a-zа-я]", "", s)


def build() -> dict:
    countries = {}
    if os.path.exists(COUNTRIES):
        countries = json.load(open(COUNTRIES, encoding="utf-8"))
    admin1 = {}
    if os.path.exists(ADMIN1):
        for line in open(ADMIN1, encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) >= 2:
                admin1[p[0]] = p[1]
    cities, index = [], {}
    with open(CITIES, encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 18:
                continue
            names, seen, cyr = [], set(), []
            for n in [p[2], p[1]] + p[3].split(","):
                k = normalize(n)
                if not k or k in seen or len(k) > 40:
                    continue
                seen.add(k)
                names.append(k)
                # The Cyrillic names of their own, with the key that finds them: a Russian label must be the
                # name the person typed (Алматы), not the first Cyrillic name in the row (Алма-Ата, Мæскуы —
                # the dump lists every language that writes in Cyrillic).
                if CYRILLIC.search(n) and len(cyr) < 8:
                    cyr.append((k, n))
            if not names:
                continue
            cities.append({
                "name": p[1], "ascii": p[2], "cyr": cyr,
                "lat": float(p[4]), "lon": float(p[5]),
                "cc": p[8], "adm1": admin1.get(p[8] + "." + p[10], ""),
                "pop": int(p[14] or 0), "tz": p[17] or "UTC",
            })
            for k in names:
                index.setdefault(k, []).append(len(cities) - 1)
    data = {"cities": cities, "index": index, "countries": countries}
    tmp = INDEX + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(data, f, protocol=4)
    os.replace(tmp, INDEX)
    return data


def load() -> dict:
    global _gazetteer
    if _gazetteer is None:
        try:
            with open(INDEX, "rb") as f:
                _gazetteer = pickle.load(f)
        except Exception:
            _gazetteer = {"cities": [], "index": {}, "countries": {}}
    return _gazetteer


def unload():
    """Give the ~90 MB of city names back: the mode is switchable, and an online bot has no use for them."""
    global _gazetteer
    _gazetteer = None


def loaded() -> bool:
    return _gazetteer is not None


def _city_name(city: dict, key: str, ru: bool) -> str:
    """The name to print: the Cyrillic one the query matched (or the closest to it), the row's own name for a
    Latin query. The dump lists every language written in Cyrillic, and picking one of those by similarity to
    a Latin name is how 'New York' came out as the Serbian 'Њу Јорк'."""
    if ru and CYRILLIC.search(key):
        alts = city["cyr"]
        exact = next((n for k, n in alts if k == key), "")
        if exact:
            return exact
        if alts:
            return max(alts, key=lambda p: difflib.SequenceMatcher(None, key, p[0]).ratio())[1]
    return city["name"]


def _label(city: dict, key: str, countries: dict, ru: bool) -> str:
    """'Алматы, Казахстан' / 'Chiang Mai, Thailand' — the shape the Open-Meteo labels have, repeats dropped.
    The admin region is left out for Russian: the dump carries it in English only."""
    c = countries.get(city["cc"], {})
    parts = [_city_name(city, key, ru)]
    if not ru and city["adm1"]:
        parts.append(city["adm1"])
    parts.append(c.get("ru" if ru else "en") or c.get("en") or city["cc"])
    return ", ".join(dict.fromkeys(x for x in parts if x))


def search(name: str, lang: str = "en", limit: int = 3) -> list:
    """Cities for the typed text, best match first, or [] when the dump does not know it."""
    g = load()
    cities, index, countries = g["cities"], g["index"], g["countries"]
    if not cities:
        return []
    ru = lang == "ru"
    key = normalize(name)
    if len(key) < 2:
        return []
    hits = [(1.0, i, key) for i in index[key]] if key in index else []
    if not hits and len(key) >= 3:  # mid-word: the biggest cities whose name starts like this
        hits = [(0.9, i, k) for k, v in index.items() if k.startswith(key) for i in v]
    if not hits and len(key) >= 4:  # a typo: closest names of the same length, then by how close they are
        near = [k for k in index if k[0] == key[0] and abs(len(k) - len(key)) <= 2]
        for k in difflib.get_close_matches(key, near, n=8, cutoff=0.78):
            ratio = difflib.SequenceMatcher(None, key, k).ratio()
            hits += [(ratio, i, k) for i in index[k]]
    best = {}
    for score, i, k in hits:
        if i not in best or score > best[i][0]:
            best[i] = (score, k)
    out, seen = [], set()
    for i, (score, k) in sorted(best.items(), key=lambda kv: (-round(kv[1][0], 2), -cities[kv[0]]["pop"])):
        c = cities[i]
        if (c["lat"], c["lon"]) in seen:  # one city under several names, once
            continue
        seen.add((c["lat"], c["lon"]))
        out.append({"label": _label(c, k, countries, ru), "lat": c["lat"], "lon": c["lon"], "tz": c["tz"]})
        if len(out) >= limit:
            break
    return out


if __name__ == "__main__":
    if "--build" in sys.argv:
        d = build()
        print(f"gazetteer: {len(d['cities'])} cities, {len(d['index'])} names -> {INDEX}")
    else:
        g = load()
        print(f"{len(g['cities'])} cities")
        for q in sys.argv[1:]:
            for lang in ("ru", "en"):
                print(f"  {q!r} [{lang}] -> {search(q, lang)}")
