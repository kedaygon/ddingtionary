import re

import modes

NORMAL = "일반 공격"
HEAVY = "강공격"
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
UNKNOWN = "판정 미기재"

CATS = [NORMAL, HEAVY, SKILL, BURST, INTRO, OUTRO, AIR, DODGE, ECHO,
        HARMONY, STAGGER, COOP, HACK]

TYPE_DEFAULT = {1: NORMAL, 2: SKILL, 3: BURST, 5: INTRO, 11: OUTRO, 12: STAGGER}

GENERIC_NAMES = {"스킬", "추가", "지속", "공격", "피해", "기본"}

SKIP_ATTR = ("증가(", "증가량", "증폭", "치료", "감소량", "회복량", "실드",
             "스태미나", "쿨타임", "협주 에너지", "공명 에너지", "에너지 회복", "지속 시간", "소모", "속도",
             "시간", "범위", "HP 회복", "피해 감소", "팬텀 HP", "증가하는 공격", "배율 상승")


def _flex(s):
    return r"\s*".join(re.escape(p) for p in s.split())


_CAT_RE = "|".join(_flex(c) for c in sorted(CATS, key=len, reverse=True))
RE_CAT = re.compile(_CAT_RE)

RE_APPLY = re.compile(
    r"(?:해당\s*)?피해는\s*(?P<t>(?:%s)(?:\s*피해)?(?:\s*/\s*(?:%s)(?:\s*피해)?)*)"
    r"\s*(?:피해)?로\s*(?:적용|간주)" % (_CAT_RE, _CAT_RE))

RE_REPLACE = re.compile(
    r"(?P<src>%s)\s*(?:은|는|이|가)\s*(?P<dst>[^.。,\n]{2,48}?)\s*(?:으)?로\s*대체"
    % _CAT_RE)

RE_STAGE = re.compile(r"(\d+)\s*단")
RE_TAIL = re.compile(r"\s*(?:피해량|피해|배율|치료량)\s*$")
RE_WS = re.compile(r"\s+")
RE_INPUT = re.compile(r"^(?:짧게|길게|누르|떼|공중에서)")
RE_BRACKET = re.compile(r"「([^」]{2,20})」")
RE_BOUNDARY = re.compile(r"[.。]\s*|(?<=다)\s+(?=[가-힣「])")


def norm(s):
    return RE_WS.sub(" ", (s or "").replace(" ", " ")).strip()


def squash(s):
    return RE_WS.sub("", s or "")


def canon_cat(s):
    k = squash(s)
    for c in CATS:
        if squash(c) == k:
            return c
    return None


def base_of(attr):
    a = re.sub(r"\([^)]*\)", "", norm(attr))
    return RE_TAIL.sub("", norm(a))


def stage_of(base):
    nums = RE_STAGE.findall(base)
    return int(nums[-1]) if nums else None


def name_of(base):
    return norm(RE_STAGE.sub("", base))


def keyword_cat(base):
    hits = [(m.start(), m.group(0)) for m in RE_CAT.finditer(base)]
    if not hits:
        return None
    return canon_cat(hits[-1][1])


def _sentences(text):
    out = []
    for raw in (text or "").split("\n"):
        line = norm(raw).lstrip("·-• ").strip()
        if line:
            out.append(line)
    return out


def _mentions(line, names):
    found = []
    flat = squash(line)
    for nm in names:
        key = squash(nm)
        if len(key) < 2:
            continue
        start = 0
        while True:
            i = flat.find(key, start)
            if i < 0:
                break
            found.append((i, i + len(key), nm))
            start = i + 1
    return found


def _stages_near(head, name):
    flat = squash(head)
    key = squash(name)
    out = set()
    if key:
        for m in re.finditer(re.escape(key) + r"((?:\d+단?,?)+)", flat):
            for n in re.findall(r"\d+", m.group(1)):
                out.add(int(n))
    tail = re.search(r"((?:\d+단?,)*\d+단)$", flat)
    if tail and not out:
        for n in re.findall(r"\d+", tail.group(1)):
            out.add(int(n))
    return sorted(out) or None


