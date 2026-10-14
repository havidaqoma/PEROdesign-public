import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import openalex_http as OA  # noqa: E402


def test_key_only_on_openalex():
    k = "TESTKEY123"
    u = OA.keyed("https://api.openalex.org/works/https://doi.org/10.1/x?mailto=a@b.org", key=k)
    assert u.endswith("api_key=TESTKEY123") and "mailto=a%40b.org" in u
    for other in ("https://api.crossref.org/works/10.1/x", "https://doi.org/10.1/x",
                  "https://api.openalex.org.evil.com/works/x"):
        assert OA.keyed(other, key=k) == other


def test_no_key_leaves_url_and_single_key():
    u = "https://api.openalex.org/works/W1?api_key=old"
    assert OA.keyed(u, key="") == u
    assert OA.keyed(u, key="new").count("api_key=") == 1


def test_redact_and_budget_error_not_retried():
    assert "SECRET" not in OA.redact("x?api_key=SECRET", key="SECRET")
    assert not issubclass(OA.OpenAlexBudgetError, Exception)
