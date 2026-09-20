import json

_DECODER = json.JSONDecoder()
_CHUNK = 4 * 1024 * 1024


def iter_entries(path):
    with open(path, "r", encoding="utf-8") as f:
        buf = f.read(_CHUNK)
        start = buf.find("[")
        if start < 0:
            return
        buf = buf[start + 1:]
        pos = 0
        while True:
            while pos < len(buf) and buf[pos] in " \t\r\n,":
                pos += 1
            if pos < len(buf) and buf[pos] == "]":
                return
            if pos >= len(buf):
                more = f.read(_CHUNK)
                if not more:
                    return
                buf = buf[pos:] + more
                pos = 0
                continue
            try:
                obj, end = _DECODER.raw_decode(buf, pos)
            except ValueError:
                more = f.read(_CHUNK)
                if not more:
                    return
                buf = buf[pos:] + more
                pos = 0
                continue
            yield obj
            pos = end
            if pos > _CHUNK:
                buf = buf[pos:]
                pos = 0


def load_prefixed(path, prefixes):
    out = {}
    pfx = tuple(prefixes)
    for e in iter_entries(path):
        k = e.get("Id")
        if isinstance(k, str) and k.startswith(pfx):
            c = e.get("Content")
            if c:
                out[k] = c
    return out