def _qualifier(head, subject):
    flat = squash(head)
    key = squash(subject)
    if not key or canon_cat(subject):
        return None
    i = flat.rfind(key)
    if i <= 0:
        return None
    m = re.search(r"(%s)·?$" % "|".join(squash(c) for c in sorted(CATS, key=len, reverse=True)),
                  flat[:i])
    return canon_cat(m.group(1)) if m else None


def _prefix(nm):
    m = re.match(r"^(%s)\s*·\s*(.+)$" % _CAT_RE, nm)
    return canon_cat(m.group(1)) if m else None


class Classifier:
    def __init__(self, con, cid, mode=None):
        self.con = con
        self.cid = cid
        self.mode = mode
        self.modes = modes.character_modes(con, cid)
        rows = con.execute(
            "SELECT id, skill_type, name, describe_text FROM skills "
            "WHERE character_id=?", (cid,)).fetchall()
        self.skills = rows
        self.text = "\n".join(t or "" for _i, _s, _n, t in rows)
        self.names = self._attr_names()
        self.header_cat = self._headers()
        self.intro_cat = self._introduced()
        self.apply_rules = self._apply_rules()
        self.replace_rules = self._replace_rules()
        self._coop = None

    def _attr_names(self):
        names = set()
        self.leads = set()
        for sid, st, sn, _t in self.skills:
            for (a,) in self.con.execute(
                    "SELECT sc.attribute_name FROM skill_scalings sc "
                    "JOIN skills s ON s.skill_level_group_id=sc.skill_level_group_id "
                    "WHERE s.id=?", (sid,)):
                nm = name_of(base_of(a))
                if nm and nm not in GENERIC_NAMES and not any(k in nm for k in SKIP_ATTR):
                    names.add(nm)
                    if "·" in nm:
                        tail = norm(nm.split("·")[-1])
                        if len(squash(tail)) >= 3 and not canon_cat(tail):
                            names.add(tail)
                        lead = norm(nm.split("·")[0])
                        if (len(squash(lead)) >= 3 and not canon_cat(lead)
                                and lead not in GENERIC_NAMES):
                            self.leads.add(lead)
            if sn:
                names.add(norm(sn))
        return sorted(names, key=len, reverse=True)

    def _headers(self):
        out = {}
        for _sid, _st, _sn, t in self.skills:
            for b in modes.parse_blocks(t):
                nm = norm(b["name"] or "")
                if not nm:
                    continue
                m = re.match(r"^(%s)\s*·\s*(.+)$" % _CAT_RE, nm)
                if m:
                    out[norm(m.group(2))] = canon_cat(m.group(1))
                    out[nm] = canon_cat(m.group(1))
        return out

    def _introduced(self):
        out = {}
        stop = re.compile(r"(?:으로|로|을|를|이|가|은|는|의|와|과|에|:)(?=\s|$|[,.:])|[,.:。]")
        for line in _sentences(self.text):
            for m in RE_CAT.finditer(line):
                cat = canon_cat(m.group(0))
                rest = line[m.end():]
                rest = re.sub(r"^\s*·?\s*", "", rest)
                if not rest or re.match(r"^(?:을|를|이|가|은|는|의|에|로|으로|피해|과|와)", rest):
                    continue
                cut = stop.search(rest)
                tail = rest[:cut.start()] if cut else rest[:30]
                inner = RE_CAT.search(tail)
                if inner:
                    tail = tail[:inner.start()]
                tail = norm(tail).strip("· ")
                if len(squash(tail)) < 2 or len(tail) > 30 or canon_cat(tail):
                    continue
                if RE_INPUT.match(squash(tail)):
                    continue
                out.setdefault(tail, cat)
        return out

    def _apply_rules(self):
        rules = []
        for sid, st, sn, t in self.skills:
            for b in modes.parse_blocks(t):
                header = norm(b["name"] or "")
                bname = header or norm(sn or "")
                for line in b["lines"]:
                    line = norm(line)
                    pos = 0
                    for m in RE_APPLY.finditer(line):
                        head = line[pos:m.start()]
                        pos = m.end()
                        targets = [canon_cat(re.sub(r"\s*피해$", "", x))
                                   for x in re.split(r"\s*/\s*", m.group("t"))]
                        targets = [x for x in targets if x]
                        if not targets:
                            continue
                        mode_names = [n for n in self.modes if n in head]
                        mode_names.sort(key=lambda n: head.find(n))
                        subjects = self._subjects(head, line[:m.start()])
                        if subjects:
                            items = [(sj, _stages_near(head, sj), not canon_cat(sj))
                                     for sj in subjects]
                            for bm in RE_BRACKET.finditer(head):
                                bn = norm(bm.group(1))
                                if bn not in subjects and not canon_cat(bn):
                                    items.append((bn, [], None))
                        else:
                            stages = _stages_near(head, "")
                            explicit = bool(header) and not canon_cat(header)
                            items = [(bname, stages, explicit)]
                        if len(targets) > 1 and len(mode_names) == len(targets):
                            pairs = list(zip(mode_names, targets))
                        elif mode_names:
                            pairs = [(mode_names[0], targets[0])]
                        else:
                            pairs = [(None, targets[0])]
                        for sj, stg, exp in items:
                            qual = _qualifier(head, sj)
                            for md, tg in pairs:
                                rules.append({"subject": sj, "block": bname,
                                              "qual": qual,
                                              "skill_id": sid, "to": tg,
                                              "mode": md, "stages": stg,
                                              "explicit": exp})
        return rules

    def _subjects(self, head, full_head):
        cands = self._filter(head, _mentions(head, self.names))
        if not cands:
            cands = self._filter(full_head, _mentions(full_head, self.names))
            if not cands:
                return []
        flat = squash(head)
        pool = cands + self._filter(head, _mentions(head, sorted(self.leads - set(self.names))))
        near = [c for c in pool if not canon_cat(c[2])
                and re.fullmatch(r"(?:으로|로|의|이|가)?(?:입히는|가하는|주는|인한)?", flat[c[1]:])]
        if near:
            return [max(near, key=lambda c: c[1] - c[0])[2]]
        cut = max(flat.rfind("다."), flat.rfind("."))
        cands = [c for c in cands if c[0] > cut] or cands
        keep = []
        for a, b, nm in sorted(cands, key=lambda x: -(x[1] - x[0])):
            if any(a >= a2 and b <= b2 for a2, b2, _n in keep):
                continue
            keep.append((a, b, nm))
        keep.sort(key=lambda x: x[0])
        specific = [k for k in keep if not canon_cat(k[2])]
        if specific:
            last = specific[-1]
            group = [last]
            for k in reversed(specific[:-1]):
                between = flat[k[1]:group[0][0]]
                if re.fullmatch(r"(?:\d+단)?[,、]?(?:혹은|또는|및|와|과)?", between):
                    group.insert(0, k)
                else:
                    break
            return [g[2] for g in group]
        return [keep[-1][2]]

    def _filter(self, text, cands):
        flat = squash(text)
        out = []
        for a, b, nm in cands:
            if canon_cat(nm):
                after = flat[b:b + 8]
                if re.match(r"\d+단?", after):
                    out.append((a, b, nm))
                    continue
                if re.match(r"(?:을|를)?(?:짧게|길게)?누르", after):
                    continue
                if re.match(r"(?:의|이|가)?(?:피해|배율)", after) or a == 0:
                    out.append((a, b, nm))
                continue
            out.append((a, b, nm))
        return out

    def _replace_rules(self):
        rules = []
        for line in _sentences(self.text):
            for m in RE_REPLACE.finditer(line):
                src = canon_cat(m.group("src"))
                dst = norm(m.group("dst"))
                pre = re.match(r"^(%s)\s*·?\s*(.*)$" % _CAT_RE, dst)
                if pre and pre.group(2).strip():
                    cat = canon_cat(pre.group(1))
                    rules.append({"subject": norm(pre.group(2)), "to": cat,
                                  "full": dst})
                    rules.append({"subject": dst, "to": cat, "full": dst})
                elif not canon_cat(dst):
                    rules.append({"subject": dst, "to": src, "full": dst})
        return rules

    def _direct(self, nm):
        key = squash(nm)
        if len(key) < 2 or nm in GENERIC_NAMES or RE_INPUT.match(key):
            return None
        flat = squash(self.text)
        for c in sorted(CATS, key=len, reverse=True):
            ck = squash(c)
            for sep in ("·", ""):
                if (ck + sep + key) in flat:
                    return c
        return None

    def natural(self, attr, skill_type):
        base = base_of(attr)
        nm = name_of(base)
        k = keyword_cat(nm)
        if k:
            return k, "이름"
        d0 = self._direct(nm)
        if d0:
            return d0, "원문"
        for key, cat in self.header_cat.items():
            if squash(nm) == squash(key) or squash(nm).startswith(squash(key)):
                return cat, "제목"
        for key, cat in self.intro_cat.items():
            kq = squash(key)
            if len(kq) >= 3 and (squash(nm) == kq or squash(nm).startswith(kq)):
                return cat, "원문"
        for r in self.replace_rules:
            kq = squash(r["subject"])
            if len(kq) >= 3 and (squash(nm) == kq or squash(nm).startswith(kq)):
                return r["to"], "대체"
        d = TYPE_DEFAULT.get(skill_type)
        if d:
            return d, "스킬 종류"
        return UNKNOWN, "근거 없음"

    def resolve(self, attr, skill_id):
        base = base_of(attr)
        nm = name_of(base)
        st = stage_of(base)
        best = None
        best_score = -1
        for r in self.apply_rules:
            if r["mode"] and r["mode"] != self.mode:
                continue
            subj = squash(r["subject"])
            key = "" if nm in GENERIC_NAMES else squash(nm)
            if not subj:
                continue
            if key == subj:
                score = 100
            elif key.startswith(subj) and len(subj) >= 2:
                score = 60
            elif subj.startswith(key) and len(key) >= 4 and not canon_cat(nm) \
                    and not subj[len(key):].startswith("·"):
                score = 50
            elif subj.endswith(key) and len(key) >= 4:
                score = 40
            elif key.endswith(subj) and len(subj) >= 3:
                score = 45
            elif len(subj) >= 2 and re.search(r"(?:^|\s)" + re.escape(norm(r["subject"])) + r"$", nm):
                score = 42
            elif not key and r["skill_id"] == skill_id and not self._mentioned(r) \
                    and self._rules_in(skill_id) <= 1:
                score = 30
            else:
                continue
            if r["explicit"] is None:
                rest = key[len(subj):] if key.startswith(subj) else None
                if not rest or rest.startswith("·") or RE_CAT.search(rest):
                    continue
            q = r.get("qual")
            if q:
                pre = _prefix(nm)
                if pre and pre != q:
                    continue
                if pre == q:
                    score += 150
                elif score < 100:
                    continue
            if not r["explicit"]:
                if r["skill_id"] != skill_id:
                    continue
                score -= 20
            elif r["skill_id"] == skill_id:
                score += 5
            if r["stages"]:
                if st is None or st not in r["stages"]:
                    continue
                score += 200
            score += len(subj) / 100.0
            if score > best_score:
                best, best_score = r, score
        return best

    def is_coop(self, attr):
        if "협동" in attr:
            return True
        nm = name_of(base_of(attr))
        k = squash(nm)
        if (len(k) < 2 or nm in GENERIC_NAMES or canon_cat(nm)
                or keyword_cat(nm)):
            return False
        if self._coop is None:
            self._coop = []
            for line in _sentences(self.text):
                for x in re.split(r"[,，.]", line):
                    f = squash(x)
                    i = f.find("협동공격")
                    if i >= 0 and "없다" not in f:
                        self._coop.append(f[max(0, i - 30):i + 16])
        return any(k in w for w in self._coop)

    def _rules_in(self, skill_id):
        return len({(r["subject"], r["to"]) for r in self.apply_rules
                    if r["skill_id"] == skill_id})

    def _mentioned(self, r):
        return squash(r["subject"]) != squash(r["block"])

    def classify(self, attr, skill_type, skill_id):
        nat, why = self.natural(attr, skill_type)
        r = self.resolve(attr, skill_id)
        if r:
            return r["to"], nat, True, "원문 '해당 피해는'"
        return nat, nat, False, why
