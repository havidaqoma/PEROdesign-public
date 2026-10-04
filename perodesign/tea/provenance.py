"""Cost-value provenance gate for PeroDesign (P1-B).

Every cost or process number that enters the cost engine must pass this gate. It adapts the rules of
AutoTEA's gate (src/validation/provenance.py, PINNED below, vendored in third_party/autotea/) to cost-library units
(USD/g, USD/cm3, USD/m2, USD/W, ...) and to table rows:

  FIELD  required fields present; confidence in {low, medium, high}; value == float(value_text)
  SOURCE the entry names a registered source whose text file exists and whose sha256 matches
  R1     the quote_span appears literally in the source text (after AutoTEA's canonicaliser)
  R2     value_text appears inside the span as a WHOLE number (not part of a longer number)
  R3     if the unit is a currency unit: a currency token is adjacent to value_text (prefix "$10.0"
         or suffix "10.0 $"); otherwise, if unit_text is declared, unit_text follows value_text
  R4     the currency token's currency equals the unit's currency (no silent USD <- EUR)
  R5     DENOMINATOR (added after agy review 2026-09-28): for USD/<x> units the text right after the
         value+currency must be the printed denominator of <x> ("$ m-2", "$ g-1", "/W", "kWh -1"...).
         A printed denominator that differs from the unit (the C60 "$ g-2" typo) is accepted only with
         an explicit `denominator_as_printed` + `denominator_note`, and is flagged in the result.
  POS    POSITION (added after agy review): `position: {sep, index[, after]}` pins the value to one
         cell of a table row ("|") or one item of a list. Plain-unit values (fraction, g, nm, ...) MUST
         carry `position` or `unit_text`, otherwise any number in the span would pass.
  CELL   ROW-UNIT (added for data tables such as the World Bank Pink Sheet, where the unit is its own
         cell, e.g. "Gold | $/toz | c/ | ... | 4,411"): `unit_cell: {index, text}` + `position`. The
         cell at `index` of the same row must equal `text`, and `text` must read <currency><denominator>
         for the declared unit. This replaces R3/R5 for that entry only; it is the same idea as
         AutoTEA's header-driven FX rule (verify the claim in the form the source makes it).
  HEADER COLUMN-UNIT (for tables whose unit is in the column header, e.g. "Price (per Gram, USD)"):
         `unit_header: <text>` must appear in the span BEFORE the value, contain a currency token of the
         unit's currency and the unit's denominator word. Replaces R3/R5 for that entry only.
         If the entry has `position`, `header_index` is REQUIRED and must equal position.index: the value must
         sit in the (anchor-relative) column the header names. Found by an attack test: an employee count in
         the same row passed as a wage before this rule.
  ROW    `row_cells: {index: text}` (with `position`): other cells of the SAME row must read exactly `text`,
         e.g. country and year of a World Bank WDI row, so a value cannot be taken from the wrong country/year.
  LABEL  for machine-readable rate tables (e.g. TNB's rates.js) whose numbers carry no currency mark: `label`
         must immediately precede the value (e.g. "energyCharge: 0.2983") and `unit_basis` must quote where the
         unit is defined. Allowed only for LCU units (MYR/...), which the engine converts with a sourced FX rate.
         `block` is REQUIRED: the span must START with that exact block header, followed by a non-identifier
         character (so "const NONDOMMVGEN = " cannot be satisfied by "const NONDOMMVGENNEM = "; found by an
         attack test, scripts/label_gate_attack.py).
  SCALE  optional scale_word (thousand | million | billion): value must equal value_text x scale, and
         the span must read "<value_text> <scale_word> <currency>" (e.g. "20 million USD"). Added
         after the gate refused "ca. 20 million USD" under R3: the refusal was correct for a bare
         "20", so the scale is declared and checked explicitly instead of loosening R3.

Differences from AutoTEA, and why:
  * value_text (the literal as printed, e.g. "10.0") is declared instead of re-spelling a float,
    because AutoTEA's value_forms(10.0) offers only "10", which cannot be currency-marked inside
    "10.0 $ m-2". Declaring the literal keeps R2/R3 exact rather than loosening them.
  * the admissible units are the cost-library units below, not AutoTEA's energy-cost units.
Text normalisation is AutoTEA's `canon` (imported, not re-implemented), so both gates treat text
identically. The import is refused if AutoTEA's provenance.py hash differs from the pinned one.
"""
from __future__ import annotations

import hashlib
import os
import math
import re
import sys
from pathlib import Path
from typing import NamedTuple

