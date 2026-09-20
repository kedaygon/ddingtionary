import json
import os
import re
import time
from collections import defaultdict

import db
import importer
import parser as rich
import scaling
import textmap

TEXT_PREFIXES = (
    "Skill_", "SkillDescription_", "SkillTree_", "SkillBranch_",
    "Term", "RoleInfo_", "ResonantChain_", "PropertyIndex_", "WeaponConf_",
    "PhantomFetter_", "MonsterInfo_",
)
STAT_PREFIXES = ("PropertyIndex_", "WeaponConf_", "PhantomFetter_", "MonsterInfo_")

ELEMENT_PROPS = {22: "응결", 23: "용융", 24: "전도", 25: "기류", 26: "회절", 27: "인멸"}


def prop_stat(pid, add_type=1):
    if pid in (10007, 10002, 10010):
        base = {10007: "atk", 10002: "hp", 10010: "def"}[pid]
        return base + "_pct" if add_type == 2 else base
    if pid in ELEMENT_PROPS:
        return "elem:" + ELEMENT_PROPS[pid]
    return {7: "atk", 2: "hp", 10: "def", 8: "crit", 9: "crit_dmg", 11: "energy",
            35: "heal", 14: "skill", 17: "normal", 18: "heavy", 19: "burst",
            20: "intro", 15: "all"}.get(pid)


def prop_value(pid, add_type, raw):
    if add_type == 2 or pid < 10000:
        return raw / 100.0
    return raw


ECHO_GROUPS = {501: 4, 502: 3, 503: 1}

VARIANT_RE = re.compile(r"^(.*?)\s*·\s*(.+)$")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def default_cache_root():
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "wuwaskill", "data")


def build_characters(roleinfo, text, report):
    by_id = {}
    rows = []
    for e in roleinfo:
        if e.get("RoleType") != 1 or e.get("IsTrial"):
            continue
        name = text.get(e.get("Name") or "")
        if not name:
            report["role_missing_name"] += 1
            continue
        by_id[e["Id"]] = (e, name)

    names = defaultdict(list)
    for rid, (e, name) in by_id.items():
        m = VARIANT_RE.match(name)
        names[m.group(1) if m else name].append(rid)

    base_of = {}
    label_of = {}
    for stem, ids in names.items():
        ids.sort()
        if len(ids) == 1:
            base_of[ids[0]] = ids[0]
            label_of[ids[0]] = None
            continue
        base = min(ids, key=lambda i: (by_id[i][0].get("Priority") or 0, i))
        for i in ids:
            base_of[i] = base
            m = VARIANT_RE.match(by_id[i][1])
            label_of[i] = m.group(2) if m else None

    for rid, (e, name) in sorted(by_id.items()):
        rows.append((
            rid,
            name,
            text.get(e.get("NickName") or ""),
            e.get("ParentId") or 0,
            base_of.get(rid, rid),
            label_of.get(rid),
            e.get("ElementId"),
            e.get("QualityId"),
            e.get("Priority"),
            0,
        ))
    return rows, set(by_id)


def build_skills(skill_rows, text, char_ids, report):
    skills = []
    params = []
    links = []
    for e in skill_rows:
        cid = e.get("SkillGroupId")
        if cid not in char_ids:
            report["skill_orphan"] += 1
            continue

        raw = text.get(e.get("SkillDescribe") or "") or ""
        detail = e.get("SkillDetailNum") or []
        subbed, missing = rich.substitute(raw, detail)
        if missing:
            report["param_unresolved"] += len(missing)
            report["param_unresolved_skills"].add(e["Id"])

        plain, spans, term_links = rich.parse_rich(subbed)

        resume_raw = text.get(e.get("SkillResume") or "") or ""
        resume_sub, _ = rich.substitute(resume_raw, e.get("SkillResumeNum") or [])
        resume_plain = rich.strip_tags(resume_sub)

        skills.append((
            e["Id"],
            cid,
            e.get("SkillLevelGroupId"),
            e.get("SkillType"),
            e.get("SortIndex"),
            e.get("MaxSkillLevel"),
            text.get(e.get("SkillName") or ""),
            raw,
            plain,
            resume_plain,
            db.dumps(spans),
        ))

        for i, v in enumerate(detail):
            params.append((e["Id"], i, str(v)))

        for l in term_links:
            links.append((e["Id"], l["term_id"], l["surface"], l["start"], l["end"]))

        if not raw:
            report["skill_no_text"] += 1

    return skills, params, links


