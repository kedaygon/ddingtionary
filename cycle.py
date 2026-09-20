import itertools
import re

import classify
import dmgtype
import modes
import rules

HEAVY = "강공격"
NORMAL = "일반 공격"
SKILL = "공명 스킬"
BURST = "공명 해방"
INTRO = "변주 스킬"
OUTRO = "반주 스킬"
AIR = "공중 공격"
DODGE = "회피 반격"
ECHO = "에코 어빌리티"

HARMONY = "조화 파동"
STAGGER = "조화도 파괴"

COOP = "협동 공격"
HACK = "해킹"
UNKNOWN = classify.UNKNOWN
UNCLEAR = "판정 불명확"

CATEGORY_ORDER = [BURST, SKILL, HEAVY, DODGE, NORMAL, AIR, ECHO,
                  HARMONY, INTRO, OUTRO, STAGGER, COOP, HACK, UNCLEAR, UNKNOWN]

TYPE_CATEGORY = {1: NORMAL, 2: SKILL, 3: BURST, 5: INTRO, 11: OUTRO, 12: "조화도 파괴"}

ENERGY_GAIN = "협주 에너지"
ENERGY_COST = "공명 에너지 소모"
COOLDOWN = "쿨타임"

CONCERTO_FULL = 100.0

_RECLASS = re.compile(r"해당 피해는\s*(강공격|일반 공격|공명 해방|공명 스킬)\s*피해로 적용")
_TAIL = re.compile(r"\s*(?:피해량|피해|치료량)$")


def _clean(name):
    return re.sub(r"\s+", " ", (name or "")).strip()


def base_name(attr):
    return _TAIL.sub("", _clean(attr))


def reclass_map(text, attrs):
    out = {}
    names = sorted(((base_name(a), a) for a in attrs), key=lambda x: -len(x[0]))
    for line in (text or "").split("\n"):
        m = _RECLASS.search(line)
        if not m:
            continue
        target = m.group(1)
        head = line[:m.start()]
        for nm, attr in names:
            if len(nm) >= 4 and nm in head:
                out[attr] = target
    return out


def load_character(con, cid, level=10, mode=None):
    name = con.execute("SELECT name FROM characters WHERE id=?", (cid,)).fetchone()[0]
    skills = con.execute(
        "SELECT id, skill_type, name, describe_text, skill_level_group_id "
        "FROM skills WHERE character_id=? ORDER BY skill_type", (cid,)).fetchall()

    available = modes.character_modes(con, cid)
    if available and mode not in available:
        mode = available[0]
    if not available:
        mode = None

    clf = classify.Classifier(con, cid, mode)

    entries = []
    energy_gain = 0.0
    energy_cost = 0.0
    cooldowns = {}

    data = dmgtype.lookup(con)
    for sid, stype, sname, text, group in skills:
        base_cat = classify.TYPE_DEFAULT.get(stype, UNKNOWN)
        rows = con.execute(
            "SELECT sc.id, sc.attribute_name, sl.total_pct, sl.total_flat, sl.total_hits, "
            "sc.scale_kind, sl.raw "
            "FROM skill_scalings sc JOIN scaling_levels sl "
            "ON sl.scaling_id=sc.id AND sl.level=? "
            "WHERE sc.skill_level_group_id=? ORDER BY sc.sort_order",
            (level, group)).fetchall()
        pending = []
        for scid, attr, pct, flat, hits, kind, raw in rows:
            attr = _clean(attr)
            if ENERGY_GAIN in attr:
                energy_gain += flat or 0.0
                continue
            if ENERGY_COST in attr:
                energy_cost += flat or 0.0
                continue
            if COOLDOWN in attr:
                cooldowns[attr] = flat
                continue
            if not pct:
                continue
            if any(k in attr for k in classify.SKIP_ATTR):
                continue

            cat, nat, rec, why = clf.classify(attr, stype, sid)
            base = {
                "skill_id": sid,
                "skill_name": sname,
                "attr": attr,
                "pct": pct,
                "hits": hits,
                "natural": nat,
                "text_category": cat,
                "skill_default": base_cat,
                "skill_type": stype,
                "coop": clf.is_coop(attr),
                "action": action_of(attr),
                "scale": kind or "atk",
                "raw": raw,
            }
            pending.append((base, cat, why, data.get(scid)))
        entries.extend(_resolve(pending))
    outro = outro_buff(con, cid, mode)
    return {
        "outro_damage": outro_damage(con, cid, clf),
        "id": cid,
        "name": name,
        "mode": mode,
        "modes": available,
        "entries": entries,
        "energy_gain": energy_gain,
        "energy_cost": energy_cost,
        "cooldowns": cooldowns,
        "outro": outro,
    }


