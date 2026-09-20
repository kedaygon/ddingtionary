import re
from collections import namedtuple

Term = namedtuple("Term", "value unit hits")

PCT = "pct"
FLAT = "flat"

_TERM_RE = re.compile(r"^(\d+(?:\.\d+)?)(%?)(?:\*(\d+))?$")


class ScalingError(ValueError):
    pass


def parse(expr):
    if expr is None:
        raise ScalingError("empty expression")
    s = str(expr).strip().replace(" ", "")
    if not s:
        raise ScalingError("empty expression")
    terms = []
    for token in s.split("+"):
        m = _TERM_RE.match(token)
        if not m:
            raise ScalingError("unparsable token %r in %r" % (token, expr))
        value = float(m.group(1))
        unit = PCT if m.group(2) else FLAT
        hits = int(m.group(3)) if m.group(3) else 1
        terms.append(Term(value, unit, hits))
    return terms


def try_parse(expr):
    try:
        return parse(expr), None
    except ScalingError as e:
        return None, str(e)


def totals(terms):
    pct = 0.0
    flat = 0.0
    hits = 0
    for t in terms:
        if t.unit == PCT:
            pct += t.value * t.hits
        else:
            flat += t.value * t.hits
        hits += t.hits
    return round(pct, 6), round(flat, 6), hits


def is_multihit(terms):
    return any(t.hits > 1 for t in terms) or len(terms) > 1


def format_terms(terms):
    out = []
    for t in terms:
        base = ("%g%%" % t.value) if t.unit == PCT else ("%g" % t.value)
        out.append(base if t.hits == 1 else "%s x%d" % (base, t.hits))
    return " + ".join(out)
