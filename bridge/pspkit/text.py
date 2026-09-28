"""Text helpers for the PSP side, which renders a plain 8x8 ASCII font."""
import unicodedata

# Letters NFKD does not reduce to ASCII on its own.
_SPECIAL = str.maketrans({"ı": "i", "İ": "I", "ß": "ss", "æ": "ae", "Æ": "AE",
                          "ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D",
                          "“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-",
                          "…": "...", "•": "*", "\t": " "})


def to_psp(text: str, limit: int = 60) -> str:
    """Transliterates to printable ASCII ('Şarkı' -> 'Sarki'); newlines become '|'."""
    text = text.replace("\r\n", "\n").replace("\n", "|").translate(_SPECIAL)
    text = unicodedata.normalize("NFKD", text)
    out = "".join(ch for ch in text if 32 <= ord(ch) < 127)
    return out.strip()[:limit]
