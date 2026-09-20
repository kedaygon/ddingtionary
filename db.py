import json
import os
import re
import sqlite3

SCHEMA_VERSION = 5

TABLES = ("meta", "characters", "skills", "skill_params", "skill_scalings",
          "scaling_levels", "scaling_terms", "terms", "skill_term_links", "tree_nodes",
          "chains", "role_stats", "stat_growth", "weapons", "weapon_growth", "props",
          "echo_main", "echo_sets", "bosses")

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    nickname TEXT,
    parent_id INTEGER NOT NULL DEFAULT 0,
    base_id INTEGER NOT NULL,
    variant_label TEXT,
    element_id INTEGER,
    quality_id INTEGER,
    priority INTEGER,
    is_alias INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY,
    character_id INTEGER NOT NULL,
    skill_level_group_id INTEGER,
    skill_type INTEGER,
    sort_index INTEGER,
    max_level INTEGER,
    name TEXT,
    describe_raw TEXT,
    describe_text TEXT,
    resume_text TEXT,
    spans TEXT,
    FOREIGN KEY (character_id) REFERENCES characters(id)
);

CREATE TABLE IF NOT EXISTS skill_params (
    skill_id INTEGER NOT NULL,
    idx INTEGER NOT NULL,
    value TEXT,
    PRIMARY KEY (skill_id, idx)
);

CREATE TABLE IF NOT EXISTS skill_scalings (
    id INTEGER PRIMARY KEY,
    skill_level_group_id INTEGER NOT NULL,
    attribute_name TEXT,
    sort_order INTEGER,
    n_levels INTEGER,
    level_cap INTEGER,
    values_json TEXT,
    scale_kind TEXT
);

CREATE TABLE IF NOT EXISTS scaling_levels (
    scaling_id INTEGER NOT NULL,
    level INTEGER NOT NULL,
    raw TEXT,
    total_pct REAL,
    total_flat REAL,
    total_hits INTEGER,
    parse_error TEXT,
    PRIMARY KEY (scaling_id, level)
);

CREATE TABLE IF NOT EXISTS scaling_terms (
    scaling_id INTEGER NOT NULL,
    level INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    hits INTEGER NOT NULL,
    PRIMARY KEY (scaling_id, level, seq)
);

CREATE TABLE IF NOT EXISTS terms (
    id INTEGER PRIMARY KEY,
    title TEXT,
    desc_raw TEXT,
    desc_text TEXT,
    spans TEXT
);

CREATE TABLE IF NOT EXISTS skill_term_links (
    skill_id INTEGER NOT NULL,
    term_id INTEGER NOT NULL,
    surface TEXT,
    start_pos INTEGER,
    end_pos INTEGER
);

CREATE TABLE IF NOT EXISTS tree_nodes (
    id INTEGER PRIMARY KEY,
    character_id INTEGER NOT NULL,
    node_index INTEGER,
    node_type INTEGER,
    parent_nodes TEXT,
    skill_id INTEGER,
    title TEXT,
    describe_raw TEXT,
    describe_text TEXT,
    params TEXT,
    property_json TEXT
);

CREATE TABLE IF NOT EXISTS chains (
    id INTEGER PRIMARY KEY,
    character_id INTEGER NOT NULL,
    idx INTEGER,
    name TEXT,
    describe_raw TEXT,
    describe_text TEXT,
    params TEXT,
    add_prop TEXT,
    buff_ids TEXT
);

CREATE TABLE IF NOT EXISTS role_stats (
    character_id INTEGER PRIMARY KEY,
    weapon_type INTEGER,
    hp REAL,
    atk REAL,
    def REAL,
    crit REAL,
    crit_dmg REAL
);

CREATE TABLE IF NOT EXISTS stat_growth (
    level INTEGER NOT NULL,
    breach INTEGER NOT NULL,
    hp REAL,
    atk REAL,
    def REAL,
    PRIMARY KEY (level, breach)
);

CREATE TABLE IF NOT EXISTS weapons (
    id INTEGER PRIMARY KEY,
    name TEXT,
    weapon_type INTEGER,
    quality INTEGER,
    atk_base REAL,
    atk_curve INTEGER,
    sub_prop INTEGER,
    sub_value REAL,
    sub_ratio INTEGER,
    sub_curve INTEGER,
    desc_raw TEXT,
    params TEXT
);

CREATE TABLE IF NOT EXISTS weapon_growth (
    curve INTEGER NOT NULL,
    level INTEGER NOT NULL,
    breach INTEGER NOT NULL,
    value REAL,
    PRIMARY KEY (curve, level, breach)
);

CREATE TABLE IF NOT EXISTS props (
    id INTEGER PRIMARY KEY,
    key TEXT,
    name TEXT,
    percent INTEGER
);

CREATE TABLE IF NOT EXISTS echo_main (
    cost INTEGER NOT NULL,
    slot INTEGER NOT NULL,
    stat TEXT NOT NULL,
    value REAL,
    PRIMARY KEY (cost, slot, stat)
);

CREATE TABLE IF NOT EXISTS echo_sets (
    id INTEGER NOT NULL,
    pieces INTEGER NOT NULL,
    name TEXT,
    add_prop TEXT,
    desc_text TEXT,
    PRIMARY KEY (id, pieces)
);

CREATE TABLE IF NOT EXISTS bosses (
    name TEXT PRIMARY KEY,
    elements TEXT,
    rarity INTEGER
);

