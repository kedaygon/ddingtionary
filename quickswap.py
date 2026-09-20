import re

import modes
import rules

RE_TAG = re.compile(r"「([^」]{2,24})」")

CONCERTO_FULL = 100.0
NORMAL_MARKERS = ("일반 공격", "공중 공격", "평타")

_TAIL = re.compile(r"\s+")


def _clean(s):
    return _TAIL.sub(" ", (s or "")).strip()


def concerto_profile(con, cid, level=10):
    rows = con.execute(
        "SELECT s.skill_type, s.name, sc.attribute_name, sl.total_flat "
        "FROM skill_scalings sc "
        "JOIN scaling_levels sl ON sl.scaling_id=sc.id AND sl.level=? "
        "JOIN skills s ON s.skill_level_group_id=sc.skill_level_group_id "
        "WHERE s.character_id=? AND sc.attribute_name LIKE '%협주 에너지%'",
        (level, cid)).fetchall()

    skill_gain = 0.0
    normal_gain = 0.0
    sources = []
    for stype, sname, attr, flat in rows:
        attr = _clean(attr)
        value = flat or 0.0
        if not value:
            continue
        is_normal = any(m in attr for m in NORMAL_MARKERS) or (
            stype == 1 and not any(
                k in attr for k in ("공명", "변주", "반주", "강공격", "회피")))
        if is_normal:
            normal_gain += value
        else:
            skill_gain += value
        sources.append({
            "skill": sname,
            "attr": attr,
            "value": value,
            "normal": is_normal,
        })
    return {
        "skill_gain": skill_gain,
        "normal_gain": normal_gain,
        "sources": sources,
    }


def burst_profile(con, cid, level=10):
    rows = con.execute(
        "SELECT sc.attribute_name, sl.total_pct, sl.total_flat "
        "FROM skill_scalings sc "
        "JOIN scaling_levels sl ON sl.scaling_id=sc.id AND sl.level=? "
        "JOIN skills s ON s.skill_level_group_id=sc.skill_level_group_id "
        "WHERE s.character_id=? AND s.skill_type=3", (level, cid)).fetchall()
    dmg = cost = cd = 0.0
    for attr, pct, flat in rows:
        attr = _clean(attr)
        if "공명 에너지 소모" in attr:
            cost = max(cost, flat or 0.0)
        elif "쿨타임" in attr:
            cd = max(cd, flat or 0.0)
        elif "협주" not in attr and pct:
            dmg = max(dmg, pct)
    return {"damage": dmg, "cost": cost, "cooldown": cd,
            "efficiency": (dmg / cost) if cost else 0.0}


RE_PER_ANY = re.compile(r"\d+(?:\.\d+)?\s*%?\s*당")
RE_OUTRO_CAP = re.compile(r"^(?:(?!다\.).){0,24}?최대치는\s*(\d+(?:\.\d+)?)\s*%")
RE_MODE_CLAUSE = re.compile(r"공명\s*모드\s*·\s*[^,，]*?(?:있을|일)\s*(?:시|경우)\s*[,，]")
RE_OUTRO_COND = re.compile(r"상태\s*:|(?:시|후|경우|때)\s*[,，]|보유한\s*목표|보유할 경우|받을 시|추가 후|추가 시|명중 시|획득 시")
RE_EFFECT = re.compile(r"「?([가-힣]{1,6}\s*효과)」?(?:의)?\s*(?:로부터\s*)?(?:받는\s*)?피해")


def describe(o):
    stat = o.get("stat")
    scope = o.get("scope") or "전체"
    el = o.get("element")
    v = o.get("value") or 0
    label = o.get("label") or ""
    if stat == "res_shred":
        return "%s 저항" % (el or "전 속성"), -v
    if stat == "def_ignore":
        return "방어력 무시", v
    if stat == "atk":
        return "공격력", v
    if stat == "crit_rate":
        return "크리티컬", v
    if stat == "crit_dmg":
        return "크리티컬 피해", v
    if stat == "damage_taken":
        m = RE_EFFECT.search(label)
        what = m.group(1).replace(" ", " ") + " 피해" if m else (scope if scope not in ("받는 피해", "전체") else "피해")
        return "적이 받는 %s" % what, v
    if scope in ("전체", None, ""):
        return ("%s 피해" % el) if el else "전체 피해", v
    return ("%s %s 피해" % (el, scope.replace(" 피해", ""))) if el else \
        (scope if scope.endswith("피해") else scope + " 피해"), v


