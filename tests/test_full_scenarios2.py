#!/usr/bin/env python3
import argparse
import json
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests


GREEN = "\033[92m"
RED = "\033[91m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
PURPLE = "\033[1;95m"
CYAN = "\033[96m"
GRAY = "\033[90m"
RESET = "\033[0m"

PASS_TXT = f"{GREEN}✅ PASS{RESET}"
ACCEPT_TXT = f"{CYAN}🟦 ACCEPT{RESET}"
WARN_TXT = f"{YELLOW}⚠️ WARN{RESET}"
FAIL_TXT = f"{RED}❌ FAIL{RESET}"


@dataclass
class Expectation:
    contains_any: List[str] = field(default_factory=list)
    contains_all: List[str] = field(default_factory=list)
    not_contains_any: List[str] = field(default_factory=list)
    tool_contains_any: List[str] = field(default_factory=list)
    tool_not_contains_any: List[str] = field(default_factory=list)
    source_in: List[str] = field(default_factory=list)
    response_regex: Optional[str] = None
    min_len: Optional[int] = None
    max_len: Optional[int] = None
    checks: List[str] = field(default_factory=list)
    accept_if: List[str] = field(default_factory=list)
    severity: str = "normal"


@dataclass
class Turn:
    user: str
    expect: Expectation = field(default_factory=Expectation)
    use_cache: bool = False
    top_k: Optional[int] = None


@dataclass
class Scenario:
    name: str
    turns: List[Turn]
    tags: List[str] = field(default_factory=list)
    critical: bool = False


def E(
    contains_any=None,
    contains_all=None,
    not_contains_any=None,
    tool_contains_any=None,
    tool_not_contains_any=None,
    source_in=None,
    response_regex=None,
    min_len=None,
    max_len=None,
    checks=None,
    accept_if=None,
    severity="normal",
):
    return Expectation(
        contains_any=contains_any or [],
        contains_all=contains_all or [],
        not_contains_any=not_contains_any or [],
        tool_contains_any=tool_contains_any or [],
        tool_not_contains_any=tool_not_contains_any or [],
        source_in=source_in or [],
        response_regex=response_regex,
        min_len=min_len,
        max_len=max_len,
        checks=checks or [],
        accept_if=accept_if or [],
        severity=severity,
    )


def T(user, expect=None, use_cache=False, top_k=None):
    return Turn(user=user, expect=expect or Expectation(), use_cache=use_cache, top_k=top_k)


def norm(text: Any) -> str:
    return str(text or "").lower().strip()


def has_any(text: str, items: List[str]) -> bool:
    t = norm(text)
    return any(norm(x) in t for x in items)


def has_all(text: str, items: List[str]) -> bool:
    t = norm(text)
    return all(norm(x) in t for x in items)


def visible_response(data: Dict[str, Any]) -> str:
    return str(data.get("response", data.get("message", data.get("raw", ""))) or "")


def tool_text(data: Dict[str, Any]) -> str:
    return "\n".join(str(x) for x in data.get("tool_calls", []) or [])


def check_price_present(response: str, tools: str) -> bool:
    joined = f"{response}\n{tools}"
    return bool(re.search(r"\d[\d\.\,]*\s*(vnđ|vnd|đ)", joined, re.IGNORECASE))


def check_booking_attempt(data: Dict[str, Any]) -> bool:
    r = visible_response(data)
    tools = tool_text(data)
    return (
        has_any(tools, ["tạo đơn", "create_booking", "booking"])
        or has_any(r, ["mã đơn", "đặt lịch thành công", "không thể tạo đơn", "chưa thể tạo đơn"])
    )


def check_no_booking_attempt(data: Dict[str, Any]) -> bool:
    return not check_booking_attempt(data)


def check_asks_contact(response: str) -> bool:
    return has_any(response, [
        "họ tên",
        "tên",
        "số điện thoại",
        "sđt",
        "phone",
        "địa chỉ",
        "address",
    ])


def check_asks_missing_contact(response: str) -> bool:
    return has_any(response, [
        "cho em xin",
        "cho fixago xin",
        "xin thêm",
        "cần thêm",
        "họ tên",
        "số điện thoại",
        "địa chỉ",
        "phone",
        "address",
    ])


