#!/usr/bin/env python3
"""
Comprehensive Test Suite for Strict Agent + Fallback Protection

Tests:
1. INFO questions (should answer, NOT book)
2. Unsupported services (should fallback)
3. Multi-question detection (should reject politely)
4. Repair requests (can ask for booking)
5. Hallucination detection (should use fallback)
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://127.0.0.1:8081/api/v1/rag/query"
TIMEOUT = 45

class TestResults:
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.timeout = 0
        self.results = []

    def add(self, name, passed, reason=""):
        self.total += 1
        if passed:
            self.passed += 1
        else:
            self.failed += 1
        self.results.append({
            "name": name,
            "passed": passed,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        })

    def print_summary(self):
        print("\n" + "=" * 100)
        print("📊 TEST RESULTS SUMMARY")
        print("=" * 100)
        print(f"✅ Passed: {self.passed}/{self.total}")
        print(f"❌ Failed: {self.failed}/{self.total}")
        print(f"⏱️  Timeout: {self.timeout}/{self.total}")
        print(f"Success Rate: {(self.passed*100//self.total) if self.total > 0 else 0}%")
        print("=" * 100)

        if self.failed > 0:
            print("\n❌ FAILED TESTS:")
            for r in self.results:
                if not r["passed"]:
                    print(f"  • {r['name']}")
                    if r["reason"]:
                        print(f"    Reason: {r['reason']}")


def test_query(test_name, query, should_contain=None, should_not_contain=None):
    """Test a single query"""
    try:
        response = requests.post(
            BASE_URL,
            json={"query": query, "history": []},
            timeout=TIMEOUT
        ).json()

        resp = response.get("response", "")

        # Validation
        passed = True
        reason = ""

        if should_contain:
            for phrase in should_contain:
                if phrase not in resp:
                    passed = False
                    reason = f"Expected '{phrase}' not found"
                    break

        if should_not_contain and passed:
            for phrase in should_not_contain:
                if phrase in resp:
                    passed = False
                    reason = f"Unexpected phrase '{phrase}' found"
                    break

        return passed, reason, resp

    except requests.exceptions.Timeout:
        return None, "Request timeout", ""
    except Exception as e:
        return False, str(e)[:80], ""


# ═══════════════════════════════════════════════════════════════════════════════
# TEST SUITES
# ═══════════════════════════════════════════════════════════════════════════════

def run_info_question_tests(results):
    """Test that INFO questions answer without booking"""
    print("\n🧪 TEST GROUP 1: INFO QUESTIONS (Should Answer, Not Book)")
    print("─" * 100)

    tests = [
        {
            "name": "Info: Pricing question",
            "query": "sửa máy lạnh bao nhiêu tiền?",
            "should_not": ["xin họ tên", "xin tên", "xin SĐT"]
        },
        {
            "name": "Info: Warranty question",
            "query": "Bảo hành bao lâu?",
            "should_not": ["xin họ tên", "đặt lịch"]
        },
        {
            "name": "Info: Promotion question",
            "query": "Có khuyến mãi không?",
            "should_not": ["xin họ tên", "xin tên"]
        },
        {
            "name": "Info: Hours question",
            "query": "Mấy giờ thì làm việc?",
            "should_not": ["xin họ tên", "đặt lịch"]
        },
        {
            "name": "Info: Area question",
            "query": "Bạn phục vụ ở đâu?",
            "should_not": ["xin họ tên", "đặt lịch"]
        },
    ]

    for test in tests:
        passed, reason, resp = test_query(
            test["name"],
            test["query"],
            should_not_contain=test.get("should_not", [])
        )

        if passed is None:
            print(f"⏱️  {test['name']}: TIMEOUT")
            results.timeout += 1
        elif passed:
            print(f"✅ {test['name']}: PASS")
            results.add(test['name'], True)
        else:
            print(f"❌ {test['name']}: FAIL - {reason}")
            results.add(test['name'], False, reason)


def run_unsupported_tests(results):
    """Test that unsupported services trigger fallback"""
    print("\n🧪 TEST GROUP 2: UNSUPPORTED SERVICES (Should Fallback)")
    print("─" * 100)

    tests = [
        {
            "name": "Unsupported: Door lock",
            "query": "bạn sửa khóa cửa được không?",
            "should": ["chưa hỗ trợ"]
        },
        {
            "name": "Unsupported: Oven",
            "query": "Có sửa lò nướng không?",
            "should": ["chưa hỗ trợ"]
        },
        {
            "name": "Unsupported: Refrigerator repair",
            "query": "Sửa tủ lạnh được không?",
            "should": ["chưa hỗ trợ"]
        },
    ]

    for test in tests:
        passed, reason, resp = test_query(
            test["name"],
            test["query"],
            should_contain=test.get("should", [])
        )

        if passed is None:
            print(f"⏱️  {test['name']}: TIMEOUT")
            results.timeout += 1
        elif passed:
            print(f"✅ {test['name']}: PASS")
            results.add(test['name'], True)
        else:
            print(f"❌ {test['name']}: FAIL - {reason}")
            results.add(test['name'], False, reason)


def run_multi_question_tests(results):
    """Test that multi-questions trigger polite rejection"""
    print("\n🧪 TEST GROUP 3: MULTI-QUESTIONS (Should Reject Politely)")
    print("─" * 100)

    tests = [
        {
            "name": "Multi: Services + Prices",
            "query": "Dịch vụ gì và giá bao nhiêu?",
            "should": ["chia nhỏ"]
        },
        {
            "name": "Multi: Service + Warranty (Single query allowed)",
            "query": "Sửa máy lạnh có bảo hành không?",
            "should_not": ["xin họ tên"]
        },
        {
            "name": "Multi: Multiple services",
            "query": "Sửa ống nước với thay bóng đèn được không?",
            "should": ["chia nhỏ"]
        },
    ]

    for test in tests:
        passed, reason, resp = test_query(
            test["name"],
            test["query"],
            should_contain=test.get("should", []),
            should_not_contain=test.get("should_not", [])
        )

        if passed is None:
            print(f"⏱️  {test['name']}: TIMEOUT")
            results.timeout += 1
        elif passed:
            print(f"✅ {test['name']}: PASS")
            results.add(test['name'], True)
        else:
            print(f"❌ {test['name']}: FAIL - {reason}")
            results.add(test['name'], False, reason)


def run_repair_tests(results):
    """Test that repair requests can ask for booking"""
    print("\n🧪 TEST GROUP 4: REPAIR REQUESTS (Can Ask for Booking)")
    print("─" * 100)

    tests = [
        {
            "name": "Repair: AC not cooling",
            "query": "Máy lạnh không lạnh",
        },
        {
            "name": "Repair: Electrical short circuit",
            "query": "Điện nhà bị chập",
        },
        {
            "name": "Repair: Water leak",
            "query": "Nước chảy liên tục",
        },
    ]

    for test in tests:
        passed, reason, resp = test_query(
            test["name"],
            test["query"],
        )

        if passed is None:
            print(f"⏱️  {test['name']}: TIMEOUT")
            results.timeout += 1
        elif resp and len(resp) > 10:
            print(f"✅ {test['name']}: PASS")
            results.add(test['name'], True)
        else:
            print(f"❌ {test['name']}: FAIL - Empty response")
            results.add(test['name'], False, "Empty response")


def run_deterministic_tests(results):
    """Test deterministic facts (hours, payment, area)"""
    print("\n🧪 TEST GROUP 5: DETERMINISTIC FACTS (Should Return Instantly)")
    print("─" * 100)

    tests = [
        {
            "name": "Deterministic: Hours",
            "query": "Mấy giờ làm việc?",
            "should": ["24/7"]
        },
        {
            "name": "Deterministic: Payment",
            "query": "Trả tiền cách nào?",
            "should": ["tiền mặt", "chuyển khoản"]
        },
    ]

    for test in tests:
        start = time.time()
        passed, reason, resp = test_query(
            test["name"],
            test["query"],
            should_contain=test.get("should", [])
        )
        latency = (time.time() - start) * 1000

        if passed is None:
            print(f"⏱️  {test['name']}: TIMEOUT")
            results.timeout += 1
        elif passed:
            print(f"✅ {test['name']}: PASS ({latency:.0f}ms)")
            results.add(test['name'], True)
        else:
            print(f"❌ {test['name']}: FAIL - {reason}")
            results.add(test['name'], False, reason)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("╔════════════════════════════════════════════════════════════════════════════════╗")
    print("║        🧪 STRICT AGENT TEST SUITE: Multi-Layer Validation                    ║")
    print("╚════════════════════════════════════════════════════════════════════════════════╝")

    print("\n⏳ Checking server connection...")
    try:
        requests.get(f"{BASE_URL}", timeout=5)
    except:
        print("❌ RAG server not responding on :8081")
        print("Start server with: source venv/bin/activate && python server.py")
        exit(1)

    print("✅ Server is responding\n")

    results = TestResults()

    run_deterministic_tests(results)
    run_info_question_tests(results)
    run_unsupported_tests(results)
    run_multi_question_tests(results)
    run_repair_tests(results)

    results.print_summary()

    # Save results to file
    with open("test_results.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": results.total,
                "passed": results.passed,
                "failed": results.failed,
                "timeout": results.timeout,
                "success_rate": (results.passed*100//results.total) if results.total > 0 else 0
            },
            "details": results.results
        }, f, indent=2)

    print("\n💾 Results saved to test_results.json")