def build_scalings(desc_rows, level_caps, text, report):
    rows = []
    levels = []
    terms = []
    for e in desc_rows:
        detail = e.get("SkillDetailNum") or []
        values = []
        for grp in detail:
            arr = grp.get("ArrayString") if isinstance(grp, dict) else None
            if arr:
                values.append(arr)
        attr = text.get(e.get("AttributeName") or "")
        if not attr:
            report["scaling_no_label"] += 1

        flat = values[0] if values else []
        sid = e["Id"]
        group = e.get("SkillLevelGroupId")
        cap = level_caps.get(group, 0)
        if cap and cap < len(flat):
            flat = flat[:cap]
        elif cap > len(flat):
            report["cap_exceeds_values"] += 1
        for lvl, raw in enumerate(flat, 1):
            parsed, err = scaling.try_parse(raw)
            if err:
                report["scaling_unparsed"] += 1
                report["scaling_unparsed_samples"].add(str(raw)[:40])
                levels.append((sid, lvl, raw, None, None, None, err))
                continue
            pct, fl, hits = scaling.totals(parsed)
            levels.append((sid, lvl, raw, pct, fl, hits, None))
            for seq, t in enumerate(parsed):
                terms.append((sid, lvl, seq, t.value, t.unit, t.hits))
            if scaling.is_multihit(parsed):
                report["scaling_multihit"] += 1

        report["level_count_%d" % len(flat)] += 1

        rows.append((
            sid,
            e.get("SkillLevelGroupId"),
            rich.strip_tags(attr),
            e.get("Order"),
            len(flat),
            cap or None,
            db.dumps(values),
            scale_kind(text.get(e.get("Description") or "")),
        ))
    return rows, levels, terms


def scale_kind(fmt):
    if not fmt:
        return None
    if "HP" in fmt or "생명" in fmt:
        return "hp"
    if "방어력" in fmt:
        return "def"
    if "공격력" in fmt:
        return "atk"
    return None


def backfill_scale_kinds(con, version_dir):
    path = importer.source_path(version_dir, "BinData/skill/skilldescription.json")
    tpath = importer.source_path(version_dir, TEXT_PATH)
    if not (os.path.isfile(path) and os.path.isfile(tpath)):
        return 0
    text = textmap.load_prefixed(tpath, ("SkillDescription_",))
    rows = []
    for e in load_json(path):
        k = scale_kind(text.get(e.get("Description") or ""))
        if k:
            rows.append((k, e["Id"]))
    con.executemany("UPDATE skill_scalings SET scale_kind=? WHERE id=?", rows)
    db.set_meta(con, "scale_kind", 1)
    con.commit()
    return len(rows)


def build_terms(text, report):
    rows = []
    titles = {}
    descs = {}
    for k, v in text.items():
        if not k.startswith("Term"):
            continue
        if k.endswith("_Title"):
            tid = k[4:-6]
            if tid.isdigit():
                titles[int(tid)] = v
        elif k.endswith("_Desc"):
            tid = k[4:-5]
            if tid.isdigit():
                descs[int(tid)] = v
    for tid in sorted(set(titles) | set(descs)):
        raw = descs.get(tid, "")
        plain, spans, _ = rich.parse_rich(raw)
        rows.append((
            tid,
            rich.strip_tags(titles.get(tid, "")),
            raw,
            plain,
            db.dumps(spans),
        ))
        if tid not in titles:
            report["term_no_title"] += 1
    return rows


def build_nodes(tree_rows, text, char_ids, report):
    rows = []
    for e in tree_rows:
        cid = e.get("NodeGroup")
        if cid not in char_ids:
            report["node_orphan"] += 1
            continue
        raw = text.get(e.get("PropertyNodeDescribe") or "") or ""
        subbed, missing = rich.substitute(raw, e.get("PropertyNodeParam") or [])
        if missing:
            report["param_unresolved"] += len(missing)
        plain = rich.strip_tags(subbed)
        rows.append((
            e["Id"],
            cid,
            e.get("NodeIndex"),
            e.get("NodeType"),
            db.dumps(e.get("ParentNodes") or []),
            e.get("SkillId") or None,
            rich.strip_tags(text.get(e.get("PropertyNodeTitle") or "") or ""),
            raw,
            plain,
            db.dumps(e.get("PropertyNodeParam") or []),
            db.dumps(e.get("Property") or []),
        ))
    return rows


