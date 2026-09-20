import re

import classify
import cycle
import skilldata

LEVEL_MIN = 1
LEVEL_MAX = 10

_UTILITY = ("증가(", "증가량", "증폭", "치료", "실드", "회복", "효율",
            "감소량", "스태미나", "피해 감소", "팬텀 HP", "증가하는 공격", "배율 상승")


def damage_profile(con, cid, level=LEVEL_MAX, mode=None):
    char = cycle.load_character(con, cid, level, mode)
    buckets = {}
    total = 0.0
    for e in char["entries"]:
        buckets.setdefault(e["category"], []).append(e)
        total += e["pct"]
    rows = []
    for cat, items in buckets.items():
        s = sum(i["pct"] for i in items)
        rows.append({
            "category": cat,
            "total": s,
            "share": (s / total * 100.0) if total else 0.0,
            "count": len(items),
            "items": sorted(items, key=lambda x: -x["pct"]),
        })
    rows.sort(key=lambda r: -r["total"])
    coop = sum(cycle.coop_pct(e) for e in char["entries"])
    return {"name": char["name"], "total": total, "rows": rows, "char": char,
            "coop_share": (coop / total * 100.0) if total else 0.0,
            "mode": char.get("mode"), "modes": char.get("modes") or []}


REASON_TEXT = {
    "게임 데이터": "게임 피해 데이터",
    "게임 데이터+원문": "게임 피해 데이터 후보 중 원문 판정",
    "게임 데이터(소거)": "게임 피해 데이터 · 같은 배율 항목 소거",
    "원문 '해당 피해는'": "원문 '해당 피해는 …로 적용'",
    "원문": "원문에 판정 명시",
    "제목": "원문 소제목",
    "대체": "원문 '…로 대체'",
}


def reclassified(con, cid, level=LEVEL_MAX, mode=None):
    char = cycle.load_character(con, cid, level, mode)
    out = []
    for e in char["entries"]:
        why = e.get("reason") or ""
        if why not in REASON_TEXT:
            continue
        base = e.get("skill_default")
        if e["category"] == base:
            continue
        if classify.keyword_cat(classify.name_of(classify.base_of(e["attr"]))) == e["category"]:
            continue
        src = base if base and base != cycle.UNKNOWN else \
            skilldata.TYPE_NAMES.get(e.get("skill_type"), "기타")
        out.append({
            "attr": e["attr"],
            "skill": e["skill_name"],
            "from": src,
            "to": e["category"],
            "pct": e["pct"],
            "partial": e.get("share_of_attr", 1.0) < 0.999,
            "reason": REASON_TEXT[why],
        })
    return out


def unclear_entries(con, cid, level=LEVEL_MAX, mode=None):
    char = cycle.load_character(con, cid, level, mode)
    return [e for e in char["entries"] if e["category"] == cycle.UNCLEAR]


def unknown_entries(con, cid, level=LEVEL_MAX, mode=None):
    char = cycle.load_character(con, cid, level, mode)
    return [e for e in char["entries"] if e["category"] == cycle.UNKNOWN]


def level_priority(con, cid, mode=None):
    rows = con.execute(
        "SELECT s.name, s.skill_type, sc.attribute_name, a.total_pct, b.total_pct "
        "FROM skill_scalings sc "
        "JOIN scaling_levels a ON a.scaling_id=sc.id AND a.level=? "
        "JOIN scaling_levels b ON b.scaling_id=sc.id AND b.level=? "
        "JOIN skills s ON s.skill_level_group_id=sc.skill_level_group_id "
        "WHERE s.character_id=?", (LEVEL_MIN, LEVEL_MAX, cid)).fetchall()

    char = cycle.load_character(con, cid, LEVEL_MAX, mode)
    cat_of = {}
    for e in char["entries"]:
        cat_of.setdefault((e["skill_name"], e["attr"]), []).append(
            (e["category"], e.get("share_of_attr", 1.0)))

    per_skill = {}
    for sname, stype, attr, p1, p10 in rows:
        if not p1 or not p10 or p10 <= p1:
            continue
        attr = re.sub(r"\s+", " ", (attr or "")).strip()
        if any(k in attr for k in _UTILITY):
            continue
        key = (stype, sname)
        d = per_skill.setdefault(
            key, {"gain": 0.0, "base": 0.0, "top": None, "cats": {}})
        gain = p10 - p1
        d["gain"] += gain
        d["base"] += p1
        for cat, share in cat_of.get((sname, attr), []):
            d["cats"][cat] = d["cats"].get(cat, 0.0) + gain * share
        if d["top"] is None or gain > d["top"][1]:
            d["top"] = (attr, gain)

    out = []
    for (stype, sname), d in per_skill.items():
        out.append({
            "skill": sname,
            "type": stype,
            "type_name": skilldata.TYPE_NAMES.get(stype, "기타"),
            "gain": d["gain"],
            "base": d["base"],
            "ratio": (d["gain"] / d["base"]) if d["base"] else 0.0,
            "top_attr": d["top"][0] if d["top"] else "",
            "cats": sorted(d["cats"].items(), key=lambda x: -x[1]),
        })
    out.sort(key=lambda x: -x["gain"])
    return out


def search(con, query, limit=200, scope="all"):
    q = (query or "").strip()
    if len(q) < 2:
        return []
    like = "%" + q + "%"
    sources = []
    if scope in ("all", "skills"):
        sources += con.execute(
            "SELECT c.id, c.name, s.id, s.skill_type, s.name, s.describe_text, NULL "
            "FROM skills s JOIN characters c ON c.id=s.character_id "
            "WHERE c.is_alias=0 AND s.describe_text LIKE ? "
            "ORDER BY c.name, s.skill_type", (like,)).fetchall()
    if scope in ("all", "chains"):
        try:
            sources += con.execute(
                "SELECT c.id, c.name, -h.id, ?, h.name, h.describe_text, h.idx "
                "FROM chains h JOIN characters c ON c.id=h.character_id "
                "WHERE c.is_alias=0 AND h.describe_text LIKE ? "
                "ORDER BY c.name, h.idx", (skilldata.CHAIN_TYPE, like)).fetchall()
        except Exception:
            pass
    out = []
    for cid, cname, sid, stype, sname, text, idx in sources:
        tname = ("공명 체인 %d" % idx) if idx is not None else \
            skilldata.TYPE_NAMES.get(stype, "기타")
        for raw in (text or "").split("\n"):
            line = raw.strip().lstrip("·-• ").strip()
            if q in line:
                out.append({
                    "character_id": cid,
                    "character": cname,
                    "skill_id": sid,
                    "skill": sname,
                    "type_name": tname,
                    "chain": idx,
                    "line": line,
                })
                if len(out) >= limit:
                    return out
    return out


def term_search(con, query, limit=60):
    q = (query or "").strip()
    if len(q) < 2:
        return []
    like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    rows = con.execute(
        "SELECT id, title, desc_text FROM terms "
        "WHERE title LIKE ? ESCAPE '\\' OR desc_text LIKE ? ESCAPE '\\' "
        "ORDER BY title LIMIT ?",
        (like, like, limit)).fetchall()
    return [(i, t, ui_clean(d)) for i, t, d in rows]


def ui_clean(text):
    return re.sub(r"\{\d+\}", "N", text or "")


