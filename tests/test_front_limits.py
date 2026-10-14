import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import front_limits as FL  # noqa: E402

MD = ("---\ntitle: x\n---\n\n# Abstract {-}\n\n{a}\n\n**Keywords:** a; b\n\n# Broader context {-}\n\n{b}\n\n"
      "# Introduction\n\nText.\n")


def doc(na, nb, nl="\n"):
    return MD.replace("{a}", " ".join(["w"] * na)).replace("{b}", " ".join(["w"] * nb)).replace("\n", nl)


def test_counts_at_limit_pass_and_keywords_excluded():
    assert FL.check(doc(250, 200)) == {"Abstract": 250, "Broader context": 200}


def test_crlf_input_counts_the_same():
    assert FL.check(doc(250, 200, "\r\n")) == {"Abstract": 250, "Broader context": 200}


@pytest.mark.parametrize("na,nb", [(251, 10), (10, 201)])
def test_over_limit_fails(na, nb):
    with pytest.raises(SystemExit, match="FRONT FAIL"):
        FL.check(doc(na, nb))


def test_missing_or_empty_section_fails_closed():
    with pytest.raises(SystemExit, match="no '# Broader context'"):
        FL.check(doc(10, 10).replace("# Broader context {-}", "# Context"))
    with pytest.raises(SystemExit, match="is empty"):
        FL.check(doc(10, 0))
