"""Reader-facing name of the analysis plans.

Operator decision 2026-10-09, after the independent pre-submission re-check: the plans were committed to a private
git repository before the runs, not deposited in an independent registry, so every reader-facing text (manuscript,
Supplementary Information, cover letter, TOC text, Source Data, public README and metadata) calls them pre-specified
analysis plans. File names (docs/*_preregistration.md, docs/preregistration_provenance.json), stored run records and
code identifiers keep their original names; the Methods and the public README say so.

plan_terms(text) rewrites the wording; check(text, where) fails closed if a hyphenated or unhyphenated
"pre-register..." word survives outside a file name.
"""
import re

_MAP = [
    (re.compile(r"\b([Aa]) pre-registration\b"), lambda m: m.group(1) + "n analysis plan"),
    (re.compile(r"\bpre-registrations\b"), "analysis plans"),
    (re.compile(r"\bPre-registrations\b"), "Analysis plans"),
    (re.compile(r"\bpre-registration\b"), "analysis plan"),
    (re.compile(r"\bPre-registration\b"), "Analysis plan"),
    (re.compile(r"\bpre-registered\b"), "pre-specified"),
    (re.compile(r"\bPre-registered\b"), "Pre-specified"),
    (re.compile(r"\bPRE-REGISTERED\b"), "PRE-SPECIFIED"),
]
# file names and JSON field paths keep the old word: docs/PaperA_preregistration.md, docs/preregistration_provenance.json, ...
_FILE = re.compile(r"[\w./-]*preregistration[\w./-]*\.(?:md|json|py)\b|PREREGISTRATION_PROVENANCE|\bpreregistration(?:\.[\w-]+)+")
_BAD = re.compile(r"(?i)\bpre-?regist\w*")
# the one Methods sentence that explains the old name is allowed
_EXPLAIN = re.compile(r"rather than pre-registrations; their file names keep the word .preregistration.")


def plan_terms(text):
    for pat, rep in _MAP:
        text = pat.sub(rep, text)
    return text


def leftovers(text):
    return _BAD.findall(_FILE.sub("", _EXPLAIN.sub("", text)))


def check(text, where):
    bad = leftovers(text)
    if bad:
        raise SystemExit(f"plan-terms gate ({where}): {len(bad)} 'pre-registered' word(s) left: {sorted(set(bad))}")
    return True


def workbook(wb, where):
    """Rewrite every string cell of an openpyxl workbook, then check it."""
    n = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and _BAD.search(c.value):
                    new = plan_terms(c.value)
                    if new != c.value:
                        c.value, n = new, n + 1
                    check(c.value, f"{where} {ws.title}!{c.coordinate}")
    return n