def outro_profile(con, cid, mode=None):
    row = con.execute(
        "SELECT id, skill_type, name, describe_text FROM skills "
        "WHERE character_id=? AND skill_type=11", (cid,)).fetchone()
    if not row:
        return None
    text = row[3] or ""
    found, _ = rules.extract([row])

    available = modes.character_modes(con, cid)
    if available and mode not in available:
        mode = available[0]

    order = {}
    blocked = set()
    for i, raw in enumerate(text.split("\n")):
        line = raw.strip().lstrip("·-• ").strip()
        if not line:
            continue
        order.setdefault(line, i)
        if available:
            hits = [n for n in available if n in line]
            if hits and mode and mode not in hits:
                blocked.add(line)

    picks = []
    for f in found:
        label = f.get("label") or ""
        if RE_PER_ANY.search(label) or "피해를 입히기 전" in label:
            continue
        cap = RE_OUTRO_CAP.search(f["source_line"][f["source_line"].find(label) + len(label):]
                                  if label in f["source_line"] else "")
        if cap and f.get("value") is not None and f["value"] < float(cap.group(1)):
            f = dict(f, value=float(cap.group(1)), stacking=True)
        sl = f["source_line"]
        cut = sl.find(label) + len(label) if label in sl else 0
        head = sl[:cut]
        head = head[max(head.rfind("다."), head.rfind(". ")) + 1:]
        f = dict(f, cond=bool(RE_OUTRO_COND.search(RE_MODE_CLAUSE.sub("", head)))
                 or bool(re.match(r"^\s*[^:：.]{1,12}상태\s*[:：]", sl)))
        if f["stat"] == "damage_taken" and re.search(r"적|목표", label):
            f["holder"] = "on_field"
        if f["holder"] not in ("next_entrant", "party", "on_field"):
            continue
        if f["stat"] not in ("dmg_boost", "dmg_bonus", "atk", "crit_rate",
                             "crit_dmg", "def_ignore", "damage_taken", "res_shred"):
            continue
        if f["source_line"] in blocked:
            continue
        picks.append((order.get(f["source_line"], 99), f))
    if not picks:
        return None
    picks.sort(key=lambda x: (x[0], x[1]["stat"] in ("damage_taken", "res_shred")))
    primary = picks[0][1]

    extras = []
    for _i, f in picks[1:]:
        extras.append({
            "label": f.get("label"),
            "stacking": f.get("stacking", False),
            "conditional": f.get("cond", False),
            "stat": f["stat"],
            "scope": f.get("scope_skill") or "전체",
            "element": f.get("scope_element"),
            "holder": f["holder"],
            "value": f["value"],
            "duration": f.get("duration"),
            "source_line": f["source_line"],
        })

    for item in [primary] + [f for _i, f in picks[1:]]:
        if item["stat"] not in ("dmg_boost", "dmg_bonus"):
            what, _v = describe({"stat": item["stat"], "scope": item.get("scope_skill"),
                                 "element": item.get("scope_element"), "value": item["value"],
                                 "label": item.get("label")})
            item["scope_skill"] = what + (" 감소" if item["stat"] == "res_shred" else "")
    extras = [dict(e, scope=f.get("scope_skill") or "전체") for e, (_i, f) in zip(extras, picks[1:])]
    tags = RE_TAG.findall(primary["source_line"])
    return {
        "tags": tags,
        "stat": primary["stat"],
        "scope": primary.get("scope_skill") or "전체",
        "element": primary.get("scope_element"),
        "holder": primary["holder"],
        "party_wide": primary["holder"] in ("party", "on_field"),
        "value": primary["value"],
        "duration": primary.get("duration"),
        "source_line": primary["source_line"],
        "extras": extras,
        "mode": mode,
        "modes": available,
        "conditional": primary.get("cond", False),
        "label": primary.get("label"),
        "stacking": primary.get("stacking", False),
    }


