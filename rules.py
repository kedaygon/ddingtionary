import json
import re
import time

ELEMENTS = ["용융", "응결", "전도", "기류", "회절", "인멸"]
SKILL_SCOPES = [
    "일반 공격", "강공격", "공중 공격", "회피 반격", "공명 스킬", "공명 해방",
    "변주 스킬", "반주 스킬", "에코 어빌리티", "조화도 파괴", "협동 공격",
]

SCOPE_HINTS = [
    "효과 피해", "받는 피해", "협동 공격", "추가 피해", "고정 피해",
]

STAT_TERMS = [
    ("치명 피해", "crit_dmg"),
    ("치명 확률", "crit_rate"),
    ("크리티컬 피해", "crit_dmg"),
    ("크리티컬", "crit_rate"),
    ("피해 저항", "res_shred"),
    ("저항", "res_shred"),
    ("치료 효과 보너스", "heal_bonus"),
    ("치료 효과", "heal_bonus"),
    ("피해 보너스", "dmg_bonus"),
    ("피해 배율", "skill_multiplier"),
    ("최종 피해", "dmg_boost"),
    ("전체 피해", "dmg_boost"),
    ("받는 피해", "damage_taken"),
    ("조화도 파괴 증폭", "stagger_amp"),
    ("공명 효율", "energy_regen"),
    ("협주 에너지", "energy_regen"),
    ("공명 에너지", "energy_regen"),
    ("방어력 무시", "def_ignore"),
    ("공격력", "atk"),
    ("방어력", "def"),
    ("HP 최대치", "hp"),
    ("HP", "hp"),
    ("생명력", "hp"),
    ("피해", "dmg_boost"),
]

HOLDER_PATTERNS = [
    (r"다음 등장 캐릭터", "next_entrant"),
    (r"파티 내[^,.]{0,20}?등장 캐릭터", "on_field"),
    (r"근처 파티 내[^,.]{0,20}?캐릭터", "party"),
    (r"파티 내[^,.]{0,20}?캐릭터", "party"),
    (r"파티[^,.]{0,14}?캐릭터", "party"),
    (r"등장 캐릭터", "on_field"),
    (r"자신", "self"),
]

_NUM = r"(\d+(?:\.\d+)?)"

RE_CHANGE = re.compile(
    r"(?P<subject>[^,.·\n]{0,40}?)"
    r"(?P<stat>치명 피해|치명 확률|크리티컬 피해|크리티컬|피해 저항|저항|치료 효과 보너스|치료 효과|피해 보너스|피해 배율|"
    r"최종 피해|전체 피해|받는 피해|조화도 파괴 증폭|공명 효율|협주 에너지|공명 에너지|"
    r"방어력 무시|공격력|방어력|HP 최대치|HP|생명력|피해)"
    r"(?:가|이|를|을)?\s*(?:\d+(?:\.\d+)?\s*초마다\s*)?"
    + _NUM + r"(?P<unit>%|pt)?\s*"
    r"(?P<verb>증가|부스트|상승|감소)"
)

RE_PER_UNIT = re.compile(
    r"(?P<src>HP 최대치|공격력|방어력)\s*" + _NUM + r"\s*(?:pt)?\s*당[^,.]{0,40}?"
    r"(?P<stat>[가-힣 ]{0,14}?(?:피해 보너스|공격력|방어력|치명 피해|치명 확률))"
    r"(?:를|을|가|이)?\s*" + _NUM + r"(?P<unit>%|pt)?\s*(?:증가|상승)"
)
RE_CAP = re.compile(r"최대\s*" + _NUM + r"(%|pt)?\s*(?:까지)?")
RE_DURATION = re.compile(_NUM + r"\s*초(?:간|\s*동안)?\s*(?:지속|유지)")
RE_STACKS = re.compile(r"최대\s*" + _NUM + r"\s*스택|" + _NUM + r"\s*스택\s*(?:까지\s*)?중첩")
RE_STACK_MAX = re.compile(r"(?:스택\s*)?최대치는\s*" + _NUM + r"\s*스택")
RE_INTERVAL = re.compile(_NUM + r"\s*초마다\s*1?회?")
RE_SWAP_END = re.compile(r"다른 캐릭터로 전환하[면며][^.]{0,30}(?:종료|해제|사라)")
RE_REFRESH = re.compile(r"(?:지속 시간이?\s*)?(?:리셋|초기화|갱신)")

