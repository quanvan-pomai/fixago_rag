"""
tools/handlers.py
-----------------
Executes the three read-only Fixago tools by calling the backend API.
Responses are formatted directly (no LLM round-trip) for speed.
LLM summarization is only used as a fallback when the response needs
free-form prose (e.g. when backend data is rich/unexpected).

Caching strategy:
  Services and groups change rarely → cached in PomaiCache with a long TTL.
  Cache key: "svc_cache:<search_arg>" / "grp_cache" / "promo_cache"
  TTL: 30 min for services/groups, 10 min for promotions (may change more often).
  On cache miss: fetch from backend, store result.
  Cache is injected at module level via init_cache(); falls back to no-cache if not set.
"""
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import requests


@dataclass
class FetchResult:
    """Wraps a backend fetch — distinguishes empty data from API error."""
    ok: bool
    data: list = field(default_factory=list)
    error: str = ""

logger = logging.getLogger("fixago.tools_handlers")

# Lazy import to avoid circular deps — tracer is always available after core/
def _audit(tool_name: str, result: "FetchResult", cache_hit: bool, t0: float):
    try:
        from core.tracer import audit_tool
        audit_tool(
            tool_name=tool_name,
            fetch_ok=result.ok,
            item_count=len(result.data),
            cache_hit=cache_hit,
            latency_ms=round((time.time() - t0) * 1000, 1),
            error_type=result.error if not result.ok else "",
        )
    except Exception:
        pass

BACKEND_URL = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:3001/api/v1")

# ── Cache injection ───────────────────────────────────────────────────────────
# Populated by server.py after rag_engine is initialized.
_cache = None

def init_cache(cache_store) -> None:
    """Inject the shared PomaiCache instance so handlers can cache API responses."""
    global _cache
    _cache = cache_store

_SVC_TTL_MS   = 30 * 60 * 1000   # 30 minutes — services rarely change
_GRP_TTL_MS   = 30 * 60 * 1000   # 30 minutes
_PROMO_TTL_MS = 10 * 60 * 1000   # 10 minutes — promos change more often


def _cache_get(key: str) -> Optional[List]:
    """Return cached JSON list, or None on miss/error."""
    if _cache is None:
        return None
    try:
        val = _cache.get(key)
        if val:
            return json.loads(val.decode("utf-8"))
    except Exception:
        pass
    return None


def _cache_set(key: str, data: List, ttl_ms: int) -> None:
    """Store a JSON-serialisable list in the cache."""
    if _cache is None:
        return
    try:
        _cache.set(key, json.dumps(data, ensure_ascii=False).encode("utf-8"), ttl_ms=ttl_ms)
    except Exception as exc:
        logger.debug("cache_set failed for %s: %s", key, exc)


# ── Price formatting helper ───────────────────────────────────────────────────

def _fmt_vnd(value) -> str:
    try:
        n = int(float(value))
    except Exception:
        n = 0
    return f"{n:,}".replace(",", ".") + " VNĐ"


def _build_price_summary(services: List[Dict]) -> str:
    priced, quote_required = [], []
    for s in services:
        price = int(float(s.get("unitPrice") or 0))
        item  = {"name": s.get("name", "Dịch vụ"), "price": price,
                 "time": s.get("estimatedTime") or 0}
        (priced if price > 0 else quote_required).append(item)

    if not priced and not quote_required:
        return ""

    lines = []
    if priced:
        prices = [x["price"] for x in priced]
        lo, hi = min(prices), max(prices)
        lines.append(
            f"Giá tham khảo: {_fmt_vnd(lo)}."
            if lo == hi else
            f"Khoảng giá tham khảo: {_fmt_vnd(lo)} - {_fmt_vnd(hi)}."
        )
        lines.append("Một số dịch vụ phù hợp:")
        for item in priced[:5]:
            t = f", thời gian khoảng {item['time']} phút" if item["time"] else ""
            lines.append(f"- {item['name']}: {_fmt_vnd(item['price'])}{t}.")

    if quote_required:
        names = ", ".join(x["name"] for x in quote_required[:3])
        lines.append(f"Một số hạng mục như {names} cần khảo sát để báo giá chính xác.")

    return "\n".join(lines)