CREATE INDEX IF NOT EXISTS ix_chains_char ON chains(character_id);
CREATE INDEX IF NOT EXISTS ix_scaling_levels_id ON scaling_levels(scaling_id);
CREATE INDEX IF NOT EXISTS ix_scaling_terms_id ON scaling_terms(scaling_id, level);
CREATE INDEX IF NOT EXISTS ix_links_skill ON skill_term_links(skill_id);
CREATE INDEX IF NOT EXISTS ix_links_term ON skill_term_links(term_id);
CREATE INDEX IF NOT EXISTS ix_nodes_char ON tree_nodes(character_id);
"""


_SKIP = ("PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "CHECK", "CONSTRAINT")


def _expected_columns():
    out = {}
    for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\n\);", SCHEMA, re.S):
        cols = []
        for line in m.group(2).strip().splitlines():
            line = line.strip().rstrip(",")
            if not line or line.upper().startswith(_SKIP):
                continue
            cols.append((line.split()[0], line))
        out[m.group(1)] = cols
    return out


def _addable(decl):
    d = decl
    for token in ("PRIMARY KEY", "AUTOINCREMENT", "UNIQUE"):
        d = d.replace(token, "")
    if "NOT NULL" in d and "DEFAULT" not in d:
        d = d.replace("NOT NULL", "")
    return " ".join(d.split())


def has_data(con):
    try:
        return con.execute("SELECT count(*) FROM characters").fetchone()[0] > 0
    except sqlite3.Error:
        return False


def repair(con):
    fixed = []
    for table, cols in _expected_columns().items():
        have = {r[1] for r in con.execute("PRAGMA table_info(%s)" % table)}
        if not have:
            continue
        for name, decl in cols:
            if name not in have:
                con.execute("ALTER TABLE %s ADD COLUMN %s" % (table, _addable(decl)))
                fixed.append("%s.%s" % (table, name))
    if fixed:
        con.commit()
    return fixed


RETIRED_TABLES = ("buffs", "extract_runs")


def connect(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    con = sqlite3.connect(path)
    for t in RETIRED_TABLES:
        con.execute("DROP TABLE IF EXISTS " + t)
    stmts = [x.strip() for x in SCHEMA.split(";") if x.strip()]
    tables = [x for x in stmts if not x.upper().startswith("CREATE INDEX")]
    indexes = [x for x in stmts if x.upper().startswith("CREATE INDEX")]
    for x in tables:
        con.execute(x)
    repair(con)
    for x in indexes:
        con.execute(x)
    con.execute("PRAGMA user_version=%d" % SCHEMA_VERSION)
    con.commit()
    return con


def reset(con):
    for t in TABLES:
        con.execute("DELETE FROM " + t)


def get_meta(con, key):
    try:
        row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    except sqlite3.Error:
        return None
    return row[0] if row else None


def set_meta(con, key, value):
    con.execute(
        "INSERT INTO meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def insert_characters(con, rows):
    con.executemany(
        "INSERT OR REPLACE INTO characters"
        "(id,name,nickname,parent_id,base_id,variant_label,element_id,quality_id,priority,is_alias)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)",
        rows,
    )


def insert_skills(con, rows):
    con.executemany(
        "INSERT OR REPLACE INTO skills"
        "(id,character_id,skill_level_group_id,skill_type,sort_index,max_level,"
        "name,describe_raw,describe_text,resume_text,spans) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )


def insert_params(con, rows):
    con.executemany(
        "INSERT OR REPLACE INTO skill_params(skill_id,idx,value) VALUES(?,?,?)",
        rows,
    )


def insert_scalings(con, rows):
    con.executemany(
        "INSERT OR REPLACE INTO skill_scalings"
        "(id,skill_level_group_id,attribute_name,sort_order,n_levels,level_cap,values_json,"
        "scale_kind) VALUES(?,?,?,?,?,?,?,?)",
        rows,
    )


def insert_scaling_levels(con, rows):
    con.executemany(
        "INSERT OR REPLACE INTO scaling_levels"
        "(scaling_id,level,raw,total_pct,total_flat,total_hits,parse_error) "
        "VALUES(?,?,?,?,?,?,?)",
        rows,
    )


def insert_scaling_terms(con, rows):
    con.executemany(
        "INSERT OR REPLACE INTO scaling_terms"
        "(scaling_id,level,seq,value,unit,hits) VALUES(?,?,?,?,?,?)",
        rows,
    )


def insert_terms(con, rows):
    con.executemany(
        "INSERT OR REPLACE INTO terms(id,title,desc_raw,desc_text,spans) VALUES(?,?,?,?,?)",
        rows,
    )


def insert_links(con, rows):
    con.executemany(
        "INSERT INTO skill_term_links(skill_id,term_id,surface,start_pos,end_pos) "
        "VALUES(?,?,?,?,?)",
        rows,
    )


def insert_nodes(con, rows):
    con.executemany(
        "INSERT OR REPLACE INTO tree_nodes"
        "(id,character_id,node_index,node_type,parent_nodes,skill_id,"
        "title,describe_raw,describe_text,params,property_json) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )



def insert_chains(con, rows):
    con.executemany(
        "INSERT OR REPLACE INTO chains "
        "(id,character_id,idx,name,describe_raw,describe_text,params,add_prop,buff_ids) "
        "VALUES (?,?,?,?,?,?,?,?,?)", rows)


def has_chains(con):
    try:
        return con.execute("SELECT count(*) FROM chains").fetchone()[0] > 0
    except sqlite3.Error:
        return False


def insert_many(con, table, rows):
    if not rows:
        return
    marks = ",".join("?" * len(rows[0]))
    con.executemany("INSERT OR REPLACE INTO %s VALUES (%s)" % (table, marks), rows)


def has_stats(con):
    try:
        return (con.execute("SELECT count(*) FROM weapons").fetchone()[0] > 0
                and con.execute("SELECT count(*) FROM echo_sets").fetchone()[0] > 0)
    except sqlite3.Error:
        return False


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
