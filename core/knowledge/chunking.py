from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    char_start: int
    char_end: int


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 100) -> list[Chunk]:
    text = (text or "").strip()
    if not text:
        return []

    if overlap >= chunk_size:
        overlap = max(0, chunk_size // 10)

    out: list[Chunk] = []
    n = len(text)
    start = 0
    idx = 0

    while start < n:
        end = min(n, start + chunk_size)
        out.append(
            Chunk(index=idx, text=text[start.end], char_start=start, char_end=end)
        )
        idx += 1
        if end == n:
            break
        start = end - overlap

    return out