NEGATIVE_VERBS = {"감소"}

RE_DEF_IGNORE = re.compile(r"방어력(?:을|를)?\s*" + _NUM + r"\s*%\s*무시")
RE_DEF_IGNORE2 = re.compile(r"목표의\s*" + _NUM + r"\s*%\s*(?:의\s*)?방어력(?=(?:을|를|과|와)?[^.,]{0,24}무시)")
RE_RES_IGNORE = re.compile(_NUM + r"\s*%\s*의?\s*(용융|응결|전도|기류|회절|인멸)\s*(?:속성\s*)?(?:피해\s*)?저항(?:을|를)?\s*무시|"
                           r"(?P<e2>용융|응결|전도|기류|회절|인멸)\s*(?:속성\s*)?저항(?:을|를)?\s*(?P<v2>\d+(?:\.\d+)?)\s*%\s*무시")
RE_COMPOUND = re.compile(r"(공격력|방어력|HP)(?:과|와)\s*([^,.]{1,24}?)(?:가|이|를|을)\s*" + _NUM +
                         r"\s*%\s*(?:증가|상승)")


class _Pos:
    def __init__(self, start, val):
        self._s = start
        self._v = val

    def start(self):
        return self._s

    def group(self, _i):
        return self._v

CONDITION_MARKERS = ("경우", "시,", "시 ", "상태에", "할 때", "발동 시", "발동 후", "후,")

RE_SEP = re.compile(r"다\.\s*|\.\s+|[시후]\s*[,，]\s*|[시후]\s+(?=\D)|경우\s*,\s*|때\s*,\s*|"
                    r"동안\s*,\s*|마다\s*,\s*|되고\s*,?\s*|되며\s*,?\s*|하고\s*,?\s*|하며\s*,?\s*|"
                    r"시키고\s*,?\s*|시키며\s*,?\s*")
LOCAL_HOLDERS = [
    (r"다음(?:에|번)?\s*(?:변주 스킬로\s*)?등장(?:하는)?\s*(?:캐릭터|공명자)", "next_entrant"),
    (r"파티 전체", "party"),
    (r"파티 내[^,.]{0,20}?등장 캐릭터", "on_field"),
    (r"(?:근처\s*)?파티(?: 내)?[^,.]{0,14}?캐릭터", "party"),
    (r"파티원", "party"),
    (r"자신|현재 캐릭터", "self"),
]


def segment(line, pos):
    head = line[:pos]
    last = 0
    for m in RE_SEP.finditer(head):
        last = m.end()
    return head[last:]


RE_COND_HOLDER = re.compile(r"^\s*(?:일|인|이\s*아닐|가\s*아닐|이\s*아닌|가\s*아닌|이\s*될|가\s*될)")
RE_NAMED_SELF = re.compile(r"(?<![가-힣])([가-힣]{2,6})(?:의|가\s*입히는|이\s*입히는)\s*$")
NOT_SELF = ("목표", "적의", "대상", "해당", "모든", "캐릭터", "공명자", "파티원", "등장", "다음",
            "현재", "효과", "스킬", "피해", "주변", "범위", "근처", "상태", "자신")


def _holder_hits(text, patterns):
    best = None
    for pattern, holder in patterns:
        for m in re.finditer(pattern, text):
            if holder != "self" and RE_COND_HOLDER.match(text[m.end():m.end() + 6]):
                continue
            if best is None or m.end() > best[0]:
                best = (m.end(), holder)
    return best


def local_holder(line, pos):
    seg = segment(line, pos)
    best = _holder_hits(seg, LOCAL_HOLDERS)
    if best:
        return best[1]
    m = RE_NAMED_SELF.search(seg)
    if m and not any(w in m.group(1) for w in NOT_SELF):
        return "self"
    for m in reversed(list(RE_SELF_DEAL.finditer(seg))):
        if not any(w in m.group(1) for w in NOT_SELF):
            return "self"
        break
    return None


