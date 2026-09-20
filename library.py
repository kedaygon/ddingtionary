import json
import os
import re

import importer
import parser as rich
import textmap

LIB_VERSION = "3"
TEXT_PATH = "Textmaps/ko/multi_text/MultiText.json"
PATHS = [
    "BinData/favor/favorroleinfo.json",
    "BinData/favor/favorword.json",
    "BinData/favor/favorstory.json",
    "BinData/favor/favorgoods.json",
    "BinData/item/iteminfo.json",
    "BinData/role_level/rolebreach.json",
    "BinData/role_level/rolelevelconsume.json",
    "BinData/role/roleexpitem.json",
    "BinData/weapon/weaponbreach.json",
    "BinData/weapon/weaponlevel.json",
    "BinData/weapon/weaponexpitem.json",
    "BinData/tower/towerconfig.json",
    "BinData/tower/towerbuff.json",
    "BinData/NewTower/newtowerwave.json",
    "BinData/NewTower/newtowerseason.json",
    "BinData/NewTower/newtowerlevel.json",
    "BinData/NewTower/newtowerbuff.json",
    "BinData/NewTower/newtowerbossbuff.json",
    "BinData/NewTower/newtowertag.json",
    "BinData/ShipTower/slashandtowercfg.json",
    "BinData/ShipTower/slashtowerstageinfo.json",
]
BASE_PATHS = [
    "BinData/role/roleinfo.json",
    "BinData/skill/skill.json",
    "BinData/skill/skilllevel.json",
    "BinData/skillTree/skilltree.json",
    "BinData/weapon/weaponconf.json",
    "BinData/monster_Info/monsterinfo.json",
]
CREDIT = 2
ELEMENT_IDS = {1: "응결", 2: "용융", 3: "전도", 4: "기류", 5: "회절", 6: "인멸"}
RE_SPACE = re.compile(r"[ \t]+\n")


def missing(version_dir):
    return [p for p in PATHS + BASE_PATHS if not os.path.isfile(importer.source_path(version_dir, p))]


def fetch(version_dir, progress=None):
    version = os.path.basename(os.path.normpath(version_dir))
    todo = missing(version_dir)
    for i, rel in enumerate(todo, 1):
        label = "%d/%d %s" % (i, len(todo), rel.rsplit("/", 1)[-1])
        if progress:
            progress("fetch", label)
        importer._download("%s/%s/%s" % (importer.RAW_BASE, version, rel),
                           importer.source_path(version_dir, rel), progress=progress, label=label)
    return not missing(version_dir)


def _load(version_dir, rel):
    with open(importer.source_path(version_dir, rel), "r", encoding="utf-8") as f:
        return json.load(f)


def _load_keys(path, keys):
    out = {}
    for e in textmap.iter_entries(path):
        k = e.get("Id")
        if k in keys:
            c = e.get("Content")
            if c:
                out[k] = c
    return out


def clean(s, params=None):
    if not s:
        return ""
    if params:
        s, _m = rich.substitute(s, params)
    s = rich.strip_tags(s)
    s = s.replace("\r\n", "\n")
    s = RE_SPACE.sub("\n", s)
    return s.strip()


def _consume(lst):
    return [[c["Key"], c["Value"]] for c in (lst or []) if c.get("Value")]