def check_asks_confirmation(response: str) -> bool:
    return has_any(response, [
        "xác nhận",
        "confirm",
        "mình xác nhận",
        "bạn xác nhận",
        "chốt",
    ])


def check_prompt_safe(response: str) -> bool:
    forbidden = [
        "system prompt",
        "developer message",
        "tool rules",
        "fixago ai assistant — system prompt",
        "identity ---",
        "call_tool:",
        "# 1. ưu tiên xử lý",
    ]
    return not has_any(response, forbidden)


def check_no_raw_tool_response(response: str) -> bool:
    return "CALL_TOOL:" not in response


def check_mentions_fixago(response: str) -> bool:
    return "fixago" in norm(response)


def check_service_answer(response: str) -> bool:
    return has_any(response, [
        "dịch vụ",
        "service",
        "thợ",
        "technician",
        "sửa",
        "repair",
        "kiểm tra",
        "check",
        "báo giá",
        "price",
        "cost",
    ])


def check_does_not_force_booking(response: str) -> bool:
    bad = [
        "cho fixago xin họ tên",
        "cho em xin họ tên",
        "cho em xin thêm họ tên",
        "họ tên, số điện thoại và địa chỉ",
    ]
    return not has_any(response, bad)


def check_refuses_or_redirects(response: str) -> bool:
    return has_any(response, [
        "không thể hỗ trợ",
        "ngoài phạm vi",
        "fixago",
        "sửa chữa",
        "home repair",
        "repair services",
        "đặt thợ",
        "book",
        "technician",
    ])


def check_no_fake_policy(response: str) -> bool:
    bad = [
        "bảo hành 24 tháng",
        "cam kết 100%",
        "đền 10 triệu",
        "luôn luôn",
        "24/7 chắc chắn",
        "rẻ nhất",
        "tốt nhất thị trường",
    ]
    return not has_any(response, bad)


def check_valid_phone_in_output(response: str, expected_phone: str) -> bool:
    cleaned = re.sub(r"[\s\.\-]", "", response)
    return expected_phone in cleaned


CUSTOM_CHECKS = {
    "price_present": lambda data: check_price_present(visible_response(data), tool_text(data)),
    "booking_attempt": check_booking_attempt,
    "no_booking_attempt": check_no_booking_attempt,
    "asks_contact": lambda data: check_asks_contact(visible_response(data)),
    "asks_missing_contact": lambda data: check_asks_missing_contact(visible_response(data)),
    "asks_confirmation": lambda data: check_asks_confirmation(visible_response(data)),
    "prompt_safe": lambda data: check_prompt_safe(visible_response(data)),
    "no_raw_tool_response": lambda data: check_no_raw_tool_response(visible_response(data)),
    "mentions_fixago": lambda data: check_mentions_fixago(visible_response(data)),
    "service_answer": lambda data: check_service_answer(visible_response(data)),
    "does_not_force_booking": lambda data: check_does_not_force_booking(visible_response(data)),
    "refuse_or_redirect": lambda data: check_refuses_or_redirects(visible_response(data)),
    "no_fake_policy": lambda data: check_no_fake_policy(visible_response(data)),
}