# ── Raw data fetchers (cached → backend) ─────────────────────────────────────

def fetch_raw_groups() -> FetchResult:
    """Return raw group list. Served from cache when available."""
    t0 = time.time()
    cache_key = "grp_cache"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug("cache HIT: %s", cache_key)
        r = FetchResult(ok=True, data=cached)
        _audit("get_groups", r, cache_hit=True, t0=t0)
        return r

    try:
        resp = requests.get(f"{BACKEND_URL}/services/groups", timeout=3)
        if resp.status_code == 200:
            data = resp.json() or []
            _cache_set(cache_key, data, _GRP_TTL_MS)
            r = FetchResult(ok=True, data=data)
        else:
            r = FetchResult(ok=False, error=f"HTTP {resp.status_code}")
    except Exception as exc:
        logger.warning("fetch_raw_groups error: %s", exc)
        r = FetchResult(ok=False, error=str(exc))
    _audit("get_groups", r, cache_hit=False, t0=t0)
    return r


def fetch_raw_services(search_arg: str) -> FetchResult:
    """
    Return raw service list for search_arg. Served from cache when available.
    search_arg="all" fetches a broad sample across multiple categories.
    """
    t0 = time.time()
    cache_key = f"svc_cache:{search_arg}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug("cache HIT: %s", cache_key)
        r = FetchResult(ok=True, data=cached)
        _audit("get_services", r, cache_hit=True, t0=t0)
        return r

    try:
        if search_arg == "all":
            all_services: List[Dict] = []
            for keyword in ["điện", "nước", "máy lạnh", "xây dựng"]:
                resp = requests.get(
                    f"{BACKEND_URL}/services",
                    params={"search": keyword, "limit": 3, "isActive": True},
                    timeout=3,
                )
                if resp.status_code == 200:
                    all_services.extend(resp.json().get("data", []))
            _cache_set(cache_key, all_services, _SVC_TTL_MS)
            r = FetchResult(ok=True, data=all_services)
            _audit("get_services", r, cache_hit=False, t0=t0)
            return r

        resp = requests.get(
            f"{BACKEND_URL}/services",
            params={"search": search_arg, "limit": 10},
            timeout=3,
        )
        if resp.status_code == 200:
            services = resp.json().get("data", [])
            # Fallback: appliance types share the "điện" group
            if not services and search_arg in {"máy lạnh", "điện lạnh", "máy giặt"}:
                fb = requests.get(
                    f"{BACKEND_URL}/services",
                    params={"search": "điện", "limit": 10},
                    timeout=3,
                )
                if fb.status_code == 200:
                    services = fb.json().get("data", [])
            _cache_set(cache_key, services, _SVC_TTL_MS)
            r = FetchResult(ok=True, data=services)
        else:
            r = FetchResult(ok=False, error=f"HTTP {resp.status_code}")
    except Exception as exc:
        logger.warning("fetch_raw_services error: %s", exc)
        r = FetchResult(ok=False, error=str(exc))
    _audit("get_services", r, cache_hit=False, t0=t0)
    return r


def fetch_raw_promotions() -> FetchResult:
    """Return raw promotion list. Served from cache when available."""
    t0 = time.time()
    cache_key = "promo_cache"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug("cache HIT: %s", cache_key)
        r = FetchResult(ok=True, data=cached)
        _audit("get_promotions", r, cache_hit=True, t0=t0)
        return r

    try:
        resp = requests.get(f"{BACKEND_URL}/discounts/available", timeout=3)
        if resp.status_code == 200:
            raw  = resp.json()
            data = raw if isinstance(raw, list) else raw.get("data", [])
            _cache_set(cache_key, data, _PROMO_TTL_MS)
            r = FetchResult(ok=True, data=data)
        else:
            r = FetchResult(ok=False, error=f"HTTP {resp.status_code}")
    except Exception as exc:
        logger.warning("fetch_raw_promotions error: %s", exc)
        r = FetchResult(ok=False, error=str(exc))
    _audit("get_promotions", r, cache_hit=False, t0=t0)
    return r


def _fmt(price: int) -> str:
    return f"{price:,}".replace(",", ".") + " VNĐ"


