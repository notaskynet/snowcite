"""Abstract truncation helper — drives T1's "don't leak abstracts to context" rule."""

from snowcite.domain.models import Paper
from snowcite.domain.search import compact_paper, truncate_abstract


def test_truncate_none_passes_through():
    assert truncate_abstract(None, 100) is None


def test_truncate_zero_drops_field():
    assert truncate_abstract("some text", 0) is None


def test_truncate_shorter_than_limit():
    assert truncate_abstract("short", 100) == "short"


def test_truncate_longer_gets_ellipsis():
    result = truncate_abstract("a" * 500, 50)
    assert result is not None
    assert len(result) == 50
    assert result.endswith("…")


def test_truncate_trailing_whitespace_trimmed_before_ellipsis():
    result = truncate_abstract("word    " + "x" * 100, 10)
    assert result is not None
    assert not result[:-1].endswith(" ")  # no orphan whitespace before ellipsis


def _paper(abstract: str | None) -> Paper:
    return Paper(source="arxiv", source_id="x1", title="Any", abstract=abstract)


def testcompact_paper_drops_abstract_by_default():
    p = _paper("Some long abstract here")
    d = compact_paper(p, 0)
    assert d["abstract"] is None


def testcompact_paper_truncates_when_limit_given():
    p = _paper("a" * 200)
    d = compact_paper(p, 40)
    assert d["abstract"] is not None
    assert len(d["abstract"]) == 40
