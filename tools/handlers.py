"""
tools/handlers.py
-----------------
Executes the three read-only Fixago tools by calling the backend API.
Responses are formatted directly (no LLM round-trip) for speed.
LLM summarization is only used as a fallback when the response needs
free-form prose (e.g. when backend data is rich/unexpected).
"""
import logging
import os
from typing import Dict, List

import requests

logger = logging.getLogger("fixago.tools_handlers")

BACKEND_URL = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:3001/api/v1")


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
