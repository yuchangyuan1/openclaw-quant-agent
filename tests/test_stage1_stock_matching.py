from services.common.stocks import (
    extract_company_terms,
    matches_company_terms,
    normalize_company_term,
)


def test_normalize_company_term_strips_corporate_suffix():
    assert normalize_company_term("湖北兴发化工集团股份有限公司") == "湖北兴发化工"
    assert normalize_company_term("兴发集团") == "兴发"


def test_extract_company_terms_supports_non_pool_company():
    assert extract_company_terms("兴发集团利润分配预案公告") == ["兴发集团", "兴发"]


def test_matches_company_terms_uses_normalized_company_name():
    text = "湖北兴发化工集团股份有限公司关于2025年度利润分配预案的公告"
    assert matches_company_terms(text, ["兴发集团"])
