import json
import os

APP_NAME = "ddinggwasajeon"
OLD_APP_NAME = "ddingmunhak"
APP_TITLE = "띵과사전"


def app_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.local/share")
    d = os.path.join(base, APP_NAME)
    old = os.path.join(base, OLD_APP_NAME)
    if not os.path.isdir(d) and os.path.isdir(old):
        try:
            os.rename(old, d)
        except OSError:
            pass
    os.makedirs(d, exist_ok=True)
    return d


def data_root():
    d = os.path.join(app_dir(), "data")
    os.makedirs(d, exist_ok=True)
    return d


def config_path():
    return os.path.join(app_dir(), "config.json")


DEFAULTS = {
    "version": "",
    "skill_level": 10,
    "party": [],
    "party_b": [],
    "party_chains": {},
    "plan": [],
}


def load():
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    cfg.pop("api_key", None)
    cfg.pop("model", None)
    return cfg


def save(cfg):
    out = {k: v for k, v in cfg.items() if k not in ("api_key", "model")}
    tmp = config_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    os.replace(tmp, config_path())


def db_path(version):
    return os.path.join(data_root(), version, "skills.sqlite")