def local_scopes(line, pos):
    seg = _BRACKET.sub("", segment(line, pos))
    for pattern, _h in LOCAL_HOLDERS:
        seg = re.sub(pattern, " ", seg)
    found = []
    for sc in sorted(SKILL_SCOPES, key=len, reverse=True):
        for m in re.finditer(re.escape(sc), seg):
            if not any(a <= m.start() < b for a, b, _s in found):
                found.append((m.start(), m.end(), sc))
    found.sort()
    keep = [True] * len(found)
    nxt = None
    for i in range(len(found) - 1, -1, -1):
        a, b, sc = found[i]
        end = found[i + 1][0] if i + 1 < len(found) else len(seg)
        gap = seg[b:end]
        if i + 1 < len(found) and RE_JOIN.match(gap):
            keep[i] = nxt
        else:
            keep[i] = not RE_TRIGGER_GAP.search(gap)
        nxt = keep[i]
    out = []
    for (_a, _b, sc), k in zip(found, keep):
        if k and sc not in out:
            out.append(sc)
    return out


RE_TAKEN_SUBJ = re.compile(r"받는\s*[가-힣 ·「」]{0,16}$")
RE_SELF_DEAL = re.compile(r"(?<![가-힣])([가-힣]{2,6})(?:가|이)\s*(?:직접\s*)?입히는")
RE_JOIN = re.compile(r"^\s*(?:을|를|과|와|,|및|、|이나|나)?\s*(?:또는|혹은|및)?\s*$")
RE_TRIGGER_GAP = re.compile(r"발동|사용|시전|명중|적중|피해를\s*입|적립|진입|획득|소모|(?:시|후)\s*[,，]?\s*$")


PREFIX_HOLDERS = LOCAL_HOLDERS[:-1] + [
    (r"자신(?!의\s*(?:공명 효율|HP|공격력|방어력|크리티컬))|현재 캐릭터", "self")]


def prefix_holder(line, pos, fallback):
    best = _holder_hits(line[:pos], PREFIX_HOLDERS)
    if best:
        return best[1]
    return fallback


def _holder(text):
    for pattern, holder in HOLDER_PATTERNS:
        for m in re.finditer(pattern, text):
            if holder != "self" and RE_COND_HOLDER.match(text[m.end():m.end() + 6]):
                continue
            return holder
    return "self"


ELEMENT_WINDOW = 14


_BRACKET = re.compile(r"[「」『』\[\]]")


def _scopes(subject, stat_word):
    blob = _BRACKET.sub("", (subject or "") + " " + (stat_word or ""))
    blob = re.sub(r"(효과)의\s", r"\1 ", blob)
    blob = re.sub(r"\s+", " ", blob).strip()
    blob = blob.replace("효과 최종 피해", "효과 피해")
    near = _BRACKET.sub("", (subject or "")[-ELEMENT_WINDOW:] + " " + (stat_word or ""))
    near = re.sub(r"\s+", " ", near).strip()
    element = next((e for e in ELEMENTS if e in near), None)
    skill = None
    for sc in SKILL_SCOPES:
        if sc in blob:
            skill = sc
            break
    if skill is None:
        for hint in SCOPE_HINTS:
            if hint in blob:
                skill = hint
                break
    return element, skill


def _condition(line):
    for marker in CONDITION_MARKERS:
        idx = line.find(marker)
        if 0 < idx < len(line) - 2:
            head = line[:idx + len(marker)].strip()
            if 4 < len(head) < 90:
                return head
    return None


def _iter_lines(text):
    lead = ""
    for raw in (text or "").split("\n"):
        stripped = raw.strip()
        if not stripped:
            lead = ""
            continue
        is_bullet = stripped[0] in "·-•"
        line = stripped.lstrip("·-• ").strip()
        if not line:
            continue
        if is_bullet:
            yield line, lead
        else:
            yield line, ""
            lead = line


def _local_duration(line, pos):
    ends = [m.end() for m in re.finditer(r"다\.|\.\s", line)]
    start = max([e for e in ends if e <= pos] or [0])
    stop = min([e for e in ends if e > pos] or [len(line)])
    m = RE_DURATION.search(line, pos, stop) or RE_DURATION.search(line, start, stop)
    return float(m.group(1)) if m else None


def extract_line(line, sid, stype, lead=""):
    items = _extract_line(line, sid, stype, lead)
    for it in items:
        if it.get("pos") is not None:
            d = _local_duration(line, it["pos"])
            if d is not None:
                it["duration"] = d
    return items


