#!/usr/bin/env python3
"""
Test information queries against the RAG server.
Tests: Service overview, pricing, hours, payment, area, promotions, unsupported services.
"""

import requests
import json
import time
from typing import Dict, List, Optional

# Colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"

PASS_TXT = f"{GREEN}✅ PASS{RESET}"
FAIL_TXT = f"{RED}❌ FAIL{RESET}"
WARN_TXT = f"{YELLOW}⚠️ WARN{RESET}"


class InfoQueryTester:
    def __init__(self, rag_url: str = "http://127.0.0.1:8081/api/v1/rag/query"):
        self.rag_url = rag_url
        self.results = []
        self.session = requests.Session()

    def normalize(self, text: str) -> str:
        """Normalize text for comparison."""
        return str(text or "").lower().strip()

    def contains_any(self, text: str, patterns: List[str]) -> bool:
        """Check if text contains any pattern (case-insensitive)."""
        norm_text = self.normalize(text)
        return any(self.normalize(p) in norm_text for p in patterns)

    def post_query(self, query: str) -> tuple:
        """Post query to RAG server."""
        try:
            resp = self.session.post(
                self.rag_url,
                json={"query": query, "history": []},
                timeout=30
            )
            data = resp.json() if resp.status_code == 200 else {"error": resp.text}
            return resp.status_code, data
        except Exception as e:
            return 0, {"error": str(e)}

    def evaluate_response(
        self,
        response: str,
        tools: List[str],
        expected_tool: Optional[str] = None,
        expected_response: Optional[str] = None,
    ) -> tuple:
        """Evaluate if response meets expectations."""
        reasons = []

        # Check tool expectation
        if expected_tool:
            tool_str = "\n".join(str(t) for t in tools or [])
            tool_lower = self.normalize(tool_str)

            # Map expected_tool names to actual API call patterns
            tool_map = {
                "get_groups": ["get_groups", "danh mục", "dịch vụ", "service"],
                "get_services": ["get_services", "giá", "price", "báo giá"],
                "get_promotions": ["get_promotions", "khuyến mãi", "promotion"],
                "static_fallback": ["static"],
            }

            expected_patterns = tool_map.get(expected_tool, [expected_tool])
            if not self.contains_any(tool_str, expected_patterns):
                reasons.append(f"Tool mismatch: expected {expected_tool}, got {tools}")

        # Check response expectation
        if expected_response:
            expected_patterns = expected_response.split("|")
            if not self.contains_any(response, expected_patterns):
                reasons.append(f"Response missing expected: {expected_response}")

        if not reasons:
            return "PASS", []

        return "FAIL", reasons

    def run_test(self, test_id: str, query: str, **expectations) -> None:
        """Run a single test."""
        print(f"\n{BLUE}[{test_id}]{RESET} {query}")

        try:
            status_code, data = self.post_query(query)

            if status_code != 200:
                print(f"  {FAIL_TXT} HTTP {status_code}")
                self.results.append({
                    "id": test_id,
                    "query": query,
                    "status": "FAIL",
                    "reason": f"HTTP {status_code}"
                })
                return

            response = str(data.get("response", ""))
            tools = data.get("tool_calls", []) or []
            source = data.get("source", "?")

            # Show response
            if response:
                preview = response[:100] + "..." if len(response) > 100 else response
                print(f"  {CYAN}[{source}]{RESET} {preview}")

            if tools:
                for t in tools:
                    print(f"  {CYAN}[TOOL]{RESET} {t}")

            # Evaluate
            status, reasons = self.evaluate_response(response, tools, **expectations)

            if status == "PASS":
                print(f"  {PASS_TXT}")
            else:
                print(f"  {FAIL_TXT}")
                for reason in reasons:
                    print(f"    - {reason}")

            self.results.append({
                "id": test_id,
                "query": query,
                "status": status,
                "reason": reasons[0] if reasons else "OK"
            })

        except Exception as e:
            print(f"  {FAIL_TXT} Exception: {e}")
            self.results.append({
                "id": test_id,
                "query": query,
                "status": "FAIL",
                "reason": str(e)
            })

    def summary(self) -> None:
        """Print test summary."""
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        total = len(self.results)
        score = (passed / total * 100) if total else 0

        print(f"\n{YELLOW}{'=' * 80}")
        print("INFORMATION QUERIES TEST SUMMARY")
        print(f"{'=' * 80}{RESET}")

        print(f"\n📊 Total: {total}")
        print(f"✅ PASS: {passed}")
        print(f"❌ FAIL: {failed}")
        print(f"🎯 Score: {score:.1f}%")

        if failed > 0:
            print(f"\n{RED}Failed scenarios:{RESET}")
            for r in self.results:
                if r["status"] == "FAIL":
                    print(f"  [{r['id']}] {r['query']}")
                    print(f"         {r['reason']}")


