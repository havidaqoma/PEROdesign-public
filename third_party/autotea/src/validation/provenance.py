"""The provenance gate. The mechanism this entire product rests on.

`docs/PRD.md` 5.3 states the contract this module enforces:

    A cost value may enter the model only with a `value`, a `unit`, a
    `distribution`, a `source`, a verbatim `quote_span`, a publication year, a
    cost-basis year, a geography and a confidence. The model may only SELECT a
    number that literally appears in a retrieved snippet, and a deterministic
    validator re-checks the numeric string against the quote text. Nothing
    verifiable means the job stops and asks. A silent default is never allowed.

The rule that makes the product safe: the language model may choose WHICH
retrieved snippet is relevant. It may never author the number. Every number is
re-checked against text that was actually fetched, by code, not by a prompt.

Four INDEPENDENT rules. Each is separately reachable and separately tested,
because a gate whose rules have never individually fired is not a tested gate:

    R1  the quote_span appears literally in the retrieved source text
    R2  the declared value appears inside that same quote_span
    R3  the value is currency-marked where it appears, so a value cannot be
        "verified" by coincidentally matching an unrelated integer
    R4  the marking currency MATCHES the currency of the declared unit, so
        "170 EUR/MWh" cannot be booked as USD/MWh

No one rule suffices. R1 alone: a model could cite a real span while declaring a
different number. R2 alone: the span itself could be invented. R3 alone:
"400MWh" contains the integer 400. R4 covers silent currency substitution, which
is the "reject on mismatch rather than silently converting" principle from the
operating rules expressed as code.

R3 and R4 were both changed after the gate was run against a real peer-reviewed
paper rather than against hand-written US-style test data. See the notes on
`_currency_marked` and `_unit_currency`.

SOURCE provenance is required on every entry, in one of two forms: an inline
`source_url`, or a `source` key naming an entry in a caller-supplied registry.
`data/anchor_published.json` uses the registry form so one source block is not
repeated across nine values. This module performs NO I/O, so it cannot itself
resolve a registry key: the caller resolves it and is responsible for asserting
the key exists. `scripts/common/verify_anchor_spans.py` enforces that, which
keeps this gate pure and testable while still refusing an entry that names no
source at all.

Text normalisation (NFKC, curly quotes, non-breaking spaces, collapsed
whitespace) exists because the HTML-to-text path can introduce all of them. If a
genuine value is refused, the fix is the normaliser, NEVER the quote. Editing a
quote to match the number is the single most dangerous failure mode here.

KNOWN LIMITATION, deliberate: currency marking is checked by ADJACENCY, so a
shared-unit enumeration such as "between 170 and 350 USD/MWh" refuses the 170.
A human reads that sentence correctly; a deterministic adjacency check cannot
establish which numbers the unit governs, so the gate refuses and the job
escalates. That is the safe direction: the alternative failure mode is a
silently mis-united number inside a paid report. Relaxing this needs a parsed
grammar, not a wider regex.
"""
from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple

# Rules 5.3 declares mandatory. `distribution` and `publication_year` are here
# because the contract lists them and this module is the reference
# implementation of that contract; a gate weaker than its own specification is
# worse than no gate, since it manufactures false confidence.
#
# Source provenance is NOT in this tuple: it is checked by the SOURCE rule below,
# because it may be supplied either inline or via a registry key.
REQUIRED_FIELDS = (
    "id",
    "value",
    "unit",
    "distribution",
    "metric",
    "geography",
    "publication_year",
    "cost_basis_year",
    "quote_span",
    "confidence",
)

# Units the cost model accepts. Anything else must be converted deliberately and
# recorded, never silently coerced.
ADMISSIBLE_UNITS = frozenset({"USD/MWh", "USD/kWh", "USD/m2", "USD/kW"})

# Real units that the model cannot use YET, because using them requires an FX rate
# with a date that has itself been sourced. Separated from ADMISSIBLE_UNITS so the
# refusal message is actionable instead of "not admissible": a customer ordering
# from Malaysia or Indonesia will bring MYR, IDR and EUR sources, and the operator
# needs to know the difference between "we need an FX policy" and "this is not a
# cost unit at all".
KNOWN_UNITS_NEEDING_FX = frozenset(
    {"EUR/MWh", "EUR/kWh", "GBP/MWh", "CNY/MWh", "JPY/MWh", "MYR/kWh", "IDR/kWh"}
)

_CONFIDENCE = frozenset({"low", "medium", "high"})

# Characters the extractor can leave behind, mapped to their plain equivalents.
_SQUASH = {
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-",
    "\u00a0": " ", "\u202f": " ", "\u2009": " ", "\ufeff": "",
}


class GateResult(NamedTuple):
    """`rule` identifies which check fired, so tests assert the REASON.

    Asserting only `ok is False` cannot tell a rule that fired from a rule that
    was merely shadowed by an earlier one -- which is how a gate reports
    "refused everything" while half its checks are dead code.
    """

    ok: bool
    rule: str  # OK | FIELD | SOURCE | UNIT | CONFIDENCE | R1 | R2 | R3 | R4
    reason: str