def _extract_line(line, sid, stype, lead=""):
    out = []
    duration = None
    m = RE_DURATION.search(line) or (RE_DURATION.search(lead) if lead else None)
    if m:
        duration = float(m.group(1))

    stacks = None
    m = RE_STACK_MAX.search(line) or RE_STACKS.search(line)
    if m:
        for g in m.groups():
            if g:
                stacks = int(float(g))
                break

    interval = None
    m = RE_INTERVAL.search(line)
    if m:
        interval = float(m.group(1))

    ends_on_swap = bool(RE_SWAP_END.search(line)) or bool(
        lead and RE_SWAP_END.search(lead))
    refresh = bool(RE_REFRESH.search(line))
    holder = _holder(line)
    if holder == "self" and lead:
        holder = _holder(lead)
    condition = _condition(line) or (_condition(lead) if lead else None)

    for m in RE_PER_UNIT.finditer(line):
        stat_word = m.group("stat").strip()
        stat = next((code for term, code in STAT_TERMS if term in stat_word), None)
        if not stat:
            continue
        cap = None
        tail = line[m.end():m.end() + 40]
        cm = RE_CAP.search(tail)
        if cm:
            cap = float(cm.group(1))
        element, skill = _scopes(line[:m.start()] + stat_word, stat_word)
        per_unit = {
            "source_stat": "hp" if "HP" in m.group("src") else
                           ("atk" if "공격력" in m.group("src") else "def"),
            "per_amount": float(m.group(2)),
            "per_value": float(m.group(4)),
            "cap": cap,
        }
        out.append({
            "label": (stat_word + " (파생)")[:120],
            "pos": m.start(),
            "scope_list": local_scopes(line, m.start()),
            "stack_local": False,
            "skill_id": sid,
            "skill_type": stype,
            "holder": holder,
            "stat": stat,
            "scope_element": element,
            "scope_skill": skill,
            "value": cap if cap is not None else float(m.group(4)),
            "unit": "pct" if (m.group("unit") or "%") == "%" else "flat",
            "derivation": "per_unit",
            "per_unit": per_unit,
            "max_stacks": stacks,
            "per_stack_value": None,
            "stack_gain_interval": interval,
            "duration": duration,
            "refresh_on_reapply": refresh,
            "ends_on_swap": ends_on_swap,
            "condition_text": condition,
            "source_line": line,
        })

    if out:
        return out

    ignores = [(m.start(), float(m.group(1))) for m in RE_DEF_IGNORE.finditer(line)]
    ignores += [(m.start(), float(m.group(1))) for m in RE_DEF_IGNORE2.finditer(line)]
    for m in RE_RES_IGNORE.finditer(line):
        scopes = local_scopes(line, m.start())
        out.append({
            "label": "저항 무시", "skill_id": sid, "skill_type": stype,
            "pos": m.start(), "scope_list": scopes, "stack_local": True,
            "holder": local_holder(line, m.start()) or prefix_holder(line, m.start(), holder),
            "stat": "res_shred", "scope_element": m.group(2) or m.group("e2"),
            "scope_skill": scopes[0] if scopes else None,
            "value": float(m.group(1) or m.group("v2")),
            "unit": "pct", "derivation": "direct", "per_unit": None, "max_stacks": stacks,
            "per_stack_value": None,
            "stack_gain_interval": interval, "duration": duration,
            "refresh_on_reapply": refresh, "ends_on_swap": ends_on_swap,
            "condition_text": condition, "source_line": line,
        })
    for start, val in ignores:
        m = _Pos(start, val)
        element, skill = _scopes(line[:m.start()], "방어력")
        scopes = local_scopes(line, m.start())
        out.append({
            "label": "방어력 무시", "skill_id": sid, "skill_type": stype,
            "pos": m.start(), "scope_list": scopes, "stack_local": True,
            "holder": local_holder(line, m.start()) or prefix_holder(line, m.start(), holder),
            "stat": "def_ignore", "scope_element": element,
            "scope_skill": scopes[0] if scopes else None, "value": float(m.group(1)), "unit": "pct",
            "derivation": "direct", "per_unit": None, "max_stacks": stacks,
            "per_stack_value": float(m.group(1)) if stacks else None,
            "stack_gain_interval": interval, "duration": duration,
            "refresh_on_reapply": refresh, "ends_on_swap": ends_on_swap,
            "condition_text": condition, "source_line": line,
        })

    for m in RE_CHANGE.finditer(line):
        if RE_PER_UNIT.search(line) and "당" in line[:m.start()][-12:]:
            continue
        stat_word = m.group("stat")
        subject = m.group("subject")
        stat = next((code for term, code in STAT_TERMS if term == stat_word), None)
        if not stat:
            continue
        if stat == "hp" and m.group("verb") in NEGATIVE_VERBS:
            continue
        if stat == "hp" and ("계승" in (subject or "") or "분신" in (subject or "")):
            continue
        value = float(m.group(3))
        unit = "pct" if (m.group("unit") or "%") == "%" else "flat"
        if m.group("verb") == "감소":
            if stat == "damage_taken":
                value = -value
            elif stat != "res_shred":
                continue
        elif stat == "res_shred":
            continue
        if stat == "dmg_boost" and stat_word in ("피해", "전체 피해") \
                and m.group("verb") != "부스트":
            stat = "dmg_bonus"
        if stat in ("dmg_bonus", "dmg_boost") and RE_TAKEN_SUBJ.search(subject or ""):
            stat = "damage_taken"
        element, skill = _scopes(subject, stat_word)
        pos = m.start("stat")
        scopes = local_scopes(line, pos)
        if stat in ("atk", "hp", "def"):
            scopes = []
            skill = None
        skill = scopes[0] if scopes else (skill if skill in SCOPE_HINTS else None)
        seg = segment(line, pos)
        near_after = line[m.end():m.end() + 24]
        label = re.sub(r"\s+", " ",
                       (subject or "").strip() + " " + stat_word).strip()[-60:]
        out.append({
            "label": label,
            "pos": pos,
            "scope_list": scopes,
            "stack_local": ("스택" in seg) or ("스택" in near_after),
            "skill_id": sid,
            "skill_type": stype,
            "holder": ("self" if stat == "damage_taken" and "로부터" in seg else
                       local_holder(line, pos) or prefix_holder(line, pos, holder)),
            "stat": stat,
            "scope_element": element,
            "scope_skill": skill,
            "value": value,
            "unit": unit,
            "derivation": "direct",
            "per_unit": None,
            "max_stacks": stacks,
            "per_stack_value": value if stacks else None,
            "stack_gain_interval": interval,
            "duration": duration,
            "refresh_on_reapply": refresh,
            "ends_on_swap": ends_on_swap,
            "condition_text": condition,
            "source_line": line,
        })
    taken = {o["pos"] for o in out}
    for m in RE_COMPOUND.finditer(line):
        pos = m.start(1)
        if pos in taken:
            continue
        rest = m.group(2)
        if not any(t in rest for t in ("피해", "크리티컬", "공격력", "방어력", "HP")):
            continue
        tail = [o for o in out if m.start(2) <= o["pos"] < m.end()]
        if not tail:
            continue
        like = tail[0]
        stat = {"공격력": "atk", "방어력": "def", "HP": "hp"}[m.group(1)]
        out.append(dict(like, label=m.group(1), pos=pos, stat=stat,
                        scope_list=[], scope_skill=None, scope_element=None,
                        value=float(m.group(3)), unit="pct"))
    out.sort(key=lambda o: o["pos"])
    return out


CANDIDATE = re.compile(r"(증가|부스트|상승|감소|무시)")


def extract(skills):
    found = []
    unmatched = []
    for sid, stype, name, text in skills:
        for line, lead in _iter_lines(text):
            hits = extract_line(line, sid, stype, lead)
            if hits:
                found.extend(hits)
            elif CANDIDATE.search(line):
                unmatched.append((sid, name, line))
    return found, unmatched


def to_rows(character_id, items):
    ts = int(time.time())
    rows = []
    for it in items:
        rows.append((
            character_id,
            it["skill_id"],
            it["skill_type"],
            it["label"],
            it["holder"],
            it["stat"],
            it["scope_element"],
            it["scope_skill"],
            it["value"],
            it["unit"],
            it["derivation"],
            json.dumps(it["per_unit"], ensure_ascii=False) if it["per_unit"] else None,
            it["max_stacks"],
            it["per_stack_value"],
            it["stack_gain_interval"],
            it["duration"],
            1 if it["refresh_on_reapply"] else 0,
            1 if it["ends_on_swap"] else 0,
            it["condition_text"],
            it["source_line"],
            "rules",
            ts,
        ))
    return rows
