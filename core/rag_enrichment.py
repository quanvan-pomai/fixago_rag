"""
core/rag_enrichment.py
Converts symptom descriptions into canonical repair phrases before RAG lookup.
e.g. "nước cứ rỉ dưới bồn rửa" → "nước rỉ dưới bồn rửa rò rỉ nước ống nước"
"""
import re

_SYMPTOM_REWRITES = [
    (r'rỉ.{0,8}(nước|bồn|vòi|lavabo|ống)',            "rò rỉ nước ống nước"),
    (r'(bồn cầu|toilet).{0,10}(nghẹt|tắc)',            "tắc nghẹt bồn cầu ống thoát"),
    (r'nước.{0,6}(chảy yếu|yếu|không lên)',            "áp lực nước yếu ống nước"),
    (r'(điện|cầu dao).{0,8}(nhảy|hay nhảy)',           "nhảy cầu dao aptomat sự cố điện"),
    (r'(chập|tóe lửa|cháy|hở).{0,8}điện',             "chập điện sự cố điện"),
    (r'(điều hòa|máy lạnh).{0,10}(không mát|lạnh yếu)', "máy lạnh không lạnh nạp gas"),
    (r'(điều hòa|máy lạnh).{0,8}(nhỏ giọt|chảy nước)',  "máy lạnh nhỏ giọt tắc ống thoát"),
    (r'tường.{0,10}(thấm|ẩm|mốc)',                    "thấm dột tường chống thấm"),
    (r'(mái|nhà).{0,8}dột',                            "dột mái chống thấm"),
    (r'(sơn|tường).{0,8}(bong|bong tróc|bạc màu)',     "sơn tường bong tróc sơn lại"),
    # No-accent variants
    (r'nuoc.{0,6}(ri|chay yeu)',                       "rò rỉ nước ống nước"),
    (r'dien.{0,8}(nhay|chap)',                         "điện sự cố nhảy cầu dao"),
    (r'may lanh.{0,10}(khong mat|khong lanh)',         "máy lạnh không lạnh"),
]


def rewrite_for_rag(query: str, detected_intent: str | None) -> str:
    """
    Enrich the user query with canonical repair keywords before RAG retrieval.
    Returns the enriched string (or original if no rewrite applies).
    """
    q = query.strip()

    canonical_kw = ""
    if detected_intent and "get_services" in detected_intent:
        m = re.search(r'search="([^"]*)"', detected_intent)
        if m:
            canonical_kw = m.group(1)

    q_lower = q.lower()
    for pattern, phrase in _SYMPTOM_REWRITES:
        if re.search(pattern, q_lower):
            if phrase not in q_lower:
                q = q + " " + phrase
            break

    if canonical_kw and canonical_kw not in q.lower():
        q = canonical_kw + " " + q

    return q