def action_of(attr):
    a = classify.squash(attr)
    if "회피반격" in a:
        return DODGE
    if "공중" in a or "낙하" in a:
        return AIR
    return None


def coop_pct(e):
    if "coop_frac" in e:
        return e["pct"] * e["coop_frac"]
    return e["pct"] if e.get("coop") else 0.0


def _cat_type(cat):
    for t, c in dmgtype.TYPE_CATS.items():
        if c == cat:
            return t
    return None


def _entry(base, cat, share, reason, options=None):
    e = dict(base)
    e["category"] = cat
    e["pct"] = base["pct"] * share
    e["share_of_attr"] = share
    e["reason"] = reason
    e["reclassed"] = cat != base["skill_default"]
    e["options"] = options or []
    return e


def _pure(option, t):
    return t is not None and set(option) == {str(t)}


def _emit(base, option, reason):
    coop = option.get("coop", 0.0)
    out = []
    for t, share in option.items():
        if t == "coop":
            continue
        e = _entry(base, dmgtype.TYPE_CATS[int(t)], share, reason)
        e["coop_frac"] = min(1.0, coop / sum(v for k, v in option.items() if k != "coop"))
        e["coop"] = coop > 0
        out.append(e)
    return out


def _known(option):
    return all(k == "coop" or int(k) in dmgtype.TYPE_CATS for k in option)


def _fallback(base, cat, why):
    if cat in (AIR, DODGE):
        cat, why = UNKNOWN, "근거 없음"
    return _entry(base, cat, 1.0, why)


def _resolve(pending):
    out = []
    taken = {}
    for base, cat, why, info in pending:
        if info and "options" in info:
            t = _cat_type(cat)
            hit = [o for o in info["options"] if _pure({k: v for k, v in o.items() if k != "coop"}, t)]
            if len(hit) == 1 and why not in ("스킬 종류", "근거 없음"):
                taken.setdefault(base["raw"], []).append(hit[0])
    for base, cat, why, info in pending:
        if not info:
            out.append(_fallback(base, cat, why))
            continue
        if "options" not in info:
            if _known(info):
                out.extend(_emit(base, info, "게임 데이터"))
            else:
                out.append(_fallback(base, cat, why))
            continue
        options = [o for o in info["options"] if _known(o)]
        t = _cat_type(cat)
        hit = [o for o in options if _pure({k: v for k, v in o.items() if k != "coop"}, t)]
        if len(hit) == 1 and why not in ("스킬 종류", "근거 없음"):
            out.extend(_emit(base, hit[0], "게임 데이터+원문"))
            continue
        if not hit and why == "원문 '해당 피해는'" and t is not None:
            out.append(_entry(base, cat, 1.0, why))
            continue
        rest = [o for o in options if o not in taken.get(base["raw"], [])]
        if len(rest) == 1 and len(options) > 1:
            out.extend(_emit(base, rest[0], "게임 데이터(소거)"))
            continue
        cats = []
        for o in options:
            label = " + ".join(dmgtype.TYPE_CATS[int(k)] for k in o if k != "coop")
            if label not in cats:
                cats.append(label)
        out.append(_entry(base, UNCLEAR, 1.0, "게임 데이터상 후보 여럿", cats))
    return out


RE_OUTRO_DMG = re.compile(r"\d+(?:\.\d+)?%(?:\*\d+)?(?:\+\d+(?:\.\d+)?%(?:\*\d+)?)*\s*"
                          r"(?:에\s*해당(?:하|되)는|의)\s*[^.%]{0,16}?피해를\s*(?:입|가)")


def outro_damage(con, cid, clf):
    row = con.execute("SELECT id, describe_text FROM skills WHERE character_id=? AND skill_type=11",
                      (cid,)).fetchone()
    if not row:
        return []
    out = []
    for line in re.split(r"(?<=[.。])\s+|\n", row[1] or ""):
        if not RE_OUTRO_DMG.search(line):
            continue
        m = classify.RE_APPLY.search(classify.norm(line))
        cat = OUTRO
        if m:
            got = classify.canon_cat(re.sub(r"\s*피해$", "", re.split(r"\s*/\s*", m.group("t"))[0]))
            cat = got or OUTRO
        out.append({"text": line.strip(), "category": cat, "coop": "협동 공격" in line})
    return out