def build_chains(chain_rows, roleinfo, text, char_ids, report):
    group_to = defaultdict(list)
    for e in roleinfo:
        cid = e.get("Id")
        g = e.get("ResonantChainGroupId")
        if cid in char_ids and g:
            group_to[g].append(cid)
    rows = []
    for e in chain_rows:
        owners = group_to.get(e.get("GroupId"))
        if not owners:
            report["chain_orphan"] += 1
            continue
        raw = text.get(e.get("AttributesDescription") or "") or ""
        subbed, missing = rich.substitute(raw, e.get("AttributesDescriptionParams") or [])
        if missing:
            report["param_unresolved"] += len(missing)
        plain = rich.strip_tags(subbed)
        name = rich.strip_tags(text.get(e.get("NodeName") or "") or "")
        for cid in owners:
            rows.append((
                cid * 100 + (e.get("GroupIndex") or 0),
                cid,
                e.get("GroupIndex"),
                name,
                raw,
                plain,
                db.dumps(e.get("AttributesDescriptionParams") or []),
                db.dumps(e.get("AddProp") or []),
                db.dumps(e.get("BuffIds") or []),
            ))
    return rows


def build_stats(src, roleinfo, text, char_ids):
    def jl(rel):
        return load_json(importer.source_path(src, rel))

    base = {}
    for p in jl("BinData/property/baseproperty.json"):
        if p.get("Lv") == 1:
            base.setdefault(p["Id"], p)
    role_rows = []
    for e in roleinfo:
        cid = e.get("Id")
        if cid not in char_ids:
            continue
        p = base.get(e.get("PropertyId"))
        if not p:
            continue
        role_rows.append((cid, e.get("WeaponType"), p.get("LifeMax"), p.get("Atk"),
                          p.get("Def"), (p.get("Crit") or 0) / 100.0,
                          (p.get("CritDamage") or 0) / 100.0))
    growth = [(g["Level"], g["BreachLevel"], g["LifeMaxRatio"] / 10000.0,
               g["AtkRatio"] / 10000.0, g["DefRatio"] / 10000.0)
              for g in jl("BinData/property/rolepropertygrowth.json")]
    wgrowth = [(g["CurveId"], g["Level"], g["BreachLevel"], g["CurveValue"] / 10000.0)
               for g in jl("BinData/property/weaponpropertygrowth.json")]
    weapons = []
    for w in jl("BinData/weapon/weaponconf.json"):
        name = rich.strip_tags(text.get(w.get("WeaponName") or "") or "")
        if not name or not w.get("IsShow", True):
            continue
        f = w.get("FirstPropId") or {}
        s = w.get("SecondPropId") or {}
        params = [x.get("ArrayString") or [] for x in (w.get("DescParams") or [])]
        weapons.append((w["ItemId"], name, w.get("WeaponType"), w.get("QualityId"),
                        f.get("Value"), w.get("FirstCurve"), s.get("Id"), s.get("Value"),
                        1 if s.get("IsRatio") else 0, w.get("SecondCurve"),
                        text.get(w.get("Desc") or "") or "", db.dumps(params)))
    props = []
    for p in jl("BinData/property/propertyindex.json"):
        props.append((p["Id"], p.get("Key"), text.get(p.get("Name") or "") or p.get("Key"),
                      1 if p.get("IsPercent") else 0))
    out = {"role_stats": role_rows, "stat_growth": growth, "weapons": weapons,
           "weapon_growth": wgrowth, "props": props}
    out.update(build_echo(src, text))
    out["bosses"] = build_bosses(src, text)
    return out


def build_bosses(src, text):
    path = importer.source_path(src, "BinData/monster_Info/monsterinfo.json")
    if not os.path.isfile(path):
        return []
    rows = {}
    for m in load_json(path):
        if m.get("RarityId") not in (3, 4):
            continue
        name = rich.strip_tags(text.get(m.get("Name") or "") or "").strip()
        elems = [e for e in (m.get("ElementIdArray") or []) if e]
        if not name or not elems:
            continue
        if name not in rows:
            rows[name] = (name, db.dumps(elems), m.get("RarityId"))
    return sorted(rows.values(), key=lambda r: r[0])


