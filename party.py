import itertools

import analysis
import cycle
import quickswap

SCOPE_ALL = ("전체", None, "")


def coverage(profile, scope, element=None):
    if element and profile.get("element") and element != profile["element"]:
        return 0.0, "%s 피해" % element
    label = scope
    if element and scope in SCOPE_ALL:
        label = "%s 피해" % element
    if scope in SCOPE_ALL:
        return 100.0, label if element else "전체 피해"
    if scope == cycle.COOP:
        char = profile.get("char") or {}
        entries = char.get("entries") or []
        base = sum(e["pct"] for e in entries) or 1.0
        hit = sum(cycle.coop_pct(e) for e in entries)
        return hit / base * 100.0, label
    if scope in (cycle.AIR, cycle.DODGE):
        char = profile.get("char") or {}
        entries = char.get("entries") or []
        base = sum(e["pct"] for e in entries) or 1.0
        hit = sum(e["pct"] for e in entries if e.get("action") == scope)
        return hit / base * 100.0, label
    known = {r["category"] for r in profile["rows"]}
    if scope not in known and scope not in cycle.CATEGORY_ORDER:
        return None, scope
    total = profile["total"] or 1.0
    hit = sum(r["total"] for r in profile["rows"] if r["category"] == scope)
    return hit / total * 100.0, label


def member(con, cid, level=10, mode=None, chain=0):
    import chainfx
    import synergy
    info = quickswap.analyze(con, cid, level, mode)
    info["chain"] = chain or 0
    import modes as _modes
    eff = info.get("mode") or mode or (_modes.character_modes(con, cid) or [None])[0]
    info["chain_buffs"] = chainfx.party_buffs(con, cid, chain or 0, eff)
    prof = analysis.damage_profile(con, cid, level, info.get("mode"))
    prof["element"] = _element_of(con, cid)
    info["profile"] = prof
    info["tags"] = set(synergy.character_tags(con, cid))
    return info


def _element_of(con, cid):
    import skilldata
    row = con.execute(
        "SELECT element_id FROM characters WHERE id=?", (cid,)).fetchone()
    return skilldata.ELEMENTS.get(row[0]) if row else None


def _tags_of(member, tags):
    owned = member.get("tags") or set()
    return [t for t in tags if t in owned]


def _apply(profile, outro):
    if outro.get("stat") not in (None, "dmg_boost", "dmg_bonus"):
        what, _v = quickswap.describe(outro)
        return None, what, 0.0
    cov, scope = coverage(profile, outro["scope"], outro.get("element"))
    gain = 0.0 if cov is None else (outro["value"] or 0.0) * cov / 100.0
    return cov, scope, gain


def evaluate_order(order):
    n = len(order)
    shared = [(m, m["outro"]) for m in order
              if m["outro"] and m["outro"].get("party_wide")]
    legs = []
    total_gain = 0.0
    for i, m in enumerate(order):
        giver = order[(i - 1) % n]
        o = giver["outro"]
        cov = scope = None
        gain = 0.0
        bonus = []
        own = 0.0
        unknown = None
        if o and not o.get("party_wide"):
            cov, scope, gain = _apply(m["profile"], o)
            own = gain
            if cov is None:
                unknown = {"scope": scope, "value": o["value"],
                           "tags": o.get("tags") or [],
                           "tag_match": _tags_of(m, o.get("tags") or [])}
            for ex in o.get("extras") or []:
                if (ex.get("value") or 0) < 1:
                    continue
                ecov, escope, egain = _apply(m["profile"], ex)
                if ecov:
                    bonus.append({"scope": escope, "value": ex["value"],
                                  "coverage": ecov, "gain": egain})
                    gain += egain
        giver_wide = bool(o and o.get("party_wide"))
        if giver_wide:
            o = None

        extras = []
        for src, so in shared:
            if src is m:
                continue
            scov, sscope, sgain = _apply(m["profile"], so)
            entry = {"from": src["name"], "scope": sscope,
                     "value": so["value"], "coverage": scov,
                     "gain": sgain if scov is not None else 0.0,
                     "duration": so.get("duration"),
                     "tags": so.get("tags") or [],
                     "tag_match": []}
            if scov is None and entry["tags"]:
                entry["tag_match"] = _tags_of(m, entry["tags"])
            extras.append(entry)
            if scov is not None:
                gain += sgain

        chain_rows = []
        for src in order:
            for cb in src.get("chain_buffs") or []:
                entry = {"from": src["name"], "idx": cb["idx"],
                         "scope": cb["scope"], "value": cb["value"],
                         "stat": cb["stat"], "counted": cb["counted"],
                         "coverage": None, "gain": 0.0}
                if cb["counted"]:
                    ccov, cscope, cgain = _apply(m["profile"], cb)
                    entry["scope"] = cscope
                    entry["coverage"] = ccov
                    if ccov is not None:
                        entry["gain"] = cgain
                        gain += cgain
                chain_rows.append(entry)

        mismatch = bool(o and o.get("element")
                        and m["profile"].get("element")
                        and o["element"] != m["profile"]["element"])
        legs.append({
            "receiver": m,
            "giver": giver,
            "outro": o,
            "element_mismatch": mismatch,
            "coverage": cov,
            "scope": scope,
            "shared": extras,
            "chains": chain_rows,
            "giver_party_wide": giver_wide,
            "unknown": unknown,
            "bonus": bonus,
            "own_gain": own,
            "gain": gain,
        })
        total_gain += gain
    return {"order": order, "legs": legs, "score": total_gain}