def normalize_text(text: str) -> str:
    """Canonical form for containment tests. Whitespace-insensitive."""
    text = unicodedata.normalize("NFKC", text)
    for bad, good in _SQUASH.items():
        text = text.replace(bad, good)
    return re.sub(r"\s+", " ", text).strip()


def _strip_separators(text: str) -> str:
    """Drop thousands separators so '1,471' and '1471' compare equal."""
    return text.replace(",", "")


def canon(text: str) -> str:
    """Public canonical form: NFKC, squashed quotes, thousands separators gone.

    Public because `src/params/fx.py` must canonicalise text EXACTLY as this
    gate does. Two independent normalisers would drift, and a drifted
    normaliser is how a genuine value silently stops matching its span.
    """
    return _strip_separators(normalize_text(text))


def value_forms(value: float) -> tuple[str, ...]:
    """Spellings of the number that count as a literal appearance.

    ROUND-TRIPPING, NOT ROUNDED. This used `f"{value:g}"`, whose default
    precision is SIX significant figures, so a declared 1.1299831372549 produced
    only the form "1.13" and matched no span containing the real figure. A gate
    that refuses a correctly-cited value is the expensive failure mode: it looks
    like the source is wrong, and the temptation is to edit the quote. Found
    while adding the FX policy, which is the first value in this repo that is not
    a round number.

    `repr` is the shortest string that round-trips to the same float, so the form
    is exact. The trailing ".0" is stripped so an integral 170.0 still offers the
    integer spelling "170" that appears in prose.

    An integral value additionally offers its thousands-separated spelling
    ("1,471"), because that is how a cost appears in a report. The rounded form
    is deliberately NOT offered: `f"{1.5:,.0f}"` == "2" would let the string "2"
    verify a declared 1.5, which is the coincidence rule R3 exists to stop.
    """
    text = repr(float(value))
    if text.endswith(".0"):
        text = text[:-2]
    forms = {text}
    if float(value).is_integer():
        forms.add(f"{int(value)}")
        forms.add(f"{int(value):,}")
    return tuple(_strip_separators(f) for f in forms)


# Retained under the original private names so this module's own call sites and
# every existing test keep working untouched.
_canon = canon
_value_forms = value_forms


# Currency tokens, longest first so "US$" is not read as "USD".
_CURRENCY_TOKEN = r"(?:US\$|USD|EUR|GBP|CNY|JPY|\$|\u20ac|\u00a3|\u00a5)"

# Which currency each token denotes.
_TOKEN_CURRENCY = {
    "US$": "USD", "USD": "USD", "$": "USD",
    "EUR": "EUR", "\u20ac": "EUR",
    "GBP": "GBP", "\u00a3": "GBP",
    "CNY": "CNY", "JPY": "JPY", "\u00a5": "JPY",
}

# Currency implied by a declared unit such as "USD/MWh".
#
# This covers the FX-needing units as well as the admissible ones, and that is
# deliberate. Rule R4's job is "does the currency written in the span match the
# currency the unit declares?". Answering it needs a currency for EVERY unit the
# gate can be asked about. Before the FX policy existed, only USD units reached
# R4, so a shorter table was equivalent. With `verify_fx_units=True` a EUR/MWh
# value now reaches R4, and a table that returned None there would report
# `mismatch: span marks EUR but the unit declares None` -- refusing a correct
# citation for the wrong reason. The admissibility split lives in the UNIT check
# (ADMISSIBLE_UNITS vs KNOWN_UNITS_NEEDING_FX), not here.
_UNIT_CURRENCY = {
    "USD/MWh": "USD", "USD/kWh": "USD", "USD/m2": "USD", "USD/kW": "USD",
    "EUR/MWh": "EUR", "EUR/kWh": "EUR",
    "GBP/MWh": "GBP", "CNY/MWh": "CNY", "JPY/MWh": "JPY",
    "MYR/kWh": "MYR", "IDR/kWh": "IDR",
}


def _currency_marked(forms: tuple[str, ...], span: str) -> str | None:
    """Return the currency token attached to the value, or None.

    Adjacency is allowed on EITHER side. The prefix form is the US convention
    ("$170"); the suffix form is the international and academic convention
    ("180 EUR/MWh", "350 USD/MWh"). The first version of this gate required a
    prefix only, which would have REFUSED correctly cited figures from real
    literature while passing a hand-written US-style fixture. That was found by
    running the gate against a peer-reviewed paper, not by reading the code.

    Adjacency permits whitespace only, so "170, 180 USD/MWh" does NOT mark the
    170 (a comma is not whitespace) and "400MWh" carries no token at all.

    NUMBER BOUNDARIES ARE LOAD-BEARING. Without them the prefix test admits a
    wrong number: value `17.0` is "verified" by the span `US$170/MWh`, because
    `US$17` is a literal prefix of it. The same hole admits `1.5` from
    `US$1.50/MWh`. Both were found by an adversarial probe against this function,
    not by reading it. The lookaheads/lookbehinds below close them.
    """
    for f in forms:
        esc = re.escape(f)
        # PREFIX ("$170"). The number must not continue into a longer number, and
        # must not be the fractional tail of one.
        m = re.search(_CURRENCY_TOKEN + r"\s?" + esc + r"(?![0-9.,])", span)
        if m:
            return m.group(0)[: -len(f)].strip()
        # SUFFIX ("180 EUR"). Same requirement, enforced before the number too, so
        # the "170" inside "1170 USD" cannot mark itself.
        m = re.search(r"(?<![0-9.])" + esc + r"\s?" + _CURRENCY_TOKEN, span)
        if m:
            return m.group(0)[len(f):].strip()
    return None


