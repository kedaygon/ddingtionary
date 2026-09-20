import itertools
import json
import os
import re

import importer

DMG_VERSION = "10"
DAMAGE_PATH = "BinData/damage/damage.json"
SKILL_PATH = "BinData/skill/skill.json"
TYPE_CATS = {0: "일반 공격", 1: "강공격", 2: "공명 해방", 3: "변주 스킬", 4: "공명 스킬",
             5: "에코 어빌리티", 7: "반주 스킬", 12: "조화 파동", 14: "해킹"}
RE_TERM = re.compile(r"^([\d.]+)%(?:\*(\d+))?$")
_cache = {}
COOP_IDS = set()


def missing(version_dir):
    return [p for p in (DAMAGE_PATH, SKILL_PATH)
            if not os.path.isfile(importer.source_path(version_dir, p))]


def fetch(version_dir, progress=None):
    version = os.path.basename(os.path.normpath(version_dir))
    for rel in missing(version_dir):
        label = rel.rsplit("/", 1)[-1]
        if progress:
            progress("fetch", label)
        importer._download("%s/%s/%s" % (importer.RAW_BASE, version, rel),
                           importer.source_path(version_dir, rel), progress=progress, label=label)
    return not missing(version_dir)


def terms(raw):
    out = []
    for part in (raw or "").replace(" ", "").split("+"):
        m = RE_TERM.match(part)
        if not m:
            return None
        v = int(round(float(m.group(1)) * 100))
        out.append((v, int(m.group(2) or 1)))
    return out or None


def _close(a, b):
    return abs(a - b) <= 3


def _units(vec, cands):
    hits = [(d,) for d, rv in cands if all(_close(rv[i], vec[i]) for i in range(len(vec)))]
    if hits:
        return hits
    pairs = []
    for (d1, r1), (d2, r2) in itertools.combinations(cands, 2):
        if all(_close(r1[i] + r2[i], vec[i]) for i in range(len(vec))):
            pairs.append((d1, d2))
    return pairs


def _prefix_len(a, b):
    a, b = str(a), str(b)
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return n


def _coherence(ids):
    if len(ids) < 2:
        return 0
    return min(_prefix_len(a, b) for a, b in itertools.combinations(ids, 2))


def _weights(combo, found, rv, types, last):
    w = {}
    coop = 0
    for unit, (vec, cnt) in zip(combo, found):
        for d in unit:
            val = (vec[-1] if len(unit) == 1 else rv[d][last]) * cnt
            w[types[d]] = w.get(types[d], 0) + val
            if d in COOP_IDS:
                coop += val
    total = sum(w.values()) or 1
    out = {str(t): round(v / total, 4) for t, v in sorted(w.items())}
    if coop:
        out["coop"] = round(coop / total, 4)
    return out


def classify_scaling(levels, cands, types):
    per = [terms(levels[k]) for k in sorted(levels)]
    if not per or any(p is None for p in per) or len({len(p) for p in per}) != 1:
        return None
    rv = dict(cands)
    last = len(per) - 1
    found, units = [], []
    for j in range(len(per[0])):
        vec = [p[j][0] for p in per]
        u = _units(vec, cands)
        if not u:
            return None
        found.append((vec, per[0][j][1]))
        units.append(u)
    if all(len({tuple(types[d] for d in unit) for unit in u}) == 1 for u in units):
        ids = [d for u in units if len(u) == 1 for d in u[0]]
        every = [d for u in units for unit in u for d in unit]
        return {"w": _weights(tuple(u[0] for u in units), found, rv, types, last), "ids": ids,
                "all": every}
    total = 1
    for u in units:
        total *= len(u)
    if total > 5000:
        return None
    combos = list(itertools.product(*units))
    score = {c: _coherence([d for unit in c for d in unit]) for c in combos}
    top = max(score.values())
    combos = [c for c in combos if score[c] == top]
    return {"combos": [(_weights(c, found, rv, types, last), [d for unit in c for d in unit])
                       for c in combos]}


STOP = {"피해", "공격", "일반", "강공격", "공중", "회피", "반격", "스킬", "공명", "해방", "변주"}


def _tokens(name):
    return {w for w in re.split(r"[\s·,()]+", name or "")
            if len(w) >= 2 and w not in STOP and not re.match(r"^\d+단$", w)}