def outro_buff(con, cid, mode=None):
    row = con.execute(
        "SELECT id, skill_type, name, describe_text FROM skills "
        "WHERE character_id=? AND skill_type=11", (cid,)).fetchone()
    if not row:
        return None
    found, _ = rules.extract([row])
    forced = "다음 등장 캐릭터" in (row[3] or "")
    best = None
    for f in found:
        if f["holder"] != "next_entrant" and not forced:
            continue
        if best is None or (f["value"] or 0) > (best["value"] or 0):
            best = f
    if best:
        best["scope_element"] = None
    return best


def rotation(char, top_n=6):
    by_cat = {}
    for e in char["entries"]:
        by_cat.setdefault(e["category"], []).append(e)
    picked = []
    for cat in CATEGORY_ORDER:
        items = sorted(by_cat.get(cat, []), key=lambda x: -x["pct"])
        if cat in (BURST, INTRO, OUTRO):
            picked.extend(items[:1])
        elif cat in (SKILL, HEAVY):
            picked.extend(items[:2])
        else:
            picked.extend(items[:1])
    picked = [p for p in picked if p["pct"] > 0][:top_n + 4]
    return picked


def buff_multiplier(buff, category):
    if not buff:
        return 1.0
    scope = buff.get("scope_skill")
    if scope and scope != category:
        return 1.0
    value = buff.get("value") or 0.0
    if buff.get("unit") != "pct":
        return 1.0
    return 1.0 + value / 100.0


def evaluate(order):
    total_base = 0.0
    total_buffed = 0.0
    legs = []
    n = len(order)
    for i, char in enumerate(order):
        giver = order[(i - 1) % n]
        buff = giver["outro"]
        picks = rotation(char)
        base = sum(p["pct"] for p in picks)
        buffed = sum(p["pct"] * buff_multiplier(buff, p["category"]) for p in picks)
        boosted = [p for p in picks if buff_multiplier(buff, p["category"]) > 1.0]
        legs.append({
            "char": char,
            "from": giver,
            "buff": buff,
            "picks": picks,
            "base": base,
            "buffed": buffed,
            "boosted": boosted,
            "concerto": char["energy_gain"],
            "concerto_ok": char["energy_gain"] >= CONCERTO_FULL,
        })
        total_base += base
        total_buffed += buffed
    return {
        "order": order,
        "legs": legs,
        "base": total_base,
        "buffed": total_buffed,
        "gain": (total_buffed / total_base - 1.0) * 100.0 if total_base else 0.0,
    }


def cyclic_orders(chars):
    first = chars[0]
    rest = chars[1:]
    return [[first] + list(p) for p in itertools.permutations(rest)]


def plan(con, char_ids, level=10):
    chars = [load_character(con, cid, level) for cid in char_ids]
    results = [evaluate(o) for o in cyclic_orders(chars)]
    results.sort(key=lambda r: -r["buffed"])
    return results


def format_report(results, level=10):
    out = []
    best = results[0]
    names = " → ".join(c["name"] for c in best["order"])
    out.append("권장 순환 (스킬 레벨 %d)" % level)
    out.append("  %s → (반복)" % names)
    out.append("")
    for leg in best["legs"]:
        c = leg["char"]
        out.append("%s  ← %s 반주" % (c["name"], leg["from"]["name"]))
        b = leg["buff"]
        if b:
            scope = b.get("scope_skill") or "전체"
            out.append("    받는 버프: %s %+g%% (%s), %s초" % (
                scope, b["value"], b["stat"], b.get("duration") or "-"))
        else:
            out.append("    받는 버프: 없음 (%s 반주는 피해만)" % leg["from"]["name"])
        for p in leg["picks"][:6]:
            mark = " ★" if p in leg["boosted"] else ""
            out.append("      %-34s %8.0f%%%s" % (p["attr"][:34], p["pct"], mark))
        out.append("    배율 합 %.0f%%  →  버프 적용 %.0f%%  (%+.0f%%)" % (
            leg["base"], leg["buffed"],
            (leg["buffed"] / leg["base"] - 1) * 100 if leg["base"] else 0))
        out.append("    협주 에너지 수급 %.0f / %d  %s" % (
            leg["concerto"], int(CONCERTO_FULL),
            "반주 발동 가능" if leg["concerto_ok"] else "부족 · 일반 공격 추가 필요"))
        out.append("")
    out.append("사이클 총합 %.0f%%  (버프 없을 때 %.0f%%,  %+.1f%%)" % (
        best["buffed"], best["base"], best["gain"]))
    if len(results) > 1:
        alt = results[1]
        out.append("")
        out.append("다른 순서 비교")
        for r in results:
            out.append("  %-28s %8.0f%%" % (
                " → ".join(c["name"] for c in r["order"]), r["buffed"]))
        out.append("  차이 %.0f%%" % (best["buffed"] - alt["buffed"]))
    return "\n".join(out)