# The two AutoTEA files used here are vendored byte-for-byte at the pinned commit in third_party/autotea/ (see its
# README); AUTOTEA_ROOT may point at a full AutoTEA checkout instead. The sha256 pins below are checked either way.
AUTOTEA_ROOT = Path(os.environ.get("AUTOTEA_ROOT", Path(__file__).resolve().parents[2] / "third_party" / "autotea"))
AUTOTEA_COMMIT = "1e8fa5afe7ac8f79a2b27f7069dd49528ea222b7"
AUTOTEA_PROVENANCE_SHA256 = "f7f360ad2f9032e77a6915033652dcdf6eca6c16fe91a7b7eb076292320b5dfc"


class AutoTEAPinError(RuntimeError):
    pass


def _load_autotea():
    p = AUTOTEA_ROOT / "src" / "validation" / "provenance.py"
    if not p.exists():
        raise AutoTEAPinError(f"AutoTEA not found at {AUTOTEA_ROOT}")
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    if h != AUTOTEA_PROVENANCE_SHA256:
        raise AutoTEAPinError(f"AutoTEA provenance.py changed (sha256 {h[:12]} != pinned "
                              f"{AUTOTEA_PROVENANCE_SHA256[:12]}, commit {AUTOTEA_COMMIT[:8]}); re-review before use")
    if str(AUTOTEA_ROOT) not in sys.path:
        sys.path.insert(0, str(AUTOTEA_ROOT))
    from src.validation import provenance as atp  # noqa: E402
    return atp


_atp = _load_autotea()
canon = _atp.canon
CURRENCY_TOKEN = _atp._CURRENCY_TOKEN          # noqa: SLF001 -- same token set as AutoTEA
TOKEN_CURRENCY = _atp._TOKEN_CURRENCY          # noqa: SLF001

CURRENCY_UNITS = {"USD", "USD/g", "USD/kg", "USD/cm3", "USD/m2", "USD/W", "USD/kWh", "USD/yr", "USD/toz"}
PLAIN_UNITS = {"g", "kg", "cm3", "m2", "nm", "fraction", "percent", "MW", "years", "count", "h/day", "kW", "g/cm3",
               "kWh", "W", "s", "MJ", "min"}
LCU_UNITS = {"MYR/kWh", "MYR/kW/month", "MYR/month"}
HEADER_DENOM = {"USD/g": r"(?:per\s+gram|per\s+g\b|/\s?g\b)", "USD/kg": r"(?:per\s+kg|/\s?kg)",
                "USD/m2": r"(?:per\s+m2|/\s?m2)", "USD/yr": r"(?:/\s?year|/\s?yr|per\s+year)",
                "USD/W": r"(?:/\s?W(?![a-z])|per\s+W(?![a-z]))"}
SCALES = {"thousand": 1e3, "million": 1e6, "billion": 1e9}
_H = r"[\-\u2010\u2011]"      # hyphen variants left after canon (U+2212 is already mapped to '-')
DENOMINATORS = {                 # printed forms of the denominator, matched right after value+currency
    "USD/m2": rf"(?:m\s?{_H}\s?2|/\s?m2|per\s+m2)",
    "USD/g": rf"(?:g\s?{_H}\s?1(?![0-9])|/\s?g(?![a-z])|per\s+g(?![a-z]))",
    "USD/kg": rf"(?:kg\s?{_H}\s?1(?![0-9])|/\s?kg|per\s+kg)",
    "USD/cm3": rf"(?:cm\s?{_H}\s?3|/\s?cm3|per\s+cm3)",
    "USD/W": rf"(?:W\s?{_H}\s?1(?![0-9])|/\s?W(?![a-z])|per\s+W(?![a-z]))",
    "USD/kWh": rf"(?:kWh\s?{_H}\s?1(?![0-9])|/\s?kWh|per\s+kWh)",
    "USD/yr": r"(?:/\s?(?:yr|year)|per\s+year)",
    "USD/toz": r"(?:/\s?toz|per\s+troy\s+oz)",
}
REQUIRED = ("id", "value", "value_text", "unit", "source", "quote_span", "confidence", "cost_basis_year",
            "geography")


class GateResult(NamedTuple):
    ok: bool
    rule: str      # OK | FIELD | SOURCE | UNIT | SCALE | POS | ROW | CELL | HEADER | LABEL | R1 | R2 | R3 | R4 | R5
    reason: str


def _unit_currency(unit: str) -> str | None:
    return unit.split("/")[0] if unit in CURRENCY_UNITS else None


