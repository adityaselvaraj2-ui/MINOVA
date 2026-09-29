from __future__ import annotations

CHUNK_SIZE = 512
CHUNK_OVERLAP = 64


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[dict]:
    if not text.strip():
        return []

    words = text.split()
    chunks = []
    start_word = 0

    while start_word < len(words):
        end_word = min(start_word + chunk_size, len(words))
        chunk_words = words[start_word:end_word]
        chunk_text_str = " ".join(chunk_words)

        char_start = len(" ".join(words[:start_word])) + (1 if start_word > 0 else 0)
        char_end = char_start + len(chunk_text_str)

        chunks.append({
            "text": chunk_text_str,
            "char_start": char_start,
            "char_end": char_end,
            "token_count": len(chunk_words),
        })

        if end_word >= len(words):
            break
        start_word = end_word - overlap

    return chunks


def chunk_pages(pages: list[dict]) -> list[dict]:
    all_chunks = []
    for page_info in pages:
        page_num = page_info["page"]
        page_text = page_info["text"]
        page_chunks = chunk_text(page_text)
        for c in page_chunks:
            c["page_number"] = page_num
        all_chunks.extend(page_chunks)
    return all_chunks