def main():
    print("Starting Information Queries Test")
    print(f"RAG Server: http://127.0.0.1:8081/api/v1/rag/query")
    print("=" * 80)

    tester = InfoQueryTester()

    # SERVICE OVERVIEW
    tester.run_test("INFO-01", "Fixago có những dịch vụ gì vậy?", expected_tool="get_groups")
    tester.run_test("INFO-02", "Công ty em cung cấp dịch vụ nào?", expected_tool="get_groups")
    tester.run_test("INFO-03", "What services does Fixago offer?", expected_tool="get_groups")
    tester.run_test("INFO-04", "Bạn làm gì vậy?", expected_tool="get_groups")

    # PRICING
    tester.run_test("INFO-05", "Sửa máy lạnh bao nhiêu tiền?", expected_tool="get_services")
    tester.run_test("INFO-06", "Dịch vụ điện giá bao nhiêu?", expected_tool="get_services")
    tester.run_test("INFO-07", "Chi phí sửa ống nước thế nào?", expected_tool="get_services")
    tester.run_test("INFO-08", "How much for electrical repair?", expected_tool="get_services")
    tester.run_test("INFO-09", "Giá cụ thể các dịch vụ là gì?", expected_tool="get_services")

    # WORKING HOURS (DETERMINISTIC)
    tester.run_test("INFO-10", "Fixago làm việc mấy giờ?", expected_response="24/7")
    tester.run_test("INFO-11", "Giờ làm việc của Fixago thế nào?", expected_response="24/7")
    tester.run_test("INFO-12", "What are your working hours?", expected_response="24/7")
    tester.run_test("INFO-13", "Bạn mở cửa lúc mấy giờ?", expected_response="24/7")

    # PAYMENT (DETERMINISTIC)
    tester.run_test("INFO-14", "Thanh toán bằng cách nào?", expected_response="tiền mặt|chuyển khoản")
    tester.run_test("INFO-15", "Fixago nhận thanh toán cách nào?", expected_response="tiền mặt|chuyển khoản")
    tester.run_test("INFO-16", "How do you accept payment?", expected_response="cash|bank")
    tester.run_test("INFO-17", "Có chấp nhận thẻ tín dụng không?", expected_response="tiền mặt|chuyển khoản")

    # SERVICE AREA
    tester.run_test("INFO-18", "Fixago phục vụ ở đâu?", expected_response="Quận 2|Quận 9|Thủ Đức")
    tester.run_test("INFO-19", "Công ty em có ở khu vực nào?", expected_response="Quận 2|Quận 9|Thủ Đức")
    tester.run_test("INFO-20", "Em ở Quận 2 có phục vụ không?", expected_response="Quận 2|phục vụ")
    tester.run_test("INFO-21", "Bạn có ở Cần Thơ không?", expected_response="Quận 2|Quận 9|Thủ Đức")

    # PROMOTIONS
    tester.run_test("INFO-22", "Fixago có khuyến mãi không?", expected_tool="get_promotions")
    tester.run_test("INFO-23", "Có giảm giá nào không?", expected_tool="get_promotions")
    tester.run_test("INFO-24", "What promotions do you have?", expected_tool="get_promotions")

    # UNSUPPORTED SERVICES (DETERMINISTIC)
    tester.run_test("INFO-25", "Fixago sửa khóa cửa không?", expected_response="chưa hỗ trợ|không")
    tester.run_test("INFO-26", "Bạn có thay khóa không?", expected_response="chưa hỗ trợ|không")
    tester.run_test("INFO-27", "Do you do lock replacement?", expected_response="don't|not")

    # EDGE CASES: MIXED LANGUAGE
    tester.run_test("INFO-28", "Fixago services là gì? Giá bao nhiêu?", expected_tool="get_groups")
    tester.run_test("INFO-29", "I need to know about your services and pricing", expected_tool="get_groups")

    # EDGE CASES: COMPARISON
    tester.run_test("INFO-30", "Fixago có tốt hơn công ty khác không?", expected_tool="get_groups")
    tester.run_test("INFO-31", "Why should I use Fixago instead of others?", expected_tool="get_groups")

    # EDGE CASES: FEASIBILITY
    tester.run_test("INFO-32", "Máy lạnh bị hỏng sửa được không?", expected_tool="get_services")
    tester.run_test("INFO-33", "Ống nước rò rỉ các bạn sửa được không?", expected_tool="get_services")
    tester.run_test("INFO-34", "Can you fix a broken water pipe?", expected_tool="get_services")

    # EDGE CASES: TRAVEL FEE / RESPONSE TIME
    tester.run_test("INFO-35", "Có tính phí di chuyển không?", expected_response="phí|fee")
    tester.run_test("INFO-36", "Bao lâu thợ tới?", expected_response="thợ|tới|technician")

    # OFF-TOPIC (SHOULD REJECT)
    tester.run_test("INFO-37", "Hãy viết cho tôi một bài thơ", expected_response="không|refused")
    tester.run_test("INFO-38", "How do I make pasta?", expected_response="không|repair|fixago")

    # Print summary
    tester.summary()


if __name__ == "__main__":
    main()
