import re

TARGETS = ["일반 공격", "강공격", "공명 스킬", "공명 해방", "에코 어빌리티",
           "공중 공격", "회피 반격", "변주 스킬", "반주 스킬", "협동 공격",
           "조화 파동", "조화도 파괴"]

def _loose(t):
    return r"\s*".join(re.escape(part) for part in t.split())


_TARGET_RE = "|".join(_loose(t) for t in sorted(TARGETS, key=len, reverse=True))

RE_APPLY = re.compile(
    r"(?:해당\s*)?피해는\s*(?P<targets>(?:%s)(?:\s*피해)?(?:\s*/\s*(?:%s)(?:\s*피해)?)*)\s*"
    r"(?:피해)?로\s*(?:적용|간주)" % (_TARGET_RE, _TARGET_RE))

RE_STAGE_END = re.compile(r"(\d+)\s*단\s*$")
RE_STAGE_ONLY = re.compile(r"^\d+$")
RE_STAGE_NUM = re.compile(r"(\d+)\s*단")
RE_SPLIT_TOKENS = re.compile(r"[,、]")

RE_REPLACE = re.compile(
    r"(?P<from>(?:%s))\s*(?:은|는)\s*(?P<to>[^.。,\n]{2,40}?)\s*(?:으)?로\s*대체"
    % _TARGET_RE)

RE_MODE = re.compile(r"공명 모드\s*·\s*([가-힣A-Za-z]+(?:\s+[가-힣A-Za-z]+)?)")

MODE_STOP = {"있을", "있는", "상태", "효과", "진입", "전환", "발동", "시", "경우",
             "해당", "지속", "종료", "대응", "및", "혹은", "또는", "공명", "모드",
             "피해", "중", "내", "외", "동안", "기간", "때", "시의", "하나"}

_PARTICLE = re.compile(r"(?:에|이|가|을|를|와|과|은|는|의|로|으로)$")

RE_COND_SPLIT = re.compile(r"\s*/\s*")

_NAME_BAD = ("하고", "한다", "된다", "있다", "없다", "이다", "발동", "소모", "획득",
             "증가", "감소", "입힌다", "적용", "지속", "가능", "경우", "있을 시")

_TAIL = re.compile(r"\s*(?:피해량|피해|치료량|배율)$")


def parse_blocks(text):
    blocks = []
    cur = None
    for raw in (text or "").split("\n"):
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            cur = None
            continue
        bullet = stripped[0] in "·-•"
        body = stripped.lstrip("·-• ").strip()
        if not body:
            continue
        if cur is None:
            if not bullet and _looks_like_name(body):
                cur = {"name": body, "lines": []}
                blocks.append(cur)
            else:
                cur = {"name": None, "lines": [body]}
                blocks.append(cur)
        else:
            cur["lines"].append(body)
    return blocks


def _looks_like_name(s):
    if len(s) > 40:
        return False
    if s.endswith((".", "!")):
        return False
    return not any(k in s for k in _NAME_BAD)


def _clean_mode(raw):
    words = [w for w in raw.split() if w]
    keep = []
    for w in words:
        base = _PARTICLE.sub("", w)
        if base in MODE_STOP or w in MODE_STOP:
            break
        keep.append(base or w)
        if len(keep) == 2:
            break
    return " ".join(keep).strip()


def mode_counts(text):
    single = {}
    pair = {}
    for m in RE_MODE.finditer(text or ""):
        words = _clean_mode(m.group(1)).split()
        if not words:
            continue
        single[words[0]] = single.get(words[0], 0) + 1
        if len(words) > 1:
            key = " ".join(words[:2])
            pair[key] = pair.get(key, 0) + 1
    return single, pair


def modes_of(text):
    single, pair = mode_counts(text)
    compound = {}
    for key, n in pair.items():
        head = key.split()[0]
        if n >= 2 and n >= single.get(head, 0) * 0.5:
            compound[head] = key
    out = []
    for head in single:
        name = compound.get(head, head)
        if name and name not in out:
            out.append(name)
    return out


def character_modes(con, cid):
    blob = "\n".join(
        t or "" for (t,) in con.execute(
            "SELECT describe_text FROM skills WHERE character_id=? "
            "AND describe_text IS NOT NULL", (cid,)))
    names = modes_of(blob)
    if len(names) < 2:
        return []
    rules = reclass_rules(con, cid, names)
    buffs = mode_outro_lines(con, cid, names)
    used = {r["mode"] for r in rules if r["mode"]} | set(buffs)
    ordered = [n for n in names if n in used]
    return ordered if len(ordered) >= 2 else []