def format_services_for_llm(services: List[Dict], search_arg: str = "") -> str:
    """
    Convert raw service list into a compact, LLM-readable fact block.
    Includes a price range summary so the LLM can lead with it.
    When search_arg='all', groups output by service category.
    """
    if not services:
        return f"Không tìm thấy dịch vụ khớp với '{search_arg}' trong hệ thống."

    priced   = [s for s in services if int(float(s.get("unitPrice") or 0)) > 0]
    unpriced = [s for s in services if int(float(s.get("unitPrice") or 0)) == 0]

    header = "Tổng quan giá dịch vụ Fixago:" if search_arg == "all" else f"Dịch vụ {search_arg} — dữ liệu từ hệ thống:"
    lines = [header]

    # Price range summary — lead with this for price questions
    if priced:
        prices = [int(float(s.get("unitPrice") or 0)) for s in priced]
        lo, hi = min(prices), max(prices)
        if lo == hi:
            lines.append(f"Giá tham khảo: {_fmt(lo)}")
        else:
            lines.append(f"Khoảng giá tham khảo: {_fmt(lo)} – {_fmt(hi)}")

    # Individual items (limit to keep prompt short for 3B model)
    limit = 10 if search_arg == "all" else 8
    for s in services[:limit]:
        price = int(float(s.get("unitPrice") or 0))
        name  = s.get("name", "Dịch vụ")
        time_ = s.get("estimatedTime") or 0
        price_str = _fmt(price) if price > 0 else "Báo giá thực tế"
        time_str  = f", ~{time_} phút" if time_ else ""
        lines.append(f"- {name}: {price_str}{time_str}")

    if unpriced:
        names = ", ".join(s.get("name", "") for s in unpriced[:3])
        lines.append(f"Hạng mục cần khảo sát thực tế: {names}.")

    lines.append("(Giá trên là tham khảo; thợ báo chính xác trước khi làm.)")
    return "\n".join(lines)


def format_services_direct(services: List[Dict], search_arg: str = "", lang: str = "vi") -> str:
    """
    Build a complete, ready-to-send price answer — NO LLM needed.
    Used when we have real price data and want a deterministic response.
    """
    if not services:
        if lang == "en":
            return (
                f"We don't have detailed pricing for '{search_arg}' in the system yet. "
                "A technician can visit and provide an exact quote before any work begins. "
                "Would you like to book an appointment?"
            )
        return (
            f"Dạ hiện mình chưa có bảng giá chi tiết cho '{search_arg}'. "
            "Fixago có thể cử thợ đến kiểm tra và báo chi phí chính xác trước khi làm. "
            "Bạn muốn đặt lịch không ạ?"
        )

    priced   = [s for s in services if int(float(s.get("unitPrice") or 0)) > 0]
    unpriced = [s for s in services if int(float(s.get("unitPrice") or 0)) == 0]

    if lang == "en":
        parts = []
        if priced:
            prices = [int(float(s["unitPrice"])) for s in priced]
            lo, hi = min(prices), max(prices)
            range_str = _fmt(lo) if lo == hi else f"{_fmt(lo)} – {_fmt(hi)}"
            parts.append(f"Typical price range for {search_arg}: {range_str}.")
            for s in priced[:4]:
                t = f", ~{s['estimatedTime']} min" if s.get("estimatedTime") else ""
                parts.append(f"• {s['name']}: {_fmt(int(float(s['unitPrice'])))}{t}")
        if unpriced:
            names = ", ".join(s["name"] for s in unpriced[:2])
            parts.append(f"On-site assessment needed for: {names}.")
        parts.append("Exact cost confirmed by technician before work starts. Want to book?")
        return "\n".join(parts)

    # Vietnamese
    parts = []
    if priced:
        # Sort by price to show most accessible services first
        priced_sorted = sorted(priced, key=lambda s: int(float(s.get("unitPrice") or 0)))
        prices = [int(float(s["unitPrice"])) for s in priced_sorted]

        # Use IQR-trimmed range to avoid outlier skew (e.g. trạm sạc xe điện)
        # Simple approach: exclude top outlier if it's 5x the median
        import statistics
        median_price = statistics.median(prices)
        typical = [p for p in prices if p <= median_price * 5]
        lo = min(typical) if typical else min(prices)
        hi = max(typical) if typical else max(prices)

        range_str = _fmt(lo) if lo == hi else f"{_fmt(lo)} – {_fmt(hi)}"
        label = "Tổng quan giá" if search_arg == "all" else f"Giá sửa {search_arg}"
        parts.append(f"Dạ {label} tham khảo: **{range_str}**.")

        # Show 4 most affordable/common services
        for s in priced_sorted[:4]:
            t = f", ~{s['estimatedTime']} phút" if s.get("estimatedTime") else ""
            parts.append(f"• {s['name']}: {_fmt(int(float(s['unitPrice'])))}{t}")

        # Mention outlier separately if exists
        outliers = [s for s in priced_sorted if int(float(s["unitPrice"])) > median_price * 5]
        if outliers:
            names = ", ".join(s["name"] for s in outliers[:2])
            parts.append(f"Dịch vụ đặc biệt như {names}: báo giá theo thực tế.")

    if unpriced:
        names = ", ".join(s["name"] for s in unpriced[:2])
        parts.append(f"Một số hạng mục như {names} cần thợ kiểm tra mới báo được giá.")
    parts.append("Thợ sẽ xác nhận chi phí chính xác trước khi làm. Bạn muốn đặt lịch không ạ?")
    return "\n".join(parts)


