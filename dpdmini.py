"""Short meanings from the DPD mini dictionary (dpd_i2h / dpd_ebts, the files the site's dictionary plugin uses).

The source files are 6-10 MB JS objects: parsing them in every bot process costs ~150 MB of RAM, so they are
turned once into a small SQLite file and the bot only queries it.
"""
import html
import json
import os
import re
import sqlite3
import threading

SRC = "/var/www/dg-node-prod/public/overrides/js/standalone-dpd/"
FILES = {"i2h": "dpd_i2h.js", "en": "dpd_ebts.js", "ru": "ru/dpd_ebts.js"}
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dpd_mini.sqlite")
_lock = threading.Lock()
_conn = None


def _load(name):
    s = open(SRC + FILES[name], encoding="utf8").read()
    return json.loads(s[s.index("{"):s.rindex("}") + 1])


def _stale():
    if not os.path.exists(DB):
        return True
    built = os.path.getmtime(DB)
    return any(os.path.getmtime(SRC + f) > built for f in FILES.values())


def _build():
    tmp = DB + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    con.execute("create table i2h(form text primary key, heads text)")
    con.execute("create table ebts(head text, lang text, txt text, primary key(head, lang))")
    for form, heads in _load("i2h").items():
        if form:
            con.execute("insert into i2h values(?,?)", (form, json.dumps(heads, ensure_ascii=False)))
    for lang in ("en", "ru"):
        for head, txt in _load(lang).items():
            con.execute("insert into ebts values(?,?,?)", (head, lang, txt))
    con.commit()
    con.close()
    os.replace(tmp, DB)


def _db():
    global _conn
    with _lock:
        if _conn is None:
            if _stale():
                _build()
            _conn = sqlite3.connect(DB, check_same_thread=False)
        return _conn


def _plain(txt):
    # "adj. <b>smooth; tender</b> [na + kakkasa]" -> "adj. smooth; tender"
    txt = re.sub(r"<[^>]+>", "", txt)
    txt = re.sub(r"\s*\[[^\]]*\]\s*$", "", txt)
    txt = html.escape(txt.strip())
    # the part of speech is the leading "adj." / "прил." token: italic, no list of parts of speech needed
    return re.sub(r"^([^\W\d_]+(?:\.[^\W\d_]+)*\.)(\s|$)", r"<i>\1</i>\2", txt)


def meaning(word, lang="en", max_heads=4):
    """HTML text with the short meaning of `word` (an inflected form or a headword), or "" when it is not in the dictionary."""
    word = (word or "").strip().lower()
    if not word or " " in word:
        return ""
    con = _db()
    forms = [word, word.replace("ṁ", "ṃ")]
    heads = []
    for f in forms:
        row = con.execute("select heads from i2h where form=?", (f,)).fetchone()
        if row:
            heads = json.loads(row[0])
            break
        if con.execute("select 1 from ebts where head=? limit 1", (f,)).fetchone():
            heads = [f]
            break
    lines, seen, more = [], set(), False
    for h in heads:
        base = re.sub(r" \d+(\.\d+)?$", "", h)
        if base in seen:
            continue
        row = None
        for l in ([lang, "en"] if lang != "en" else ["en"]):
            row = con.execute("select txt from ebts where head=? and lang=?", (h, l)).fetchone()
            if row:
                break
        if not row:
            continue
        if len(lines) >= max_heads:
            more = True  # not the whole list: the caller sees the "…" line
            break
        seen.add(base)
        lines.append((base, _plain(row[0])))
    if not lines:
        return ""
    # a single meaning of the very word that was typed needs no bold headword; otherwise every line has one
    if len(lines) == 1 and not more and lines[0][0].lower() in (word, word.replace("ṁ", "ṃ")):
        return lines[0][1]
    out = [f"<b>{html.escape(b)}</b> — {t}" for b, t in lines]
    return "\n".join(out + (["…"] if more else []))


if __name__ == "__main__":
    import sys
    print(meaning(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "en") or "-")
