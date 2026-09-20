import re
from collections import defaultdict

import skilldata

RE_TAG = re.compile(r"「([^」]{2,24})」")

UNIVERSAL_MIN = 9

MECHANICS = ("광학 효과", "암흑 효과", "풍식 효과", "전자 효과", "서리 효과",
             "불꽃 효과", "이상 효과", "협동 공격", "조화 파동", "조화 밀집",
             "해킹")
MECH_MAX = 14

GRANT_HINTS = ("추가한다", "부여", "진입시키", "누적", "축적", "발동시키",
               "획득시키", "표기를 추가", "상태에 진입")
USE_HINTS = ("보유할", "보유한", "상태에 있", "상태에 진입 시",
             "보유할 때마다", "있을 경우", "상태의")

BUFF_HINTS = ("증가", "부스트", "상승", "감소")

_cache = {}


def tag_map(con):
    key = id(con)
    if key in _cache:
        return _cache[key]
    tags = defaultdict(set)
    mech = defaultdict(set)
    for cid, name, _b, _v, _e in skilldata.characters(con):
        for (t,) in con.execute(
                "SELECT describe_text FROM skills WHERE character_id=? "
                "AND describe_text IS NOT NULL", (cid,)):
            for m in RE_TAG.finditer(t or ""):
                tags[m.group(1)].add(cid)
            for k in MECHANICS:
                if k in (t or ""):
                    mech[k].add(cid)
    shared = {k: v for k, v in tags.items() if 2 <= len(v) < UNIVERSAL_MIN}
    for k, v in mech.items():
        if 2 <= len(v) <= MECH_MAX and not any(k in t for t in shared):
            shared[k] = v
    _cache[key] = shared
    return shared


def character_tags(con, cid):
    out = {}
    for tag, owners in tag_map(con).items():
        if cid not in owners:
            continue
        out[tag] = role_of(con, cid, tag)
    return out


def role_of(con, cid, tag):
    grant = use = buff = boost = 0
    quoted = "「%s」" % tag if tag not in MECHANICS else tag
    for (t,) in con.execute(
            "SELECT describe_text FROM skills WHERE character_id=? "
            "AND describe_text IS NOT NULL", (cid,)):
        for line in (t or "").split("\n"):
            if quoted not in line:
                continue
            tail = line.split(quoted, 1)[1][:60]
            if any(h in tail for h in GRANT_HINTS):
                grant += 1
            if any(h in tail for h in USE_HINTS):
                use += 1
            if any(h in line for h in BUFF_HINTS):
                buff += 1
                if any(h in line for h in ("다음 등장 캐릭터", "파티")):
                    boost += 1
    if boost and not grant:
        return "강화"
    if use and buff:
        return "활용"
    if grant and not use:
        return "부여"
    if use:
        return "활용"
    return "보유"


def pairs(con, cids):
    shared = tag_map(con)
    members = {cid: skilldata.character_name(con, cid) for cid in cids}
    out = []
    for tag, owners in shared.items():
        inside = [c for c in cids if c in owners]
        if len(inside) < 2:
            continue
        roles = [(members[c], role_of(con, c, tag)) for c in inside]
        out.append({
            "tag": tag,
            "members": roles,
            "outside": len(owners) - len(inside),
        })
    out.sort(key=lambda x: (-len(x["members"]), x["tag"]))
    return out


def suggest(con, cids, limit=8):
    shared = tag_map(con)
    have = defaultdict(list)
    for tag, owners in shared.items():
        for c in cids:
            if c in owners:
                have[tag].append(c)
    scores = defaultdict(list)
    for tag, mine in have.items():
        for other in shared[tag]:
            if other in cids:
                continue
            scores[other].append(tag)
    out = []
    for cid, tags in scores.items():
        out.append({
            "id": cid,
            "name": skilldata.character_name(con, cid),
            "tags": sorted(tags),
        })
    out.sort(key=lambda x: -len(x["tags"]))
    return out[:limit]