def _finish(res, name, siblings, claimed=()):
    if "w" in res:
        return res["w"]
    combos = res["combos"]
    if res.get("wide"):
        return {"options": list({json.dumps(w, sort_keys=True): w for w, _i in combos}.values())}
    free = [c for c in combos if not set(c[1]) & set(claimed)]
    if free and len(free) < len(combos) and len({json.dumps(w, sort_keys=True) for w, _i in free}) == 1:
        combos = free
    toks = _tokens(name)
    df = {}
    for n, _ids in siblings:
        for t in _tokens(n):
            df[t] = df.get(t, 0) + 1
    sims = [(sum(1.0 / df[t] for t in toks & _tokens(n)), ids) for n, ids in siblings]
    best = max([x for x, _i in sims] or [0])
    anchors = [d for x, ids in sims if best and x == best for d in ids]
    if anchors:
        score = [min(max(_prefix_len(d, a) for a in anchors) for d in ids) for _w, ids in combos]
        top = max(score)
        combos = [c for c, sc in zip(combos, score) if sc == top]
    options = []
    for w, _ids in combos:
        if w not in options:
            options.append(w)
    if len(options) == 1:
        return options[0]
    return {"options": options}


def build(con, version_dir):
    with open(importer.source_path(version_dir, DAMAGE_PATH), "r", encoding="utf-8") as f:
        dmg = {r["Id"]: r for r in json.load(f)}
    COOP_IDS.clear()
    COOP_IDS.update(d for d, r in dmg.items() if 0 in (r.get("SubType") or []))
    with open(importer.source_path(version_dir, SKILL_PATH), "r", encoding="utf-8") as f:
        skills = {s["Id"]: s for s in json.load(f)}
    rows = con.execute("SELECT id, character_id, skill_level_group_id FROM skills").fetchall()
    by_char = {}
    for sid, cid, _g in rows:
        by_char.setdefault(cid, []).append(sid)
    out = []
    pending = []
    for sid, cid, grp in rows:
        own = [d for d in (skills.get(sid) or {}).get("DamageList") or [] if d in dmg]
        other = [d for s2 in by_char[cid] if s2 != sid
                 for d in (skills.get(s2) or {}).get("DamageList") or [] if d in dmg]
        got_all = []
        for scid, name in con.execute(
                "SELECT id, attribute_name FROM skill_scalings WHERE skill_level_group_id=?", (grp,)):
            levels = {lv: raw for lv, raw in con.execute(
                "SELECT level, raw FROM scaling_levels WHERE scaling_id=? AND level<=10", (scid,))}
            if not levels:
                continue
            res = None
            for wide, pool in ((False, own), (True, own + other)):
                if res and "w" in res:
                    break
                ids = list(dict.fromkeys(pool))
                cands = [(d, dmg[d]["RateLv"][:len(levels)]) for d in ids
                         if dmg[d].get("RateLv") and dmg[d]["RateLv"][0] > 0
                         and len(dmg[d]["RateLv"]) >= len(levels)]
                types = {d: dmg[d]["Type"] for d in ids}
                got = classify_scaling(levels, cands, types)
                if got and (not res or "w" in got):
                    res = dict(got, wide=wide)
            if res:
                got_all.append((scid, name, res))
        pending.append((sid, cid, got_all))
    claimed = {}
    for sid, cid, got_all in pending:
        for _s, _n, r in got_all:
            if "w" in r:
                claimed.setdefault(cid, {}).setdefault(sid, set()).update(r["all"])
    for sid, cid, got_all in pending:
        siblings = [(n, r["ids"]) for _s, n, r in got_all if "w" in r]
        other = set()
        for s2, ids in claimed.get(cid, {}).items():
            if s2 != sid:
                other |= ids
        for scid, name, res in got_all:
            out.append((scid, json.dumps(_finish(res, name, siblings, other))))
    return out


def write(con, rows):
    con.execute("CREATE TABLE IF NOT EXISTS scaling_types (scaling_id INTEGER PRIMARY KEY, types TEXT)")
    con.execute("DELETE FROM scaling_types")
    con.executemany("INSERT INTO scaling_types (scaling_id, types) VALUES (?, ?)", rows)
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('dmg_version', ?)", (DMG_VERSION,))
    con.commit()
    _cache.pop(id(con), None)


def ready(con):
    try:
        row = con.execute("SELECT value FROM meta WHERE key='dmg_version'").fetchone()
        return bool(row) and row[0] == DMG_VERSION
    except Exception:
        return False


def backfill(con, version_dir, progress=None):
    if missing(version_dir) and not fetch(version_dir, progress):
        return False
    write(con, build(con, version_dir))
    return True


def lookup(con):
    key = id(con)
    if key not in _cache:
        try:
            _cache[key] = {sid: json.loads(t)
                           for sid, t in con.execute("SELECT scaling_id, types FROM scaling_types")}
        except Exception:
            _cache[key] = {}
    return _cache[key]


def clear():
    _cache.clear()
