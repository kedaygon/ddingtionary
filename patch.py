import difflib
import html
import json
import re

import parser as rich
import theme

CONTEXT = 70
RE_TOKEN = re.compile(r"\s+|[^\s\w]|\w+", re.U)
TYPE_NAMES = {1: "일반 공격", 2: "공명 스킬", 3: "공명 해방", 4: "고유 스킬", 5: "변주 스킬",
              6: "공명 회로", 7: "고유 스킬", 8: "고유 스킬", 9: "고유 스킬", 10: "고유 스킬",
              11: "반주 스킬", 12: "조화도 파괴"}
CATEGORIES = [
    ("new_chars", "새 캐릭터"),
    ("skill_text", "스킬 설명 변경"),
    ("skill_values", "스킬 배율 변경"),
    ("chains", "공명 체인 변경"),
    ("new_weapons", "새 무기"),
    ("weapons", "무기 효과 변경"),
    ("sets", "에코 세트 변경"),
]


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def diff_html(old, new):
    a = RE_TOKEN.findall(old or "")
    b = RE_TOKEN.findall(new or "")
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    out = []
    ops = sm.get_opcodes()
    for n, (op, i1, i2, j1, j2) in enumerate(ops):
        if op == "equal":
            seg = "".join(a[i1:i2])
            first, last = n == 0, n == len(ops) - 1
            if len(seg) > CONTEXT * 2 + 20 and len(ops) > 1:
                head = "" if first else seg[:CONTEXT]
                tail = "" if last else seg[-CONTEXT:]
                seg_html = _esc(head) + "<span style='color:%s'> … </span>" % theme.TEXT_DIM + _esc(tail)
                out.append(seg_html)
            else:
                out.append(_esc(seg))
            continue
        if i2 > i1:
            out.append("<span style='color:%s;text-decoration:line-through'>%s</span>"
                       % (theme.BAD, _esc("".join(a[i1:i2]))))
        if j2 > j1:
            out.append("<span style='color:%s;font-weight:600'>%s</span>"
                       % (theme.GOOD, _esc("".join(b[j1:j2]))))
    return "".join(out)


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _esc(s):
    return html.escape(s).replace("\n", "<br>")


def _table(con, sql, args=()):
    try:
        return con.execute(sql, args).fetchall()
    except Exception:
        return []


def _chars(con):
    return {cid: (name, elem) for cid, name, elem in _table(
        con, "SELECT id, name, element_id FROM characters WHERE is_alias=0")}


def _skills(con):
    return {sid: (cid, st, name, _norm(t), grp) for sid, cid, st, name, t, grp in _table(
        con, "SELECT id, character_id, skill_type, name, describe_text, skill_level_group_id FROM skills")}


def _values(con):
    out = {}
    for grp, attr, lv, pct, flat, raw in _table(con, """
            SELECT sc.skill_level_group_id, sc.attribute_name, sl.level, sl.total_pct,
                   sl.total_flat, sl.raw
            FROM skill_scalings sc JOIN scaling_levels sl ON sl.scaling_id=sc.id"""):
        out.setdefault((grp, _norm(attr)), {})[lv] = raw or ""
    return out


def _weapon_text(desc, params, rank):
    try:
        plist = json.loads(params or "[]")
    except ValueError:
        plist = []
    r = rank - 1
    vals = [(p[r] if r < len(p) else (p[-1] if p else "")) for p in plist]
    text, _m = rich.substitute(desc or "", vals)
    return _norm(rich.strip_tags(text))


def compare(old, new):
    res = {k: [] for k, _n in CATEGORIES}
    oc, nc = _chars(old), _chars(new)
    for cid in sorted(set(nc) - set(oc), key=lambda c: nc[c][0]):
        res["new_chars"].append({"cid": cid, "name": nc[cid][0]})
    os_, ns = _skills(old), _skills(new)
    for sid, (cid, st, name, text, grp) in ns.items():
        if cid not in oc or sid not in os_:
            continue
        o = os_[sid]
        if o[3] != text and text:
            res["skill_text"].append({"cid": cid, "name": nc.get(cid, ("", 0))[0],
                                      "what": "%s · %s" % (TYPE_NAMES.get(st, ""), name),
                                      "old": o[3], "new": text})
    ov, nv = _values(old), _values(new)
    group_owner = {}
    for sid, (cid, st, name, _t, grp) in ns.items():
        group_owner.setdefault(grp, (cid, st, name))
    for key, levels in nv.items():
        if key not in ov:
            continue
        grp, attr = key
        owner = group_owner.get(grp)
        if not owner or owner[0] not in oc:
            continue
        top = max(levels)
        old_top = ov[key].get(top)
        if old_top is None or _norm(old_top) == _norm(levels[top]):
            continue
        cid, st, name = owner
        res["skill_values"].append({"cid": cid, "name": nc.get(cid, ("", 0))[0],
                                    "what": "%s · %s · %s" % (TYPE_NAMES.get(st, ""), name, attr),
                                    "level": top, "old": ov[key][top], "new": levels[top]})
    och = {(c, i): (n, _norm(t)) for c, i, n, t in _table(
        old, "SELECT character_id, idx, name, describe_text FROM chains")}
    for c, i, n, t in _table(new, "SELECT character_id, idx, name, describe_text FROM chains"):
        if c in oc and (c, i) in och and och[(c, i)][1] != _norm(t):
            res["chains"].append({"cid": c, "name": nc.get(c, ("", 0))[0],
                                  "what": "%d체인 · %s" % (i, n), "old": och[(c, i)][1], "new": _norm(t)})
    ow = {w[0]: w for w in _table(old, "SELECT id, name, quality, weapon_type, desc_raw, params FROM weapons")}
    for wid, name, q, wt, desc, params in _table(
            new, "SELECT id, name, quality, weapon_type, desc_raw, params FROM weapons"):
        if wid not in ow:
            if ow:
                res["new_weapons"].append({"name": name, "quality": _int(q), "type": _int(wt),
                                           "text": _weapon_text(desc, params, 1)})
            continue
        for rank in (1, 5):
            a = _weapon_text(ow[wid][4], ow[wid][5], rank)
            b = _weapon_text(desc, params, rank)
            if a != b:
                res["weapons"].append({"name": name, "quality": _int(q), "what": "%d재련" % rank,
                                       "old": a, "new": b})
                break
    osets = {(i, p): (n, _norm(t)) for i, p, n, t in _table(
        old, "SELECT id, pieces, name, desc_text FROM echo_sets")}
    for i, p, n, t in _table(new, "SELECT id, pieces, name, desc_text FROM echo_sets"):
        if (i, p) not in osets:
            if osets:
                res["sets"].append({"name": n, "what": "%d세트 · 새 세트" % p, "old": "", "new": _norm(t)})
        elif osets[(i, p)][1] != _norm(t):
            res["sets"].append({"name": n, "what": "%d세트" % p, "old": osets[(i, p)][1], "new": _norm(t)})
    return res