def check_entry(entry: dict, sources: dict[str, dict], source_dir: Path) -> GateResult:
    for f in REQUIRED:
        if entry.get(f) in (None, ""):
            return GateResult(False, "FIELD", f"missing required field '{f}'")
    if entry["confidence"] not in ("low", "medium", "high"):
        return GateResult(False, "FIELD", f"confidence {entry['confidence']!r} not in low/medium/high")
    vt = str(entry["value_text"])
    try:
        v = float(entry["value"])
        v_from_text = float(vt.replace(",", ""))
    except (TypeError, ValueError):
        return GateResult(False, "FIELD", f"value {entry['value']!r} / value_text {vt!r} not numeric")
    scale_word = entry.get("scale_word")
    scale = 1.0
    if scale_word is not None:
        if scale_word not in SCALES:
            return GateResult(False, "SCALE", f"scale_word {scale_word!r} not in {sorted(SCALES)}")
        scale = SCALES[scale_word]
    if not math.isfinite(v) or v != v_from_text * scale:
        return GateResult(False, "FIELD", f"value {v!r} != value_text {vt!r} x {scale:g}")
    unit = entry["unit"]
    if unit not in CURRENCY_UNITS and unit not in PLAIN_UNITS and unit not in LCU_UNITS:
        return GateResult(False, "UNIT", f"unit {unit!r} not admissible")
    src = sources.get(entry["source"])
    if src is None:
        return GateResult(False, "SOURCE", f"source {entry['source']!r} not registered")
    fp = source_dir / src["file"]
    if not fp.exists():
        return GateResult(False, "SOURCE", f"source file missing: {fp}")
    raw = fp.read_bytes()
    if hashlib.sha256(raw).hexdigest() != src["sha256"]:
        return GateResult(False, "SOURCE", f"source file {fp.name} changed since registration (sha256 mismatch)")
    text = canon(raw.decode("utf-8"))
    span = canon(str(entry["quote_span"]))
    if span not in text:
        return GateResult(False, "R1", "quote_span not found in the source text")
    cvt = canon(vt)
    num = re.escape(cvt)
    # whole number only: not part of a longer number (10.2), and not a unit exponent or label digit
    # (the '2' of 'm2' / 'm-2', the '1' of 'Glass1'): no letter, digit, '.' or '-' directly before it.
    if not re.search(rf"(?<![0-9A-Za-z.\-]){num}(?![0-9])(?!\.[0-9])", span):
        return GateResult(False, "R2", f"value_text {vt!r} not found as a whole number inside quote_span")
    pos = entry.get("position")
    cells: list[str] = []
    if pos is not None:
        seg = span
        if pos.get("after"):
            a = canon(str(pos["after"]))
            if a not in seg:
                return GateResult(False, "POS", f"position anchor {pos['after']!r} not in span")
            seg = seg.split(a, 1)[1]
        cells = [c.strip() for c in (seg.split(pos["sep"]) if pos["sep"] != " " else seg.split())]
        i = int(pos["index"])
        if not 0 <= i < len(cells):
            return GateResult(False, "POS", f"position index {i} out of range ({len(cells)} cells)")
        if not re.match(rf"{num}(?![0-9])(?!\.[0-9])", cells[i]):
            return GateResult(False, "POS", f"cell {i} is {cells[i]!r}, does not start with {vt!r}")
        for j, want in (entry.get("row_cells") or {}).items():
            j = int(j)
            if not 0 <= j < len(cells) or cells[j] != canon(str(want)):
                return GateResult(False, "ROW", f"row cell {j} is {cells[j] if 0 <= j < len(cells) else None!r}, not {want!r}")
    cur = _unit_currency(unit)
    if unit in LCU_UNITS:
        lab = entry.get("label")
        blk = entry.get("block")
        if not lab or not entry.get("unit_basis") or not blk:
            return GateResult(False, "LABEL", f"{unit} value needs 'label', 'unit_basis' and 'block'")
        if not re.match(rf"{re.escape(canon(str(blk)))}(?![A-Za-z0-9_])", span):
            return GateResult(False, "LABEL", f"span does not start with block header {blk!r}")
        if not re.search(rf"{re.escape(canon(str(lab)))}\s?[+]?{num}(?![0-9])(?!\.[0-9])", span):
            return GateResult(False, "LABEL", f"label {lab!r} does not directly precede {vt!r} in the span")
        return GateResult(True, "OK", f"verified (label; unit per {entry['unit_basis'][:60]})")
    uc = entry.get("unit_cell")
    if uc is not None:
        if pos is None or cur is None or unit not in DENOMINATORS:
            return GateResult(False, "CELL", "unit_cell needs 'position' and a currency unit with a known denominator")
        j = int(uc["index"])
        if not 0 <= j < len(cells) or cells[j] != canon(str(uc["text"])):
            return GateResult(False, "CELL", f"cell {j} is {cells[j] if 0 <= j < len(cells) else None!r}, "
                                             f"not {uc['text']!r}")
        m = re.fullmatch(rf"({CURRENCY_TOKEN})\s?{DENOMINATORS[unit]}", canon(str(uc["text"])))
        if m is None:
            return GateResult(False, "CELL", f"unit cell {uc['text']!r} does not read <currency><denominator of {unit}>")
        if TOKEN_CURRENCY.get(m.group(1)) != cur:
            return GateResult(False, "R4", f"unit cell marks {TOKEN_CURRENCY.get(m.group(1))} but unit {unit} declares {cur}")
        return GateResult(True, "OK", "verified (unit from row cell)")
    uh = entry.get("unit_header")
    if uh is not None:
        h = canon(str(uh))
        k = span.find(h)
        vpos = re.search(rf"(?<![0-9A-Za-z.\-]){num}(?![0-9])(?!\.[0-9])", span)
        if cur is None or unit not in HEADER_DENOM:
            return GateResult(False, "HEADER", f"unit_header not supported for unit {unit}")
        if k < 0 or vpos is None or k > vpos.start():
            return GateResult(False, "HEADER", f"unit_header {uh!r} not in the span before the value")
        tok = re.search(CURRENCY_TOKEN, h)
        if tok is None or TOKEN_CURRENCY.get(tok.group(0)) != cur:
            return GateResult(False, "HEADER", f"unit_header {uh!r} has no {cur} currency token")
        if not re.search(HEADER_DENOM[unit], h, re.I):
            return GateResult(False, "HEADER", f"unit_header {uh!r} does not state the denominator of {unit}")
        if pos is not None and entry.get("header_index") != pos.get("index"):
            return GateResult(False, "HEADER", f"value is in cell {pos.get('index')} but the header is declared for "
                                               f"column {entry.get('header_index')!r}")
        return GateResult(True, "OK", "verified (unit from column header)")
    if cur is None and pos is None and not entry.get("unit_text"):
        return GateResult(False, "FIELD", f"plain-unit value ({unit}) needs 'position' or 'unit_text'")
    if scale_word is not None:
        if cur is None:
            return GateResult(False, "SCALE", "scale_word is only allowed on currency units")
        # \s* (not \s+): sources print both "20 million USD" and "11million US$" (Cai 2017 SI)
        m = re.search(rf"(?<![0-9.]){num}\s*{scale_word}\s?({CURRENCY_TOKEN})", span)
        if m is None:
            return GateResult(False, "SCALE", f"span does not read '{vt} {scale_word} <currency>'")
        tok_cur = TOKEN_CURRENCY.get(m.group(1))
        if tok_cur != cur:
            return GateResult(False, "R4", f"span marks {tok_cur} but unit {unit} declares {cur}")
        return GateResult(True, "OK", "verified")
    if cur is not None:
        pre = re.search(rf"({CURRENCY_TOKEN})\s?{num}(?![0-9])(?!\.[0-9])", span)
        suf = re.search(rf"(?<![0-9.]){num}\s?({CURRENCY_TOKEN})", span)
        m = pre or suf
        if m is None:
            return GateResult(False, "R3", f"value_text {vt!r} is not currency-marked in the span")
        tok_cur = TOKEN_CURRENCY.get(m.group(1))
        if tok_cur != cur:
            return GateResult(False, "R4", f"span marks {tok_cur} but unit {unit} declares {cur}")
        after = span[m.end():]
        if unit in DENOMINATORS:
            printed = entry.get("denominator_as_printed")
            if printed is not None:
                if not entry.get("denominator_note"):
                    return GateResult(False, "R5", "denominator_as_printed needs a denominator_note")
                if not re.match(rf"\s?{re.escape(canon(str(printed)))}", after):
                    return GateResult(False, "R5", f"printed denominator {printed!r} does not follow the value")
                return GateResult(True, "OK", f"verified (printed denominator {printed!r} differs from {unit}: "
                                              f"{entry['denominator_note']})")
            if not re.match(rf"\s?{DENOMINATORS[unit]}", after):
                return GateResult(False, "R5", f"span does not print the denominator of {unit} after the value "
                                               f"(next text: {after[:12]!r})")
        elif unit == "USD" and re.match(r"\s?(?:/|per\s)", after):
            return GateResult(False, "R5", f"unit USD but span prints a per-something price: {after[:12]!r}")
    elif entry.get("unit_text"):
        ut = re.escape(canon(str(entry["unit_text"])))
        if not re.search(rf"(?<![0-9.]){num}\s?{ut}", span):
            return GateResult(False, "R3", f"unit_text {entry['unit_text']!r} does not follow {vt!r} in the span")
    return GateResult(True, "OK", "verified")
