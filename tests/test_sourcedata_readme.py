"""The Source Data README must cite the same SI Notes, Tables and Figures as the workbook's own sheet descriptions.

The README index is written by hand; the workbook descriptions are written by scripts/paper*_sourcedata.py. A panel
review (2026-10-15) found the README pointing to SI Note S17 where the workbook (correctly) says Note S20. This test
compares the SI references of every sheet that both list. Fails closed: no README, or no sheet in common, is an error.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READMES = [ROOT / "scripts/release/overlay/source_data/README.md",  # private development tree
           ROOT / "source_data/README.md"]                           # public release tree
SCRIPTS = [ROOT / "scripts/paperA_sourcedata.py", ROOT / "scripts/paperB_sourcedata.py"]
REF = re.compile(r"\b(Note|Table|Figure)s? (S\d+)\b")


def refs(text):
    """SI references in a description; 'SI Note S19, Table S29' gives {('Note','S19'), ('Table','S29')}."""
    out, kind = set(), None
    for m in re.finditer(r"\b(Note|Table|Figure)s?\b|\b(S\d+)\b", text):
        if m.group(1):
            kind = m.group(1)
        elif kind:
            out.add((kind, m.group(2)))
    return out


def test_readme_and_workbook_cite_the_same_si_items():
    readme = next((p for p in READMES if p.exists()), None)
    assert readme is not None, f"no Source Data README at {READMES}"
    rows = dict(re.findall(r"^\| `(\w+)` \| (.*?) \| [\d,]+ \|", readme.read_text(encoding="utf-8"), flags=re.M))
    pairs = {}
    for s in SCRIPTS:
        for name, desc in re.findall(r'\[\s*"(\w+)",\s*"([^"]+)"\s*\]', s.read_text(encoding="utf-8")):
            pairs.setdefault(name, []).append(desc)
    common = sorted(set(rows) & set(pairs))
    assert len(common) >= 20, f"only {len(common)} sheets found in both README and workbook scripts"
    bad = {n: (sorted(refs(rows[n])), [sorted(refs(d)) for d in pairs[n]]) for n in common
           if all(refs(rows[n]) != refs(d) for d in pairs[n])}
    assert not bad, f"README and workbook cite different SI items: {bad}"


def test_ref_parser():
    assert refs("POST-HOC: x (SI Note S19, Table S29)") == {("Note", "S19"), ("Table", "S29")}
    assert refs("SI Table S9/S10: checks") == {("Table", "S9"), ("Table", "S10")}
    assert refs("Figure S9 and main Figure 6b") == {("Figure", "S9")}
    assert REF.search("Note S20")
