from services.common.stocks import (
    extract_company_terms,
    matches_company_terms,
    normalize_company_term,
)


def test_normalize_company_term_strips_us_corporate_suffix():
    assert normalize_company_term("Apple Inc.") == "apple"
    assert normalize_company_term("Microsoft Corporation") == "microsoft"


def test_extract_company_terms_supports_non_pool_company():
    terms = extract_company_terms("Palantir Technologies earnings update")
    assert terms[0] == "Palantir Technologies"
    assert "Palantir" in terms


def test_matches_company_terms_uses_normalized_company_name():
    text = "Apple Inc. filed its latest annual report with the SEC."
    assert matches_company_terms(text, ["Apple"])