def analyze(con, cid, level=10, mode=None):
    name = con.execute("SELECT name FROM characters WHERE id=?", (cid,)).fetchone()[0]
    c = concerto_profile(con, cid, level)
    b = burst_profile(con, cid, level)
    o = outro_profile(con, cid, mode)
    shortfall = max(0.0, CONCERTO_FULL - c["skill_gain"])
    return {
        "id": cid,
        "name": name,
        "mode": mode,
        "modes": modes.character_modes(con, cid),
        "skill_gain": c["skill_gain"],
        "normal_gain": c["normal_gain"],
        "sources": c["sources"],
        "self_sufficient": shortfall <= 0,
        "shortfall": shortfall,
        "burst": b,
        "outro": o,
    }


def rank(con, level=10):
    ids = [r[0] for r in con.execute(
        "SELECT id FROM characters WHERE is_alias=0 ORDER BY name")]
    out = [analyze(con, cid, level) for cid in ids]
    out.sort(key=lambda x: -x["skill_gain"])
    return out


def party_check(con, cids, level=10):
    members = [analyze(con, cid, level) for cid in cids]
    ok = [m for m in members if m["self_sufficient"]]
    notes = []

    if len(ok) == len(members):
        verdict = "평타 없이 스킬만으로 순환 가능"
    elif ok:
        verdict = "일부만 자력 순환 · 나머지는 평타로 보충 필요"
    else:
        verdict = "전원 평타 보충 필요"

    for m in members:
        if not m["self_sufficient"]:
            notes.append("%s: 스킬 수급 %.0f · %.0f 부족" % (
                m["name"], m["skill_gain"], m["shortfall"]))
        if m["normal_gain"]:
            notes.append("%s: 일반 공격 수급 %.0f 별도 보유" % (m["name"], m["normal_gain"]))

    windows = []
    n = len(members)
    for i, m in enumerate(members):
        giver = members[(i - 1) % n]
        o = giver["outro"]
        if not o or not o.get("duration"):
            continue
        cd = m["burst"]["cooldown"]
        windows.append({
            "receiver": m["name"],
            "giver": giver["name"],
            "scope": o["scope"],
            "value": o["value"],
            "duration": o["duration"],
            "burst_cd": cd,
            "fits": bool(cd and cd <= o["duration"]),
        })

    return {"members": members, "verdict": verdict, "notes": notes, "windows": windows}


def format_party(result):
    out = ["퀵스왑 판정: %s" % result["verdict"], ""]
    for m in result["members"]:
        mark = "자력" if m["self_sufficient"] else "부족 %.0f" % m["shortfall"]
        out.append("%-12s 스킬 수급 %5.0f / 100  [%s]" % (m["name"], m["skill_gain"], mark))
        if m["normal_gain"]:
            out.append("             일반 공격 수급 %.0f (별도)" % m["normal_gain"])
        b = m["burst"]
        if b["cost"]:
            out.append("             공명 해방 %.0f%% / %.0f에너지 (효율 %.1f) · 쿨 %.0f초"
                       % (b["damage"], b["cost"], b["efficiency"], b["cooldown"]))
    out.append("")
    if result["windows"]:
        out.append("반주 버프 창 vs 공명 해방 쿨타임")
        for w in result["windows"]:
            state = "창 안에 궁 가능" if w["fits"] else "궁 쿨이 버프보다 길어 2주기에 1회"
            out.append("  %s ← %s : %s %+g%% %g초 vs 궁 쿨 %g초 → %s" % (
                w["receiver"], w["giver"], w["scope"], w["value"],
                w["duration"], w["burst_cd"], state))
    if result["notes"]:
        out.append("")
        out.append("참고")
        for n in result["notes"]:
            out.append("  · " + n)
    return "\n".join(out)
