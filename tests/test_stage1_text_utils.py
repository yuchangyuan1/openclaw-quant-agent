from services.common.text import chunk_text, hashed_embedding, tokenize_text


def test_tokenize_text_mixed_language():
    tokens = tokenize_text("Apple Q1 profit growth 12%")
    assert "apple" in tokens
    assert "profit" in tokens


def test_hashed_embedding_is_deterministic():
    assert hashed_embedding("Apple quarterly growth", 32) == hashed_embedding("Apple quarterly growth", 32)


def test_chunk_text_splits_long_content():
    chunks = chunk_text("A" * 1000, chunk_size=300, overlap=50)
    assert len(chunks) >= 3