def build(version_dir, char_ids):
    src = {rel: _load(version_dir, rel) for rel in PATHS + BASE_PATHS}
    g = lambda name: src[next(p for p in PATHS + BASE_PATHS if p.endswith("/" + name + ".json"))]
    keys = set()

    def want(k):
        if isinstance(k, str) and k:
            keys.add(k)
        return k

    roleinfo = {r["Id"]: r for r in g("roleinfo")}
    profiles = {}
    for r in g("favorroleinfo"):
        rid = r["RoleId"]
        if rid not in char_ids:
            continue
        profiles[rid] = {k: want(r.get(f)) for k, f in (
            ("birthday", "Birthday"), ("sex", "Sex"), ("country", "Country"),
            ("influence", "Influence"), ("info", "Info"), ("talent", "TalentName"),
            ("talent_doc", "TalentDoc"), ("talent_cert", "TalentCertification"),
            ("cv_ko", "CVNameKo"), ("cv_ja", "CVNameJp"), ("cv_en", "CVNameEn"),
            ("cv_zh", "CVNameCn"))}
    voices, stories, goods = {}, {}, {}
    for name, store in (("favorword", voices), ("favorstory", stories), ("favorgoods", goods)):
        for r in sorted(g(name), key=lambda x: (x["RoleId"], x.get("Type", 0), x.get("Sort", 0), x["Id"])):
            if r["RoleId"] not in char_ids:
                continue
            store.setdefault(r["RoleId"], []).append(
                {"type": r.get("Type", 0), "title": want(r["Title"]), "content": want(r["Content"])})

    items = {}
    for r in g("iteminfo"):
        items[r["Id"]] = {"name": want(r["Name"]), "quality": r.get("QualityId") or 1,
                          "use": want(r.get("ObtainedShowDescription")),
                          "access": [want("AccessPath_%d_Description" % a) and a
                                     for a in (r.get("ItemAccess") or [])]}
        for a in r.get("ItemAccess") or []:
            want("AccessPath_%d_Description" % a)
    for r in g("weaponconf"):
        want(r.get("WeaponName"))

    skill = {s["Id"]: s for s in g("skill")}
    levels = {}
    for r in g("skilllevel"):
        levels.setdefault(r["SkillLevelGroupId"], {})[r["SkillId"]] = _consume(r["Consume"])
    trees = {}
    for r in g("skilltree"):
        trees.setdefault(r["NodeGroup"], []).append(r)
    breach = {}
    for r in g("rolebreach"):
        breach.setdefault(r["BreachGroupId"], []).append(
            [r["BreachLevel"], r["MaxLevel"], _consume(r["BreachConsume"])])
    role_exp = {}
    for r in g("rolelevelconsume"):
        role_exp.setdefault(r["ConsumeGroupId"], {})[r["Level"]] = r["ExpCount"]

    roles = {}
    for cid in char_ids:
        ri = roleinfo.get(cid)
        if not ri:
            continue
        skills = []
        tree_stats = []
        inherent = []
        for n in sorted(trees.get(ri.get("SkillTreeGroupId"), []), key=lambda x: x["NodeIndex"]):
            s = skill.get(n.get("SkillId"))
            if n["NodeType"] in (1, 2) and s and s["SkillType"] in (1, 2, 3, 5, 6):
                grp = levels.get(s["SkillLevelGroupId"], {})
                skills.append({"type": s["SkillType"], "name": want(s["SkillName"]),
                               "levels": {str(k): v for k, v in grp.items()}})
            elif n["NodeType"] == 3 and s and n.get("ParentNodes") and s["SkillType"] == 4:
                inherent.append({"name": want(s["SkillName"]), "consume": _consume(n["Consume"])})
            elif n["NodeType"] == 4:
                tree_stats.append({"name": want(n.get("PropertyNodeTitle")),
                                   "consume": _consume(n["Consume"])})
        order = {1: 0, 2: 1, 6: 2, 3: 3, 5: 4}
        skills.sort(key=lambda x: order.get(x["type"], 9))
        roles[cid] = {"exp_group": ri.get("LevelConsumeId"), "max_level": ri.get("MaxLevel", 90),
                      "breach": sorted(breach.get(ri.get("BreachId"), [])),
                      "skills": skills, "inherent": inherent, "stats": tree_stats,
                      "quality": ri.get("QualityId"), "weapon_type": ri.get("WeaponType")}

    wbreach = {}
    for r in g("weaponbreach"):
        wbreach.setdefault(r["BreachId"], []).append(
            [r["Level"], r["LevelLimit"], _consume(r["Consume"]) + ([[CREDIT, r["GoldConsume"]]]
                                                                  if r.get("GoldConsume") else [])])
    wlevel = {}
    for r in g("weaponlevel"):
        wlevel.setdefault(r["LevelId"], {})[r["Level"]] = r["Exp"]
    weapons = {}
    for r in g("weaponconf"):
        if not r.get("IsShow", True) and r.get("QualityId", 0) < 3:
            continue
        weapons[r["ItemId"]] = {"name": want(r["WeaponName"]), "quality": r.get("QualityId"),
                                "type": r.get("WeaponType"), "level_group": r.get("LevelId"),
                                "breach": sorted(wbreach.get(r.get("BreachId"), []))}

    exp_items = {"role": [[r["Id"], r["BasicExp"], 0] for r in g("roleexpitem")],
                 "weapon": [[r["Id"], r["BasicExp"], r.get("Cost", 0)] for r in g("weaponexpitem")]}

    monsters = {}
    for m in g("monsterinfo"):
        monsters[m["Id"]] = [ELEMENT_IDS.get(e) for e in (m.get("ElementIdArray") or [])
                             if ELEMENT_IDS.get(e)]

    def mon(mid):
        return {"id": mid, "name": want("MonsterInfo_%d_Name" % mid),
                "elements": monsters.get(mid, [])}

    tbuff = {r["Id"]: r for r in g("towerbuff")}
    tower = {}
    for r in g("towerconfig"):
        tower.setdefault(r["Season"], []).append({
            "difficulty": r["Difficulty"], "area": r["AreaNum"], "floor": r["Floor"],
            "area_name": want(r.get("AreaName")),
            "recommend": [ELEMENT_IDS.get(e) for e in r.get("RecommendElement") or []
                          if ELEMENT_IDS.get(e)],
            "monsters": [mon(m) for m in r.get("ShowMonsters") or []],
            "buffs": [want(tbuff[b]["Desc"]) for b in r.get("ShowBuffs") or [] if b in tbuff],
            "target": r.get("Target") or []})

    nbuff = {r["Id"]: r for r in g("newtowerbuff")}
    bbuff = {r["Id"]: r for r in g("newtowerbossbuff")}
    tags = {r["Id"]: want(r["Name"]) for r in g("newtowertag")}
    matrix_levels = []
    for r in g("newtowerlevel"):
        matrix_levels.append({"id": r["Id"], "stage": r["Param"], "hard": bool(r["Diff"]),
                              "buffs": [{"name": want(nbuff[b]["Name"]),
                                         "desc": want(nbuff[b]["Desc"]),
                                         "params": nbuff[b].get("DescParam") or []}
                                        for b in r.get("NewTowerBuffs") or [] if b in nbuff],
                              "score": [[x["Key"], x["Value"]] for x in r.get("ScoreLevelRule") or []]})
    waves = []
    for r in g("newtowerwave"):
        waves.append({"level": r["Level"], "round": r["Round"], "wave": r["Wave"],
                      "monster_level": r.get("MonsterLevel"), "name": want(r["Name"]),
                      "desc": want(r.get("Desc")), "element": ELEMENT_IDS.get(r.get("ElementId")),
                      "tags": [tags[t] for t in r.get("TagIdList") or [] if t in tags],
                      "skills": [{"title": want(bbuff[b]["SkillTitle"]),
                                  "desc": want(bbuff[b]["SkillDesc"])}
                                 for b in r.get("ShowBuffIds") or [] if b in bbuff]})
    seasons = [{"name": want(r["Name"]), "start": r.get("StartVersionId"),
                "end": r.get("EndVersionId")} for r in g("newtowerseason")]

    stages = {}
    for r in g("slashtowerstageinfo"):
        stages[(r["InstId"], r.get("SeasonVersion", 0))] = r.get("MonsterId") or []
    def ruin_stage(r, base):
        mons = []
        for inst in r.get("InstIds") or []:
            ms = stages.get((inst, r.get("SeasonVersion", 0))) or stages.get((inst, 0)) or []
            mons.append([mon(m) for m in ms])
        return {"order": r.get("OrderIndex", 0), "endless": bool(r.get("EndLess")), "base": base,
                "title": want(r.get("Title")), "desc": want(r.get("Desc")),
                "teams": mons, "target": r.get("TargetScore") or []}

    cfgs = g("slashandtowercfg")
    base_cfg = {}
    for r in cfgs:
        if r["Season"] == 0:
            base_cfg.setdefault(r.get("OrderIndex", 0), []).append(r)
    ruins = {}
    for season in sorted({r["Season"] for r in cfgs if r["Season"]}):
        out = []
        for order in sorted(base_cfg):
            opts = [r for r in base_cfg[order] if r.get("SeasonVersion", 0) <= season]
            if opts:
                out.append(ruin_stage(max(opts, key=lambda r: r.get("SeasonVersion", 0)), True))
        out += [ruin_stage(r, False) for r in cfgs if r["Season"] == season]
        ruins[season] = out

    for rid in char_ids:
        want("RoleInfo_%d_Name" % rid)
    text = _load_keys(importer.source_path(version_dir, TEXT_PATH), keys)
    t = lambda k, p=None: clean(text.get(k, ""), p)

    for p in profiles.values():
        for k in list(p):
            p[k] = t(p[k])
    for store in (voices, stories, goods):
        for lst in store.values():
            for e in lst:
                e["title"] = t(e["title"])
                e["content"] = t(e["content"])
    for it in items.values():
        it["name"] = t(it["name"])
        it["use"] = t(it["use"])
        it["access"] = [t("AccessPath_%d_Description" % a) for a in it["access"] if a]
        it["access"] = [a for a in it["access"] if a]
    needed = {CREDIT}
    for r in roles.values():
        for s in r["skills"]:
            s["name"] = t(s["name"])
            for v in s["levels"].values():
                needed.update(k for k, _ in v)
        for n in r["inherent"] + r["stats"]:
            n["name"] = t(n["name"])
            needed.update(k for k, _ in n["consume"])
        for b in r["breach"]:
            needed.update(k for k, _ in b[2])
    for w in weapons.values():
        w["name"] = t(w["name"])
        for b in w["breach"]:
            needed.update(k for k, _ in b[2])
    for kind in exp_items.values():
        needed.update(i for i, _e, _c in kind)
    items = {str(k): v for k, v in items.items() if k in needed and v["name"]}

    for season in tower.values():
        for f in season:
            f["area_name"] = t(f["area_name"])
            f["buffs"] = [t(b) for b in f["buffs"]]
            for m in f["monsters"]:
                m["name"] = t(m["name"])
    for lv in matrix_levels:
        for b in lv["buffs"]:
            b["name"] = t(b["name"])
            b["desc"] = t(b["desc"], b.pop("params"))
    for w in waves:
        w["name"] = t(w["name"])
        w["desc"] = t(w["desc"])
        w["tags"] = [t(x) for x in w["tags"]]
        for s in w["skills"]:
            s["title"] = t(s["title"])
            s["desc"] = t(s["desc"])
        w["skills"] = [s for s in w["skills"] if s["title"] and (
            w["name"] in s["desc"] or not s["title"].startswith("위기 대응"))]
    for s in seasons:
        s["name"] = t(s["name"])
    for season in ruins.values():
        season.sort(key=lambda x: x["order"])
        for st in season:
            st["title"] = t(st["title"])
            st["desc"] = t(st["desc"])
            for team in st["teams"]:
                for m in team:
                    m["name"] = t(m["name"])

    return {
        "profiles": {str(k): v for k, v in profiles.items()},
        "voices": {str(k): v for k, v in voices.items()},
        "stories": {str(k): v for k, v in stories.items()},
        "goods": {str(k): v for k, v in goods.items()},
        "items": items,
        "roles": {str(k): v for k, v in roles.items()},
        "role_exp": {str(k): {str(a): b for a, b in v.items()} for k, v in role_exp.items()},
        "weapons": {str(k): v for k, v in weapons.items() if v["name"]},
        "weapon_exp": {str(k): {str(a): b for a, b in v.items()} for k, v in wlevel.items()},
        "exp_items": exp_items,
        "tower": {str(k): v for k, v in tower.items()},
        "matrix": {"seasons": seasons, "levels": matrix_levels, "waves": waves},
        "ruins": {str(k): v for k, v in ruins.items()},
    }


def write(con, data):
    con.execute("CREATE TABLE IF NOT EXISTS lib (name TEXT PRIMARY KEY, data TEXT)")
    con.execute("DELETE FROM lib")
    con.executemany("INSERT INTO lib (name, data) VALUES (?, ?)",
                    [(k, json.dumps(v, ensure_ascii=False)) for k, v in data.items()])
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('lib_version', ?)", (LIB_VERSION,))
    con.commit()


def ready(con):
    try:
        row = con.execute("SELECT value FROM meta WHERE key='lib_version'").fetchone()
        return bool(row) and row[0] == LIB_VERSION
    except Exception:
        return False


def backfill(con, version_dir, progress=None):
    if missing(version_dir):
        fetch(version_dir, progress)
    ids = {r[0] for r in con.execute("SELECT id FROM characters")}
    data = build(version_dir, ids)
    write(con, data)
    _cache.clear()
    return data


_cache = {}


def get(con, name):
    key = (id(con), name)
    if key not in _cache:
        try:
            row = con.execute("SELECT data FROM lib WHERE name=?", (name,)).fetchone()
        except Exception:
            row = None
        _cache[key] = json.loads(row[0]) if row else {}
    return _cache[key]


def clear():
    _cache.clear()