def format_groups_for_llm(groups: List[Dict]) -> str:
    """Convert raw groups into a compact fact block."""
    if not groups:
        return "Nhóm dịch vụ: Điện, Nước, Điện lạnh, Xây dựng, Thạch cao (dữ liệu mặc định)."
    names = [g.get("name", "") for g in groups if g.get("name")]
    return "Nhóm dịch vụ Fixago: " + ", ".join(names) + "."


def format_promotions_for_llm(promos: List[Dict]) -> str:
    """Convert raw promotions into a compact fact block."""
    if not promos:
        return "Hiện không có khuyến mãi."
    lines = ["Khuyến mãi hiện có:"]
    for p in promos:
        line = f"- {p.get('name', 'Ưu đãi')}"
        if p.get("code"):
            line += f" (mã: {p['code']})"
        if p.get("discountType") == 1:
            line += f": giảm {p.get('discountValue', 0)}%"
            if p.get("maxDiscountAmount"):
                v = int(float(p["maxDiscountAmount"]))
                line += f", tối đa {v:,}".replace(",", ".") + " VNĐ"
        else:
            v = int(float(p.get("discountValue", 0)))
            line += f": giảm {v:,}".replace(",", ".") + " VNĐ"
        lines.append(line)
    return "\n".join(lines)


# ── Tool handlers ─────────────────────────────────────────────────────────────

def handle_get_groups(messages: List[Dict], used_tools: List[str]) -> str:
    used_tools.append("Thực thi Tool [Backend API]: Lấy danh sách nhóm dịch vụ (GET /services/groups)...")

    try:
        resp = requests.get(f"{BACKEND_URL}/services/groups", timeout=3)
        if resp.status_code == 200:
            groups = resp.json()  # plain array
            if groups:
                names = [g.get("name", "") for g in groups if g.get("name")]
                group_list = ", ".join(names)
                return (
                    f"Dạ Fixago cung cấp các dịch vụ sửa chữa tại nhà gồm: {group_list}. "
                    "Bạn đang cần hỗ trợ hạng mục nào để mình tư vấn thêm nhé?"
                )
    except Exception as exc:
        logger.warning("handle_get_groups backend error: %s", exc)

    # Fallback: static answer
    return (
        "Dạ Fixago cung cấp các dịch vụ sửa chữa tại nhà gồm: Điện, Nước, Điện lạnh, "
        "Xây dựng và Thạch cao. Bạn đang cần hỗ trợ hạng mục nào để mình tư vấn thêm nhé?"
    )