def build_echo(src, text):
    def jl(rel):
        return load_json(importer.source_path(src, rel))

    growth = {(g["GrowthId"], g["Level"]): g["Value"] / 10000.0
              for g in jl("BinData/phantom/phantomgrowth.json")}
    items = {x["Id"]: x for x in jl("BinData/phantom/phantommainpropitem.json")}
    mains = []
    seen = set()
    for m in jl("BinData/phantom/phantommainproperty.json"):
        cost = ECHO_GROUPS.get(m.get("RandGroupId"))
        if not cost:
            continue
        for slot, iid in enumerate(m.get("PropGroup") or []):
            it = items.get(iid)
            if not it:
                continue
            stat = prop_stat(it["PropId"], it.get("AddType", 1))
            if not stat or (cost, slot, stat) in seen:
                continue
            seen.add((cost, slot, stat))
            g = growth.get((it.get("GrowthId"), 25), 1.0)
            mains.append((cost, slot, stat,
                          round(prop_value(it["PropId"], it.get("AddType", 1),
                                           it["StandardProperty"] * g), 2)))
    fetters = {f["Id"]: f for f in jl("BinData/phantom/phantomfetter.json")}
    sets = []
    for g in jl("BinData/phantom/phantomfettergroup.json"):
        name = rich.strip_tags(text.get(g.get("FetterGroupName") or "") or "")
        if not name:
            continue
        for fm in g.get("FetterMap") or []:
            f = fetters.get(fm.get("Value"))
            if not f:
                continue
            props = []
            for p in f.get("AddProp") or []:
                st = prop_stat(p["Id"], 2 if p.get("IsRatio") else 1)
                if st:
                    v = p["Value"] * 100.0 if p.get("IsRatio") else \
                        prop_value(p["Id"], 1, p["Value"])
                    props.append([st, round(v, 2)])
            raw = text.get(f.get("EffectDescription") or "") or ""
            desc, _m = rich.substitute(raw, f.get("EffectDescriptionParam") or [])
            sets.append((g["Id"], fm["Key"], name, db.dumps(props), rich.strip_tags(desc)))
    return {"echo_main": mains, "echo_sets": sets}


STATS_VERSION = "3"


def write_stats(con, data):
    for table, rows in data.items():
        con.execute("DELETE FROM " + table)
        db.insert_many(con, table, rows)
    db.set_meta(con, "stats_version", STATS_VERSION)


def backfill_stats(con, version_dir, progress=None):
    if importer.missing_extra(version_dir):
        importer.fetch_extra(version_dir, progress)
    text = textmap.load_prefixed(importer.source_path(version_dir, TEXT_PATH_STATS),
                                 STAT_PREFIXES)
    roleinfo = load_json(importer.source_path(version_dir, "BinData/role/roleinfo.json"))
    char_ids = {r[0] for r in con.execute("SELECT id FROM characters")}
    data = build_stats(version_dir, roleinfo, text, char_ids)
    write_stats(con, data)
    con.commit()
    return len(data["weapons"])


TEXT_PATH_STATS = "Textmaps/ko/multi_text/MultiText.json"


CHAIN_PATH = "BinData/resonate_chain/resonantchain.json"
TEXT_PATH = "Textmaps/ko/multi_text/MultiText.json"


def backfill_chains(con, version_dir):
    chain_file = importer.source_path(version_dir, CHAIN_PATH)
    text_file = importer.source_path(version_dir, TEXT_PATH)
    role_file = importer.source_path(version_dir, "BinData/role/roleinfo.json")
    if not all(os.path.isfile(p) for p in (chain_file, text_file, role_file)):
        return 0
    text = textmap.load_prefixed(text_file, ("ResonantChain_",))
    char_ids = {r[0] for r in con.execute("SELECT id FROM characters")}
    report = defaultdict(int)
    rows = build_chains(load_json(chain_file), load_json(role_file), text, char_ids, report)
    con.execute("DELETE FROM chains")
    db.insert_chains(con, rows)
    con.commit()
    return len(rows)