def _unit_currency(unit: str) -> str | None:
    """Currency implied by a declared unit, or None if the unit is unusable."""
    return _UNIT_CURRENCY.get(unit)


def _token_currency(token: str) -> str | None:
    return _TOKEN_CURRENCY.get(token)


def validate_value(entry: dict, source_text: str, *,
                   verify_fx_units: bool = False) -> GateResult:
    """The runtime gate. Decides whether one cost value may enter the model.

    `verify_fx_units` exists for exactly one caller: the FX policy in
    `src/params/fx.py`. It changes WHICH QUESTION is being asked, not how strict
    the answer is, and the distinction is load-bearing:

        default (False)      "may this number enter the model AS IS?"
                             A EUR/MWh value is refused at UNIT, because the
                             model works in USD and converting silently is the
                             failure mode rule R4 exists to prevent.

        True                 "is this number's PROVENANCE CHAIN sound?"
                             The four rules R1-R4 still run unchanged, so a
                             fabricated span, an absent value or a mismatched
                             marker is still refused. Only the admissibility of
                             the unit is deferred, because the caller has stated
                             it will convert and re-record the result.

    Without this flag the FX policy would have to either loosen R4 (which would
    let a EUR number be booked as USD) or re-implement R1-R4 privately (two
    normalisers that drift). Both are worse than one honest parameter. The
    returned OK means "chain verified, conversion still REQUIRED before use" --
    it is never permission to use the value directly.
    """
    for field in REQUIRED_FIELDS:
        if field not in entry or entry[field] in ("", None):
            return GateResult(False, "FIELD", f"missing required field '{field}'")

    # SOURCE -- every value must name where it came from. Either inline, or via a
    # registry key the caller resolves. A number with no traceable origin is the
    # exact failure this whole module exists to prevent, so it is refused here
    # rather than at report time.
    if not entry.get("source_url") and not entry.get("source"):
        return GateResult(
            False, "SOURCE",
            "no source: give 'source_url', or a registry key in 'source'",
        )

    needs_fx = entry["unit"] in KNOWN_UNITS_NEEDING_FX
    if entry["unit"] not in ADMISSIBLE_UNITS and not (verify_fx_units and needs_fx):
        if needs_fx:
            return GateResult(
                False, "UNIT",
                f"unit '{entry['unit']}' needs an FX rate with a sourced date; "
                f"the model works in USD and will not convert silently",
            )
        return GateResult(False, "UNIT", f"unit '{entry['unit']}' is not admissible")

    if entry["confidence"] not in _CONFIDENCE:
        return GateResult(
            False, "CONFIDENCE",
            f"confidence '{entry['confidence']}' not one of {sorted(_CONFIDENCE)}",
        )

    try:
        value = float(entry["value"])
    except (TypeError, ValueError):
        return GateResult(False, "FIELD", f"value {entry['value']!r} is not numeric")

    span = _canon(str(entry["quote_span"]))
    source = _canon(str(source_text))

    # R1 -- the span must literally exist in what was actually retrieved.
    if span not in source:
        return GateResult(False, "R1", "quote_span not found in the source text")

    # R2 -- the declared value must appear inside its OWN span.
    forms = _value_forms(value)
    if not any(f in span for f in forms):
        return GateResult(
            False, "R2", f"value {value:g} does not appear inside its own quote_span"
        )

    # R3 -- and be currency-marked there, so an unrelated integer cannot pass.
    token = _currency_marked(forms, span)
    if token is None:
        return GateResult(
            False, "R3",
            f"value {value:g} is present but not currency-marked in the span",
        )

    # R4 -- the marking currency must MATCH the currency of the declared unit.
    mark_cur = _token_currency(token)
    unit_cur = _unit_currency(str(entry["unit"]))
    if mark_cur is None:
        return GateResult(False, "R4", f"unrecognised currency token {token!r}")
    if mark_cur != unit_cur:
        return GateResult(
            False, "R4",
            f"currency mismatch: the span marks {mark_cur} but the unit "
            f"declares {unit_cur}",
        )

    return GateResult(True, "OK", "verified")


def validate_all(entries: list[dict], source_text: str) -> list[tuple[str, GateResult]]:
    """Validate a list of entries. Returns (id, result) pairs in input order."""
    return [
        (str(e.get("id", f"<entry {i}>")), validate_value(e, source_text))
        for i, e in enumerate(entries)
    ]
