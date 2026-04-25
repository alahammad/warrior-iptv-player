import re
import unicodedata
from difflib import SequenceMatcher

_STOPWORDS_PREFIX = ("the ", "a ", "an ", "ال")
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)
_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]")
_ARABIC_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ئ": "ي", "ي": "ي",
    "ؤ": "و",
    "ة": "ه",
    "ک": "ك", "گ": "ك",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
})


def normalize(text: str) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text).lower()
    t = _ARABIC_DIACRITICS.sub("", t)
    t = t.translate(_ARABIC_MAP)
    # Strip Latin combining marks (accents) after NFKD decomposition of non-Arabic letters
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    t = _NON_WORD.sub(" ", t).strip()
    while True:
        for sw in _STOPWORDS_PREFIX:
            if t.startswith(sw) and len(t) > len(sw):
                t = t[len(sw):].lstrip()
                break
        else:
            break
    return re.sub(r"\s+", " ", t)


def score(query: str, title: str) -> float:
    """Return a relevance score in [0, 100]. Higher is better. 0 means no match."""
    if not query or not title:
        return 0.0
    q_norm = normalize(query)
    t_norm = normalize(title)
    if not q_norm or not t_norm:
        return 0.0

    if q_norm == t_norm:
        return 100.0

    q_tokens = q_norm.split(" ")
    t_tokens = t_norm.split(" ")
    t_joined = " ".join(t_tokens)

    # Contiguous substring match (e.g., "god father" inside "godfather" via joined-no-space variant)
    q_packed = q_norm.replace(" ", "")
    t_packed = t_norm.replace(" ", "")

    if q_norm in t_joined:
        base = 85.0
        if t_joined.startswith(q_norm):
            base += 6.0
        return base - min(10.0, max(0, len(t_packed) - len(q_packed)) * 0.05)

    if q_packed and q_packed in t_packed:
        base = 70.0
        if t_packed.startswith(q_packed):
            base += 6.0
        return base - min(10.0, max(0, len(t_packed) - len(q_packed)) * 0.05)

    present = 0
    prefix_hits = 0
    for qt in q_tokens:
        for tt in t_tokens:
            if tt.startswith(qt):
                prefix_hits += 1
                present += 1
                break
            if qt in tt:
                present += 1
                break

    if present == len(q_tokens):
        ratio = present / max(1, len(t_tokens))
        return 55.0 + 10.0 * ratio + 3.0 * prefix_hits

    if present:
        partial = present / len(q_tokens)
        return 20.0 + 25.0 * partial

    fuzzy = SequenceMatcher(None, q_packed, t_packed).ratio()
    if fuzzy >= 0.72:
        return 10.0 + 25.0 * fuzzy
    return 0.0


def rank(query: str, items: list, title_of, *, min_score: float = 30.0, limit: int | None = None):
    if not query:
        return list(items)
    scored: list[tuple[float, int, object]] = []
    for idx, item in enumerate(items):
        s = score(query, title_of(item))
        if s >= min_score:
            scored.append((s, idx, item))
    scored.sort(key=lambda x: (-x[0], x[1]))
    result = [it for _, _, it in scored]
    if limit is not None:
        result = result[:limit]
    return result
