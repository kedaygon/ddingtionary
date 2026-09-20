import re

_TAG = re.compile(r"<(/?)([A-Za-z]+)(?:\s+href)?\s*=?\s*([^>]*)>")
_PARAM = re.compile(r"\{(\d+)\}")


def parse_rich(text):
    if not text:
        return "", [], []

    plain = []
    spans = []
    links = []
    stack = []
    pos = 0
    length = 0

    for m in _TAG.finditer(text):
        chunk = text[pos:m.start()]
        if chunk:
            plain.append(chunk)
            length += len(chunk)
        pos = m.end()

        closing, name, value = m.group(1), m.group(2).lower(), m.group(3).strip()

        if closing:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == name:
                    _, val, start = stack.pop(i)
                    if length > start:
                        entry = {
                            "kind": name,
                            "value": val,
                            "start": start,
                            "end": length,
                            "text": "".join(plain)[start:length],
                        }
                        spans.append(entry)
                        if name == "te" and val.isdigit():
                            links.append({
                                "term_id": int(val),
                                "surface": entry["text"],
                                "start": start,
                                "end": length,
                            })
                    break
        else:
            stack.append((name, value, length))

    tail = text[pos:]
    if tail:
        plain.append(tail)

    flat = "".join(plain)
    spans.sort(key=lambda s: (s["start"], s["end"]))
    return flat, spans, links


def substitute(text, params):
    if not text:
        return text, []
    missing = []

    def repl(m):
        i = int(m.group(1))
        if params and 0 <= i < len(params):
            return str(params[i])
        missing.append(i)
        return m.group(0)

    return _PARAM.sub(repl, text), missing


def param_slots(text):
    return sorted({int(m.group(1)) for m in _PARAM.finditer(text or "")})


def strip_tags(text):
    return parse_rich(text)[0]