def rotations(members):
    seen = set()
    out = []
    for perm in itertools.permutations(members):
        key = _cycle_key(perm)
        if key in seen:
            continue
        seen.add(key)
        out.append(evaluate_order(list(perm)))
    return out


def _cycle_key(perm):
    ids = [m["id"] for m in perm]
    n = len(ids)
    rots = [tuple(ids[i:] + ids[:i]) for i in range(n)]
    return min(rots)


def summarize(result):
    legs = result["legs"]
    if not legs:
        return {"total": 0.0, "avg": 0.0, "top": None}
    total = sum(l["gain"] for l in legs)
    top = max(legs, key=lambda l: l["gain"])
    return {
        "total": total,
        "avg": total / len(legs),
        "top": top,
    }


def plan(con, cids, level=10, modes_by_id=None, chains_by_id=None):
    modes_by_id = modes_by_id or {}
    chains_by_id = chains_by_id or {}
    members = [member(con, cid, level, modes_by_id.get(cid), chains_by_id.get(cid, 0))
               for cid in cids]
    current = evaluate_order(list(members))
    alternatives = sorted(rotations(members), key=lambda r: -r["score"])
    results = [current] + [r for r in alternatives
                           if _cycle_key(r["order"]) != _cycle_key(current["order"])]
    best = current

    self_ok = [m for m in members if m["self_sufficient"]]
    if len(self_ok) == len(members):
        verdict = "평타 없이 스킬만으로 순환 가능"
        verdict_kind = "good"
    elif self_ok:
        verdict = "일부만 자력 순환 · 나머지는 평타로 보충"
        verdict_kind = "warn"
    else:
        verdict = "전원 평타 보충 필요"
        verdict_kind = "warn"

    best_alt = alternatives[0] if alternatives else current

    windows = []
    for leg in best["legs"]:
        o = leg["outro"]
        if not o or not o.get("duration"):
            continue
        cd = leg["receiver"]["burst"]["cooldown"]
        windows.append({
            "receiver": leg["receiver"]["name"],
            "giver": leg["giver"]["name"],
            "duration": o["duration"],
            "cooldown": cd,
            "fits": bool(cd and cd <= o["duration"]),
        })

    return {
        "members": members,
        "results": results,
        "best": best,
        "best_alt": best_alt,
        "summary": summarize(best),
        "verdict": verdict,
        "verdict_kind": verdict_kind,
        "windows": windows,
    }


def rotation_lines(char, limit=6):
    picks = cycle.rotation(char["char"] if "char" in char else char)
    return picks[:limit]


def suggest_partners(con, cid, level=10, limit=8, mode=None):
    target = member(con, cid, level, mode)
    out = []
    for other_id, name, _b, _v, elem in _all_ids(con):
        if other_id == cid:
            continue
        other = quickswap.analyze(con, other_id, level)
        o = other["outro"]
        if not o:
            continue
        cov, scope = coverage(target["profile"], o["scope"], o.get("element"))
        if cov is None or cov <= 0:
            continue
        out.append({
            "id": other_id,
            "name": name,
            "element": elem,
            "scope": scope,
            "party_wide": o.get("party_wide", False),
            "value": o["value"],
            "duration": o["duration"],
            "coverage": cov,
            "gain": (o["value"] or 0.0) * cov / 100.0,
            "concerto": other["skill_gain"],
        })
    out.sort(key=lambda x: -x["gain"])
    return target, out[:limit]


def _all_ids(con):
    import skilldata
    return skilldata.characters(con)
