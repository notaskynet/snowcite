"""Bibliography — BibTeX and Hayagriva generation."""

from snowcite.domain.bibliography import (
    build_cite_key_map,
    disambiguate_key,
    generate_bibtex,
    make_cite_key,
)


def test_make_cite_key_basic():
    assert make_cite_key(["John Smith"], 2024, "A Fancy Title") == "smith2024a"


def test_make_cite_key_no_authors_uses_title_fallback():
    # Without authors the prefix comes from the first meaningful title word,
    # not the legacy "unknown" sentinel.
    assert make_cite_key([], 2024, "Untitled draft") == "untitled2024untitled"


def test_make_cite_key_no_authors_skips_stopwords():
    # "The" / "a" etc. are skipped so the key stays informative.
    assert make_cite_key([], 2024, "The Fancy Paper") == "fancy2024the"


def test_make_cite_key_no_authors_no_title_is_anon():
    assert make_cite_key([], 2024, "") == "anon2024untitled"


def test_make_cite_key_no_year():
    assert make_cite_key(["Jane Doe"], None, "Some Paper") == "doendsome"


def test_disambiguate_collides():
    used: set[str] = set()
    a = disambiguate_key("smith2024a", used)
    b = disambiguate_key("smith2024a", used)
    c = disambiguate_key("smith2024a", used)
    assert a == "smith2024a"
    assert b == "smith2024aa"
    assert c == "smith2024ab"


def test_generate_bibtex_basic():
    entry = generate_bibtex(
        title="Adversarial Attacks",
        authors=["Jane Doe", "John Smith"],
        year=2024,
        venue="ICML",
        doi="10.1/foo",
        source="openalex",
    )
    assert "@article{doe2024adversarial," in entry
    assert "author = {Jane Doe and John Smith}" in entry
    assert "doi = {10.1/foo}" in entry


def test_generate_bibtex_arxiv_becomes_misc():
    entry = generate_bibtex(
        title="Preprint",
        authors=["Alice"],
        year=2023,
        venue="arxiv:2301.00001",
        source="arxiv",
    )
    assert entry.startswith("@misc{")
    assert "howpublished =" in entry


def test_generate_bibtex_escapes_special_chars():
    entry = generate_bibtex(
        title="20% of $N$ papers & counting",
        authors=["Author"],
        year=2024,
    )
    assert r"\%" in entry
    assert r"\$" in entry
    assert r"\&" in entry


def test_build_cite_key_map_by_id():
    entries = [
        {"id": 10, "title": "Paper A", "authors": ["Alice Smith"], "year": 2023},
        {"id": 11, "title": "Paper B", "authors": ["Bob Jones"], "year": 2024},
    ]
    m = build_cite_key_map(entries)
    assert m == {10: "smith2023paper", 11: "jones2024paper"}


def test_build_cite_key_map_disambiguates():
    # Two entries with identical author+year+first-title-word → second gets a suffix.
    entries = [
        {"id": 1, "title": "Review", "authors": ["Alice Smith"], "year": 2024},
        {"id": 2, "title": "Review", "authors": ["Alice Smith"], "year": 2024},
    ]
    m = build_cite_key_map(entries)
    assert m[1] == "smith2024review"
    assert m[2] == "smith2024reviewa"
