import re

import rules

COUNTED = ("atk", "dmg_bonus", "dmg_boost", "damage_taken", "res_shred", "def_ignore")
PARTY_HOLDERS = ("party", "on_field")
RE_MODE = re.compile(r"공명 모드\s*·\s*([^\s,에]+)")
RE_CRIT = re.compile(r"크리티컬(?:\s*피해)?(?:가|이|를|을)?\s*[\d.]+%")

_cache = {}


def chains(con, cid):
    try:
        return con.execute(
            "SELECT id, idx, name, describe_text FROM chains "
            "WHERE character_id=? ORDER BY idx", (cid,)).fetchall()
    except Exception:
        return []


def party_buffs(con, cid, level, mode=None):
    key = (id(con), cid, level, mode)
    if key in _cache:
        return _cache[key]
    rows = [r for r in chains(con, cid) if (r[1] or 0) <= (level or 0)]
    idx_of = {r[0]: r[1] for r in rows}
    name_of = {r[0]: r[2] for r in rows}
    found, _ = rules.extract([(r[0], 100, r[2], r[3]) for r in rows])
    out = []
    seen = set()
    for f in found:
        if f["holder"] not in PARTY_HOLDERS:
            continue
        line = f["source_line"]
        m = RE_MODE.search(line)
        if m and mode and not mode.startswith(m.group(1)) and not m.group(1).startswith(mode):
            continue
        value = f.get("value") or 0.0
        if value < 1.0:
            continue
        stat = f["stat"]
        near = line[max(0, (f.get("pos") or 0) - 10):(f.get("pos") or 0)]
        crit = bool(RE_CRIT.search(near)) and stat == "dmg_boost"
        k = (f["skill_id"], stat, f.get("scope_skill"), f.get("scope_element"), value)
        if k in seen:
            continue
        seen.add(k)
        out.append({
            "idx": idx_of.get(f["skill_id"]),
            "chain_name": name_of.get(f["skill_id"]),
            "stat": "crit_dmg" if crit else stat,
            "counted": (stat in COUNTED) and not crit,
            "scope": f.get("scope_skill") or "전체",
            "element": f.get("scope_element"),
            "value": value,
            "duration": f.get("duration"),
            "line": line,
        })
    _cache[key] = out
    return out