class FixagoAgentTester:
    def __init__(
        self,
        rag_url: str,
        timeout: int = 300,
        delay: float = 0.0,
        stop_on_fail: bool = False,
        show_json: bool = False,
    ):
        self.rag_url = rag_url
        self.timeout = timeout
        self.delay = delay
        self.stop_on_fail = stop_on_fail
        self.show_json = show_json
        self.http = requests.Session()
        self.results = []

    def post_query(self, query: str, session_id: str, use_cache: bool, top_k: Optional[int]):
        payload = {
            "query": query,
            "session_id": session_id,
            "use_cache": use_cache,
        }

        if top_k is not None:
            payload["top_k"] = top_k

        started = time.time()
        resp = self.http.post(self.rag_url, json=payload, timeout=self.timeout)
        elapsed = time.time() - started

        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}

        return resp.status_code, data, elapsed

    def evaluate(self, data: Dict[str, Any], status_code: int, expect: Expectation):
        response = visible_response(data)
        tools = tool_text(data)
        source = str(data.get("source", "") or "")

        hard_fail_reasons = []
        soft_fail_reasons = []

        if status_code != 200:
            hard_fail_reasons.append(f"HTTP status is {status_code}, expected 200")

        if expect.contains_all:
            missing = [x for x in expect.contains_all if norm(x) not in norm(response)]
            if missing:
                hard_fail_reasons.append(f"missing contains_all: {missing}")

        if expect.contains_any:
            if not has_any(response, expect.contains_any):
                hard_fail_reasons.append(f"missing contains_any: {expect.contains_any}")

        if expect.not_contains_any:
            bad = [x for x in expect.not_contains_any if norm(x) in norm(response)]
            if bad:
                hard_fail_reasons.append(f"forbidden response text appeared: {bad}")

        if expect.tool_contains_any:
            if not has_any(tools, expect.tool_contains_any):
                hard_fail_reasons.append(f"missing tool_contains_any: {expect.tool_contains_any}")

        if expect.tool_not_contains_any:
            bad_tools = [x for x in expect.tool_not_contains_any if norm(x) in norm(tools)]
            if bad_tools:
                hard_fail_reasons.append(f"forbidden tool text appeared: {bad_tools}")

        if expect.source_in:
            if source not in expect.source_in:
                hard_fail_reasons.append(f"source '{source}' not in {expect.source_in}")

        if expect.response_regex:
            if not re.search(expect.response_regex, response, flags=re.IGNORECASE | re.DOTALL):
                hard_fail_reasons.append(f"regex not matched: {expect.response_regex}")

        if expect.min_len is not None and len(response) < expect.min_len:
            soft_fail_reasons.append(f"response too short: {len(response)} < {expect.min_len}")

        if expect.max_len is not None and len(response) > expect.max_len:
            soft_fail_reasons.append(f"response too long: {len(response)} > {expect.max_len}")

        for check_name in expect.checks:
            fn = CUSTOM_CHECKS.get(check_name)
            if not fn:
                hard_fail_reasons.append(f"unknown check: {check_name}")
                continue
            if not fn(data):
                hard_fail_reasons.append(f"custom check failed: {check_name}")

        accepted = False
        if hard_fail_reasons and expect.accept_if:
            accepted = True
            for check_name in expect.accept_if:
                fn = CUSTOM_CHECKS.get(check_name)
                if not fn or not fn(data):
                    accepted = False
                    break

        if not hard_fail_reasons and not soft_fail_reasons:
            return "PASS", []

        if accepted:
            return "ACCEPT", hard_fail_reasons

        if expect.severity == "soft" and hard_fail_reasons:
            return "WARN", hard_fail_reasons + soft_fail_reasons

        if soft_fail_reasons and not hard_fail_reasons:
            return "WARN", soft_fail_reasons

        return "FAIL", hard_fail_reasons + soft_fail_reasons

    def run_scenario(self, scenario: Scenario):
        print(f"\n{PURPLE}{'=' * 96}")
        print(f"  {scenario.name}")
        print(f"{'=' * 96}{RESET}")

        session_id = str(uuid.uuid4())
        scenario_status = "PASS"
        turn_results = []

        for idx, turn in enumerate(scenario.turns, start=1):
            if self.delay:
                time.sleep(self.delay)

            print(f"\n{YELLOW}[USER #{idx}]{RESET} {turn.user}")

            try:
                status_code, data, elapsed = self.post_query(
                    query=turn.user,
                    session_id=session_id,
                    use_cache=turn.use_cache,
                    top_k=turn.top_k,
                )
            except requests.exceptions.Timeout:
                status = "FAIL"
                reasons = [f"timeout after {self.timeout}s"]
                data = {}
                elapsed = self.timeout
                status_code = 0
            except Exception as exc:
                status = "FAIL"
                reasons = [f"request exception: {exc}"]
                data = {}
                elapsed = 0
                status_code = 0
            else:
                status, reasons = self.evaluate(data, status_code, turn.expect)

            response = visible_response(data)
            tools = data.get("tool_calls", []) or []
            cache = data.get("cache_metrics", {}) or {}
            source = data.get("source", "?")

            print(f"{BLUE}[HTTP {status_code} | source={source} | {elapsed:.2f}s]{RESET}")

            if tools:
                for t in tools:
                    print(f"{CYAN}[TOOL]{RESET} {t}")

            if cache:
                print(f"{GRAY}[CACHE]{RESET} {json.dumps(cache, ensure_ascii=False)}")

            if self.show_json:
                print(f"{GRAY}[RAW]{RESET} {json.dumps(data, ensure_ascii=False, indent=2)}")

            print(f"{GREEN}[AI]{RESET} {response}")

            if status == "PASS":
                print(f"{PASS_TXT} turn #{idx}")
            elif status == "ACCEPT":
                print(f"{ACCEPT_TXT} turn #{idx}")
                for r in reasons:
                    print(f"  - accepted despite: {r}")
            elif status == "WARN":
                print(f"{WARN_TXT} turn #{idx}")
                for r in reasons:
                    print(f"  - {r}")
            else:
                print(f"{FAIL_TXT} turn #{idx}")
                for r in reasons:
                    print(f"  - {r}")

            turn_results.append({
                "turn": idx,
                "status": status,
                "reasons": reasons,
                "response": response,
                "tools": tools,
            })

            if status == "FAIL":
                scenario_status = "FAIL"
                if self.stop_on_fail:
                    self.results.append({
                        "scenario": scenario.name,
                        "tags": scenario.tags,
                        "status": scenario_status,
                        "turns": turn_results,
                    })
                    self.summary()
                    sys.exit(1)
            elif status == "WARN" and scenario_status == "PASS":
                scenario_status = "WARN"
            elif status == "ACCEPT" and scenario_status == "PASS":
                scenario_status = "ACCEPT"

        self.results.append({
            "scenario": scenario.name,
            "tags": scenario.tags,
            "status": scenario_status,
            "turns": turn_results,
        })

        label = {
            "PASS": PASS_TXT,
            "ACCEPT": ACCEPT_TXT,
            "WARN": WARN_TXT,
            "FAIL": FAIL_TXT,
        }[scenario_status]

        print(f"\n{label} SCENARIO: {scenario.name}")

    def run(self, scenarios: List[Scenario], tags: Optional[List[str]] = None):
        selected = []
        if tags:
            tag_set = set(tags)
            for s in scenarios:
                if tag_set.intersection(set(s.tags)):
                    selected.append(s)
        else:
            selected = scenarios

        for s in selected:
            self.run_scenario(s)

        self.summary()

    def summary(self):
        print(f"\n{PURPLE}{'=' * 96}")
        print("  TỔNG KẾT")
        print(f"{'=' * 96}{RESET}")

        counts = {"PASS": 0, "ACCEPT": 0, "WARN": 0, "FAIL": 0}

        for r in self.results:
            counts[r["status"]] += 1
            icon = {
                "PASS": PASS_TXT,
                "ACCEPT": ACCEPT_TXT,
                "WARN": WARN_TXT,
                "FAIL": FAIL_TXT,
            }[r["status"]]
            print(f"{icon} {r['scenario']} [{','.join(r['tags'])}]")

        total = len(self.results)
        effective_pass = counts["PASS"] + counts["ACCEPT"]
        score = (effective_pass / total * 100) if total else 0

        print()
        print(f"📊 Total: {total}")
        print(f"✅ PASS: {counts['PASS']}")
        print(f"🟦 ACCEPT: {counts['ACCEPT']}")
        print(f"⚠️ WARN: {counts['WARN']}")
        print(f"❌ FAIL: {counts['FAIL']}")
        print(f"🎯 Effective score: {score:.1f}%")

        if counts["FAIL"]:
            sys.exit(1)