def handle_get_services(search_arg: str, messages: List[Dict], used_tools: List[str]) -> str:
    used_tools.append(f'Thực thi Tool [Backend API]: Tìm kiếm dịch vụ với từ khóa "{search_arg}"...')

    try:
        resp = requests.get(
            f"{BACKEND_URL}/services",
            params={"search": search_arg, "limit": 10},
            timeout=3,
        )
        if resp.status_code != 200:
            return (
                "Dạ hiện mình chưa lấy được bảng giá từ hệ thống. "
                "Dạ giá của Fixago tùy theo hạng mục và tình trạng thực tế, thợ sẽ báo rõ trước khi làm. "
                "Bạn muốn mình hỗ trợ đặt lịch không ạ?"
            )

        services = resp.json().get("data", [])

        # Fallback for appliances that share the "điện" group
        if not services and search_arg in {"máy lạnh", "điện lạnh", "máy giặt"}:
            fb = requests.get(f"{BACKEND_URL}/services", params={"search": "điện", "limit": 10}, timeout=3)
            if fb.status_code == 200:
                services = fb.json().get("data", [])

        if not services:
            return (
                f"Dạ hiện mình chưa thấy dịch vụ khớp với '{search_arg}' trong hệ thống. "
                "Dạ giá của Fixago tùy theo hạng mục và tình trạng thực tế, thợ sẽ báo rõ trước khi làm. "
                "Bạn muốn mình hỗ trợ đặt lịch không ạ?"
            )

        summary = _build_price_summary(services)
        if summary:
            return (
                "Dạ Fixago có các dịch vụ phù hợp với nhu cầu của bạn.\n\n"
                f"{summary}\n\n"
                "Dạ giá của Fixago tùy theo hạng mục và tình trạng thực tế, thợ sẽ báo rõ trước khi làm. "
                "Bạn muốn mình hỗ trợ đặt lịch không ạ?"
            )

        return (
            "Dạ Fixago có thể hỗ trợ tình trạng này. "
            "Dạ giá của Fixago tùy theo hạng mục và tình trạng thực tế, thợ sẽ báo rõ trước khi làm. "
            "Bạn muốn mình hỗ trợ đặt lịch không ạ?"
        )

    except Exception as exc:
        return (
            f"Dạ hiện mình chưa lấy được bảng giá do lỗi hệ thống: {exc}. "
            "Dạ giá của Fixago tùy theo hạng mục và tình trạng thực tế, thợ sẽ báo rõ trước khi làm. "
            "Bạn có thể để lại thông tin, Fixago sẽ hỗ trợ kiểm tra lại ạ."
        )


def handle_get_promotions(messages: List[Dict], used_tools: List[str]) -> str:
    used_tools.append("Thực thi Tool [Backend API]: Lấy danh sách ưu đãi (GET /discounts/available)...")

    try:
        resp = requests.get(f"{BACKEND_URL}/discounts/available", timeout=3)
        if resp.status_code == 200:
            raw    = resp.json()
            promos = raw if isinstance(raw, list) else raw.get("data", [])
            if promos:
                lines = ["Dạ Fixago hiện có các chương trình ưu đãi sau:"]
                for p in promos:
                    line = f"- {p.get('name', 'Ưu đãi')}"
                    if p.get("code"):
                        line += f" (mã: {p['code']})"
                    if p.get("discountType") == 1:
                        line += f": giảm {p.get('discountValue', 0)}%"
                        if p.get("maxDiscountAmount"):
                            line += f", tối đa {_fmt_vnd(p['maxDiscountAmount'])}"
                    else:
                        line += f": giảm {_fmt_vnd(p.get('discountValue', 0))}"
                    lines.append(line)
                lines.append("Bạn muốn mình tư vấn thêm hoặc hỗ trợ đặt lịch không ạ?")
                return "\n".join(lines)
            else:
                return (
                    "Dạ hiện Fixago chưa có chương trình khuyến mãi nào. "
                    "Bạn mô tả tình trạng cần sửa để mình tư vấn dịch vụ phù hợp nhé!"
                )
    except Exception as exc:
        logger.warning("handle_get_promotions backend error: %s", exc)

    return (
        "Dạ mình chưa lấy được thông tin khuyến mãi lúc này. "
        "Bạn mô tả tình trạng cần sửa để mình tư vấn dịch vụ phù hợp nhé!"
    )
