from services.common.text import chunk_text, hashed_embedding, tokenize_text


def test_tokenize_text_mixed_language():
    tokens = tokenize_text("贵州茅台 Q1 profit growth 12%")
    assert "贵" in tokens
    assert "州茅" in tokens
    assert "profit" in tokens


def test_hashed_embedding_is_deterministic():
    assert hashed_embedding("贵州茅台一季报增长", 32) == hashed_embedding("贵州茅台一季报增长", 32)


def test_chunk_text_splits_long_content():
    chunks = chunk_text("A" * 1000, chunk_size=300, overlap=50)
    assert len(chunks) >= 3