def mode_outro_lines(con, cid, names):
    row = con.execute(
        "SELECT describe_text FROM skills WHERE character_id=? AND skill_type=11",
        (cid,)).fetchone()
    found = set()
    if not row:
        return found
    for line in (row[0] or "").split("\n"):
        for n in names:
            if n in line:
                found.add(n)
    return found


def _norm_target(s):
    s = _TAIL.sub("", s.strip())
    s = re.sub(r"\s+", "", s)
    for t in TARGETS:
        if re.sub(r"\s+", "", t) == s:
            return t
    return s


def _stages_from(head):
    stages = []
    for tok in reversed(RE_SPLIT_TOKENS.split(head or "")):
        t = tok.strip()
        if not t:
            continue
        m = RE_STAGE_END.search(t)
        if m:
            stages.append(int(m.group(1)))
            continue
        if RE_STAGE_ONLY.match(t):
            stages.append(int(t))
            continue
        break
    return sorted(set(stages)) or None


def replace_rules(con, cid):
    rules = []
    rows = con.execute(
        "SELECT name, describe_text FROM skills WHERE character_id=? "
        "AND describe_text IS NOT NULL", (cid,)).fetchall()
    for sname, text in rows:
        for line in (text or "").split("\n"):
            for m in RE_REPLACE.finditer(line):
                src = m.group("from").strip()
                dst = m.group("to").strip()
                if not dst or src not in TARGETS:
                    continue
                if dst in TARGETS:
                    continue
                rules.append({"block": dst, "to": src, "mode": None,
                              "stages": None, "skill": sname, "weak": True})
    return rules


def reclass_rules(con, cid, names=None):
    rules = []
    rows = con.execute(
        "SELECT name, describe_text FROM skills WHERE character_id=? "
        "AND describe_text IS NOT NULL", (cid,)).fetchall()
    for sname, text in rows:
        for block in parse_blocks(text):
            bname = block["name"] or sname
            for line in block["lines"]:
                pos = 0
                for m in RE_APPLY.finditer(line):
                    targets = [_norm_target(x)
                               for x in RE_COND_SPLIT.split(m.group("targets"))]
                    targets = [t for t in targets if t in TARGETS]
                    head = line[pos:m.start()]
                    pos = m.end()
                    if not targets:
                        continue
                    stages = _stages_from(head)
                    mode_names = _modes_in(head, names)
                    if len(targets) > 1 and len(mode_names) == len(targets):
                        for mode, target in zip(mode_names, targets):
                            rules.append({"block": bname, "to": target,
                                          "mode": mode, "stages": stages,
                                          "skill": sname})
                    elif mode_names:
                        rules.append({"block": bname, "to": targets[0],
                                      "mode": mode_names[0], "stages": stages,
                                      "skill": sname})
                    else:
                        rules.append({"block": bname, "to": targets[0],
                                      "mode": None, "stages": stages,
                                      "skill": sname})
    return rules


def _modes_in(text, names=None):
    if names is None:
        return modes_of(text)
    out = []
    for n in sorted(names, key=len, reverse=True):
        idx = text.find(n)
        if idx >= 0 and n not in out:
            out.append((idx, n))
    return [n for _i, n in sorted(out)]


def reclass_map(con, cid, mode=None):
    names = character_modes(con, cid) or None
    out = []
    for r in replace_rules(con, cid):
        out.append(r)
    for r in reclass_rules(con, cid, names):
        if r["mode"] and mode and r["mode"] != mode:
            continue
        if r["mode"] and not mode:
            continue
        out.append(r)
    return out


def _stage_of(attr):
    nums = RE_STAGE_NUM.findall(attr or "")
    return int(nums[-1]) if nums else None


def resolve(attr, rules):
    hit = _resolve(attr, [r for r in rules if not r.get("weak")])
    if hit:
        return hit
    return _resolve(attr, [r for r in rules if r.get("weak")])


def _resolve(attr, rules):
    base = _TAIL.sub("", (attr or "").strip())
    stage = _stage_of(base)
    best = None
    best_score = -1
    for r in rules:
        for key in (r["block"], r.get("skill")):
            if not key or len(key) < 2:
                continue
            if base == key:
                score = 1000 + len(key)
            elif base.startswith(key):
                score = 500 + len(key)
            elif key.endswith(base):
                score = 400 + len(base)
            elif key in base:
                score = 200 + len(key)
            elif len(base) >= 4 and base in key:
                score = 100 + len(base)
            else:
                continue
            if r.get("stages"):
                if stage is None or stage not in r["stages"]:
                    continue
                score += 2000
            if score > best_score:
                best, best_score = r, score
            break
    return best["to"] if best else None
