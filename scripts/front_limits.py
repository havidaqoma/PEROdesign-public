"""Length limits of the EES Solar (RSC) front matter, checked on the rendered manuscript (numbers already substituted).
Abstract <= 250 words (Keywords line excluded), Broader context <= 200 words. Fails closed: a missing or empty section
is an error, not a pass. Used by scripts/paperAB_build.py after the build; tests/test_front_limits.py covers it."""
import re

LIMITS = {"Abstract": 250, "Broader context": 200}


def section(md, title):
    m = re.search(r"^# " + re.escape(title) + r"(?: \{-\})?[ \t]*\r?$(.*?)(?=^# |\Z)", md, flags=re.M | re.S)
    if not m:
        raise SystemExit(f"FRONT FAIL: no '# {title}' section in the rendered manuscript")
    lines = [ln for ln in m.group(1).splitlines() if ln.strip() and not ln.startswith("**Keywords")]
    if not lines:
        raise SystemExit(f"FRONT FAIL: '# {title}' section is empty")
    return " ".join(lines)


def check(md):
    counts = {}
    for title, lim in LIMITS.items():
        n = len(section(md, title).split())
        counts[title] = n
        if n > lim:
            raise SystemExit(f"FRONT FAIL: {title} has {n} words (limit {lim})")
    return counts
