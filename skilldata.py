TYPE_NAMES = {1: "기본 공격", 2: "공명 스킬", 3: "공명 해방", 4: "고유 스킬",
              5: "변주 스킬", 6: "공명 회로", 7: "고유 스킬", 8: "고유 스킬",
              9: "고유 스킬", 10: "고유 스킬", 11: "반주 스킬", 12: "조화도 파괴"}

TYPE_ORDER = {1: 0, 2: 1, 3: 2, 5: 3, 11: 4, 6: 5, 4: 6, 12: 7}

ELEMENTS = {1: "응결", 2: "용융", 3: "전도", 4: "기류", 5: "회절", 6: "인멸"}


def load_skills(con, character_id):
    return con.execute(
        "SELECT id, skill_type, name, describe_text FROM skills "
        "WHERE character_id=? AND describe_text IS NOT NULL AND describe_text<>'' "
        "ORDER BY skill_type, sort_index",
        (character_id,)).fetchall()


def characters(con):
    return con.execute(
        "SELECT id, name, base_id, variant_label, element_id FROM characters "
        "WHERE is_alias=0 ORDER BY name").fetchall()


def character_name(con, cid):
    row = con.execute("SELECT name FROM characters WHERE id=?", (cid,)).fetchone()
    return row[0] if row else ""


def element_names(con):
    return {cid: ELEMENTS.get(elem) for cid, _n, _b, _v, elem in characters(con)}


def name_colors(con):
    import theme
    return {name: theme.element_color(ELEMENTS.get(elem))
            for _c, name, _b, _v, elem in characters(con)}


CHAIN_TYPE = 100


def load_chains(con, character_id):
    try:
        return con.execute(
            "SELECT id, idx, name FROM chains WHERE character_id=? ORDER BY idx",
            (character_id,)).fetchall()
    except Exception:
        return []