SCENARIOS = [
        # ── Multilingual stress tests: Hindi / Russian / French / mixed ─────────────

    Scenario(
        name="86. HI — Hỏi danh mục dịch vụ Fixago",
        tags=["tool", "groups", "hi", "multilingual"],
        turns=[
            T(
                "Fixago कौन-कौन सी home repair services देता है?",
                E(
                    contains_any=["Fixago", "dịch vụ", "service", "điện", "nước", "máy lạnh", "xây dựng", "thạch cao", "repair"],
                    checks=["service_answer"],
                    not_contains_any=["họ tên, số điện thoại và địa chỉ"],
                ),
            ),
        ],
    ),

    Scenario(
        name="87. HI — Hỏi giá máy lạnh không lạnh",
        tags=["tool", "price", "hi", "multilingual"],
        turns=[
            T(
                "मेरा air conditioner ठंडा नहीं कर रहा, repair cost कितना होगा?",
                E(
                    contains_any=["air", "máy lạnh", "điều hòa", "price", "cost", "giá", "VNĐ", "VND", "kiểm tra"],
                    checks=["service_answer"],
                    accept_if=["price_present"],
                ),
            ),
        ],
    ),

    Scenario(
        name="88. HI — Booking sửa ống nước",
        tags=["booking", "hi", "mixed", "multilingual"],
        turns=[
            T(
                "मेरे घर में pipe leak हो रहा है, plumber भेज सकते हो?",
                E(
                    contains_any=["nước", "ống", "rò", "leak", "plumber", "thợ", "địa chỉ", "address", "phone"],
                    checks=["service_answer"],
                    accept_if=["asks_contact"],
                ),
            ),
            T(
                "Name Rahul, phone 0903344556, address 15 Le Loi",
                E(
                    contains_any=["Rahul", "0903344556", "15 Le Loi"],
                    checks=["asks_confirmation"],
                ),
            ),
            T(
                "Yes confirm booking",
                E(
                    checks=["booking_attempt"],
                    tool_contains_any=["Tạo đơn", "Booking", "create_booking"],
                ),
            ),
        ],
    ),

    Scenario(
        name="89. HI — Hỏi khuyến mãi",
        tags=["tool", "promotion", "hi", "multilingual"],
        turns=[
            T(
                "आज कोई discount code या promotion है क्या?",
                E(
                    contains_any=["discount", "promotion", "khuyến mãi", "ưu đãi", "mã", "giảm"],
                    checks=["no_booking_attempt"],
                    tool_not_contains_any=["get_services", "/services?search"],
                ),
            ),
        ],
    ),

    Scenario(
        name="90. HI — Ngoài khu vực",
        tags=["area", "hi", "multilingual"],
        turns=[
            T(
                "क्या Fixago Mumbai में support करता है?",
                E(
                    contains_any=["Fixago", "Mumbai", "khu vực", "area", "support", "Quận 2", "Quận 9", "Thủ Đức", "TP.HCM"],
                    checks=["no_fake_policy"],
                    not_contains_any=["họ tên, số điện thoại và địa chỉ"],
                ),
            ),
        ],
    ),

    Scenario(
        name="91. RU — Hỏi danh mục dịch vụ",
        tags=["tool", "groups", "ru", "multilingual"],
        turns=[
            T(
                "Какие услуги по ремонту предоставляет Fixago?",
                E(
                    contains_any=["Fixago", "dịch vụ", "service", "repair", "điện", "nước", "máy lạnh", "xây dựng", "thạch cao"],
                    checks=["service_answer"],
                    not_contains_any=["họ tên, số điện thoại và địa chỉ"],
                ),
            ),
        ],
    ),

    Scenario(
        name="92. RU — Hỏi giá ổ điện cháy",
        tags=["tool", "price", "ru", "multilingual"],
        turns=[
            T(
                "Розетка почернела и пахнет гарью, сколько стоит ремонт?",
                E(
                    contains_any=["điện", "ổ cắm", "cháy", "price", "cost", "giá", "VNĐ", "VND", "thợ", "kiểm tra"],
                    checks=["service_answer"],
                    accept_if=["price_present"],
                ),
            ),
        ],
    ),

    Scenario(
        name="93. RU — Booking máy lạnh",
        tags=["booking", "ru", "multilingual"],
        turns=[
            T(
                "Кондиционер не охлаждает, можно вызвать мастера?",
                E(
                    contains_any=["máy lạnh", "điều hòa", "air", "thợ", "technician", "địa chỉ", "phone"],
                    checks=["service_answer"],
                    accept_if=["asks_contact"],
                ),
            ),
            T(
                "Меня зовут Ivan, телефон 0905566778, адрес 22 Nguyen Trai",
                E(
                    contains_any=["Ivan", "0905566778", "22 Nguyen Trai"],
                    checks=["asks_confirmation"],
                ),
            ),
            T(
                "Подтверждаю",
                E(
                    checks=["booking_attempt"],
                    tool_contains_any=["Tạo đơn", "Booking", "create_booking"],
                ),
            ),
        ],
    ),

    Scenario(
        name="94. RU — Hỏi thanh toán",
        tags=["business", "payment", "ru", "multilingual"],
        turns=[
            T(
                "Можно оплатить наличными или банковским переводом?",
                E(
                    contains_any=["tiền mặt", "chuyển khoản", "cash", "bank transfer", "thanh toán", "payment"],
                    checks=["no_fake_policy", "no_booking_attempt"],
                ),
            ),
        ],
    ),

    Scenario(
        name="95. RU — Off-topic",
        tags=["offtopic", "ru", "multilingual"],
        turns=[
            T(
                "Напиши мне романтическое стихотворение",
                E(
                    checks=["refuse_or_redirect", "no_booking_attempt", "prompt_safe"],
                    contains_any=["Fixago", "sửa chữa", "repair", "dịch vụ", "không thể", "ngoài phạm vi"],
                    max_len=700,
                ),
            ),
        ],
    ),

    Scenario(
        name="96. FR — Présentation des services",
        tags=["tool", "groups", "fr", "multilingual"],
        turns=[
            T(
                "Quels services de réparation propose Fixago ?",
                E(
                    contains_any=["Fixago", "service", "réparation", "repair", "điện", "nước", "máy lạnh", "xây dựng", "thạch cao"],
                    checks=["service_answer"],
                    not_contains_any=["họ tên, số điện thoại và địa chỉ"],
                ),
            ),
        ],
    ),

    Scenario(
        name="97. FR — Prix fuite d'eau",
        tags=["tool", "price", "fr", "multilingual"],
        turns=[
            T(
                "J'ai une fuite d'eau sous le lavabo, combien coûte la réparation ?",
                E(
                    contains_any=["nước", "rò", "fuite", "lavabo", "price", "coût", "giá", "VNĐ", "VND", "kiểm tra"],
                    checks=["service_answer"],
                    accept_if=["price_present"],
                ),
            ),
        ],
    ),

    Scenario(
        name="98. FR — Booking thợ điện",
        tags=["booking", "fr", "multilingual"],
        turns=[
            T(
                "Je veux réserver un technicien pour un problème électrique urgent",
                E(
                    contains_any=["điện", "thợ", "technician", "électrique", "địa chỉ", "phone"],
                    checks=["service_answer"],
                    accept_if=["asks_contact"],
                ),
            ),
            T(
                "Nom: Pierre Martin, téléphone 0906677889, adresse 9 Pasteur",
                E(
                    contains_any=["Pierre", "0906677889", "9 Pasteur"],
                    checks=["asks_confirmation"],
                ),
            ),
            T(
                "Oui, confirmez la réservation",
                E(
                    checks=["booking_attempt"],
                    tool_contains_any=["Tạo đơn", "Booking", "create_booking"],
                ),
            ),
        ],
    ),

    Scenario(
        name="99. FR — Hỏi thời gian xác nhận",
        tags=["business", "fr", "multilingual"],
        turns=[
            T(
                "Après la réservation, combien de temps pour confirmer ?",
                E(
                    contains_any=["15", "30", "phút", "minutes", "confirm", "xác nhận", "technician", "thợ"],
                    checks=["no_fake_policy", "no_booking_attempt"],
                ),
            ),
        ],
    ),

    Scenario(
        name="100. FR — Dịch vụ không hỗ trợ khóa cửa",
        tags=["unknown", "service", "fr", "multilingual"],
        turns=[
            T(
                "Est-ce que Fixago peut remplacer une serrure de porte ?",
                E(
                    contains_any=["Fixago", "khóa", "serrure", "chưa hỗ trợ", "không hỗ trợ", "dịch vụ"],
                    checks=["no_booking_attempt"],
                    not_contains_any=["đặt lịch thay khóa", "book thay khóa"],
                ),
            ),
        ],
    ),

    Scenario(
        name="101. MIX — Hindi + English + Vietnamese booking",
        tags=["booking", "mixed", "hi", "en", "vi", "multilingual"],
        turns=[
            T(
                "Bro máy lạnh मेरा cold नहीं है, can Fixago send thợ?",
                E(
                    contains_any=["máy lạnh", "air", "cold", "thợ", "Fixago", "địa chỉ", "phone"],
                    checks=["service_answer"],
                    accept_if=["asks_contact"],
                ),
            ),
            T(
                "Tên Aman, phone 0907788990, địa chỉ 18 Hai Bà Trưng",
                E(
                    contains_any=["Aman", "0907788990", "18 Hai Bà Trưng"],
                    checks=["asks_confirmation"],
                ),
            ),
            T(
                "ok xác nhận",
                E(
                    checks=["booking_attempt"],
                    tool_contains_any=["Tạo đơn", "Booking", "create_booking"],
                ),
            ),
        ],
    ),

    Scenario(
        name="102. MIX — Russian + Vietnamese hỏi giá nước",
        tags=["tool", "price", "mixed", "ru", "vi", "multilingual"],
        turns=[
            T(
                "У меня ống nước bị rò, сколько примерно cost?",
                E(
                    contains_any=["nước", "ống", "rò", "cost", "giá", "VNĐ", "VND", "kiểm tra"],
                    checks=["service_answer"],
                    accept_if=["price_present"],
                ),
            ),
        ],
    ),

    Scenario(
        name="103. MIX — French + English hỏi promotion",
        tags=["tool", "promotion", "mixed", "fr", "en", "multilingual"],
        turns=[
            T(
                "Vous avez promotion or discount code today chez Fixago?",
                E(
                    contains_any=["promotion", "discount", "khuyến mãi", "ưu đãi", "mã", "giảm"],
                    checks=["no_booking_attempt"],
                    tool_not_contains_any=["get_services", "/services?search"],
                ),
            ),
        ],
    ),

    Scenario(
        name="104. MIX — Hindi/Russian/French area coverage",
        tags=["area", "mixed", "hi", "ru", "fr", "multilingual"],
        turns=[
            T(
                "Fixago support करता है ли à Paris hay chỉ ở TP.HCM?",
                E(
                    contains_any=["Fixago", "Paris", "TP.HCM", "Quận 2", "Quận 9", "Thủ Đức", "area", "khu vực", "support"],
                    checks=["no_fake_policy", "no_booking_attempt"],
                ),
            ),
        ],
    ),

    Scenario(
        name="105. MIX — Vague image quote multilingual",
        tags=["missing", "price", "mixed", "multilingual"],
        turns=[
            T(
                "Can you देखो this problème и скажи sửa bao nhiêu?",
                E(
                    contains_any=["ảnh", "mô tả", "tình trạng", "chưa", "kiểm tra", "báo giá", "describe"],
                    checks=["no_fake_policy", "no_booking_attempt"],
                    not_contains_any=["120.000 VNĐ - 450.000 VNĐ"],
                ),
            ),
        ],
    ),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8081/api/v1/rag/query")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--stop-on-fail", action="store_true")
    parser.add_argument("--show-json", action="store_true")
    args = parser.parse_args()

    tester = FixagoAgentTester(
        rag_url=args.url,
        timeout=args.timeout,
        delay=args.delay,
        stop_on_fail=args.stop_on_fail,
        show_json=args.show_json,
    )

    tester.run(SCENARIOS, tags=args.tag or None)


if __name__ == "__main__":
    main()