def do_import(version=None, cache_root=None, out=None, force=False,
              progress=None, repo_path=None):
    t0 = time.time()
    emit = progress or (lambda stage, msg: None)
    cache_root = cache_root or default_cache_root()

    if repo_path:
        version = version or "local"
        src = repo_path
    else:
        version = version or importer.latest_version()
        src = importer.fetch(version, cache_root, progress=emit, force=force)

    out = out or os.path.join(cache_root, version, "skills.sqlite")

    report = defaultdict(int)
    report["param_unresolved_skills"] = set()
    report["scaling_unparsed_samples"] = set()

    emit("parse", "텍스트맵 읽는 중")
    text = textmap.load_prefixed(
        importer.source_path(src, "Textmaps/ko/multi_text/MultiText.json"),
        TEXT_PREFIXES,
    )

    emit("parse", "테이블 읽는 중")
    roleinfo = load_json(importer.source_path(src, "BinData/role/roleinfo.json"))
    skill_rows = load_json(importer.source_path(src, "BinData/skill/skill.json"))
    desc_rows = load_json(importer.source_path(src, "BinData/skill/skilldescription.json"))
    tree_rows = load_json(importer.source_path(src, "BinData/skillTree/skilltree.json"))
    level_rows = load_json(importer.source_path(src, "BinData/skill/skilllevel.json"))
    chain_rows = load_json(importer.source_path(src, CHAIN_PATH))

    level_caps = defaultdict(int)
    for e in level_rows:
        g = e.get("SkillLevelGroupId")
        if g is not None:
            level_caps[g] = max(level_caps[g], e.get("SkillId") or 0)

    emit("parse", "구조화 중")
    chars, char_ids = build_characters(roleinfo, text, report)
    skills, params, links = build_skills(skill_rows, text, char_ids, report)
    owners = {s[1] for s in skills}
    live_bases = {c[4] for c in chars if c[0] in owners}
    chars = [c[:9] + (1 if (c[0] not in owners and c[4] in live_bases) else 0,) for c in chars]
    scalings, scaling_levels, scaling_terms = build_scalings(desc_rows, level_caps, text, report)
    terms = build_terms(text, report)
    nodes = build_nodes(tree_rows, text, char_ids, report)
    chains = build_chains(chain_rows, roleinfo, text, char_ids, report)

    term_ids = {t[0] for t in terms}
    report["link_dangling"] = len({l[1] for l in links if l[1] not in term_ids})

    emit("write", "데이터베이스 저장 중")
    final = out
    out = final + ".new"
    for p in (out, out + "-wal", out + "-shm"):
        if os.path.exists(p):
            os.remove(p)
    con = db.connect(out)
    db.reset(con)
    db.insert_characters(con, chars)
    db.insert_skills(con, skills)
    db.insert_params(con, params)
    db.insert_scalings(con, scalings)
    db.insert_scaling_levels(con, scaling_levels)
    db.insert_scaling_terms(con, scaling_terms)
    db.insert_terms(con, terms)
    db.insert_links(con, links)
    db.insert_nodes(con, nodes)
    db.insert_chains(con, chains)
    if not importer.missing_extra(src):
        write_stats(con, build_stats(src, roleinfo, text, char_ids))
    db.set_meta(con, "game_version", version)
    db.set_meta(con, "imported_at", int(time.time()))
    db.set_meta(con, "scale_kind", 1)
    con.commit()
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.execute("PRAGMA journal_mode=DELETE")
    con.close()
    for p in (final + "-wal", final + "-shm"):
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass
    try:
        os.replace(out, final)
    except OSError as e:
        raise importer.ImportError_(
            "데이터베이스 파일을 바꾸지 못했습니다. 띵과사전을 다시 켠 뒤 시도하세요 (%s)" % e)
    out = final

    summary = {
        "version": version,
        "out": out,
        "characters": len(chars),
        "distinct": len({c[4] for c in chars}),
        "skills": len(skills),
        "scalings": len(scalings),
        "scaling_values": len(scaling_levels),
        "terms": len(terms),
        "links": len(links),
        "nodes": len(nodes),
        "chains": len(chains),
        "param_unresolved": report["param_unresolved"],
        "scaling_unparsed": report["scaling_unparsed"],
        "link_dangling": report["link_dangling"],
        "elapsed": round(time.time() - t0, 1),
    }
    emit("done", "완료")
    return summary
