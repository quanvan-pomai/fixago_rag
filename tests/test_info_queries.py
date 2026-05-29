"""
Test non-booking information queries about Fixago.
Focus: Service overview, pricing, hours, payment, area, promotions, unsupported services.
No booking confirmations expected.
"""

test_scenarios = [
    # ─────────────────────────────────────────────────────────────────────────────
    # SERVICE OVERVIEW QUESTIONS
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-01",
        "query": "Fixago có những dịch vụ gì vậy?",
        "expected_tool": "get_groups",
        "note": "Service overview in Vietnamese"
    },
    {
        "id": "INFO-02",
        "query": "Công ty em cung cấp dịch vụ nào?",
        "expected_tool": "get_groups",
        "note": "Alternative service overview phrasing"
    },
    {
        "id": "INFO-03",
        "query": "What services does Fixago offer?",
        "expected_tool": "get_groups",
        "note": "Service overview in English"
    },
    {
        "id": "INFO-04",
        "query": "Bạn làm gì vậy?",
        "expected_tool": "get_groups",
        "note": "Casual service overview question"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # PRICING QUESTIONS (WITH SPECIFIC SERVICES)
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-05",
        "query": "Sửa máy lạnh bao nhiêu tiền?",
        "expected_tool": "get_services",
        "note": "AC repair pricing"
    },
    {
        "id": "INFO-06",
        "query": "Dịch vụ điện giá bao nhiêu?",
        "expected_tool": "get_services",
        "note": "Electrical service pricing"
    },
    {
        "id": "INFO-07",
        "query": "Chi phí sửa ống nước thế nào?",
        "expected_tool": "get_services",
        "note": "Plumbing service pricing"
    },
    {
        "id": "INFO-08",
        "query": "How much for electrical repair?",
        "expected_tool": "get_services",
        "note": "English pricing question"
    },
    {
        "id": "INFO-09",
        "query": "Giá cụ thể các dịch vụ là gì?",
        "expected_tool": "get_services",
        "note": "General pricing inquiry"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # WORKING HOURS QUESTIONS (DETERMINISTIC)
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-10",
        "query": "Fixago làm việc mấy giờ?",
        "expected_response": "24/7",
        "note": "Working hours question - should be deterministic"
    },
    {
        "id": "INFO-11",
        "query": "Giờ làm việc của Fixago thế nào?",
        "expected_response": "24/7",
        "note": "Alternative hours phrasing"
    },
    {
        "id": "INFO-12",
        "query": "What are your working hours?",
        "expected_response": "24/7",
        "note": "English hours question"
    },
    {
        "id": "INFO-13",
        "query": "Bạn mở cửa lúc mấy giờ?",
        "expected_response": "24/7",
        "note": "Casual hours question"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # PAYMENT METHOD QUESTIONS (DETERMINISTIC)
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-14",
        "query": "Thanh toán bằng cách nào?",
        "expected_response": "tiền mặt|chuyển khoản",
        "note": "Payment method question - deterministic"
    },
    {
        "id": "INFO-15",
        "query": "Fixago nhận thanh toán cách nào?",
        "expected_response": "tiền mặt|chuyển khoản",
        "note": "Alternative payment phrasing"
    },
    {
        "id": "INFO-16",
        "query": "How do you accept payment?",
        "expected_response": "cash|bank transfer",
        "note": "English payment question"
    },
    {
        "id": "INFO-17",
        "query": "Có chấp nhận thẻ tín dụng không?",
        "expected_response": "tiền mặt|chuyển khoản",
        "note": "Credit card payment inquiry"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # SERVICE AREA / LOCATION QUESTIONS
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-18",
        "query": "Fixago phục vụ ở đâu?",
        "expected_response": "Quận 2|Quận 9|Thủ Đức",
        "note": "Service area question"
    },
    {
        "id": "INFO-19",
        "query": "Công ty em có ở khu vực nào?",
        "expected_response": "Quận 2|Quận 9|Thủ Đức",
        "note": "Alternative area phrasing"
    },
    {
        "id": "INFO-20",
        "query": "Em ở Quận 2 có phục vụ không?",
        "expected_response": "Quận 2|phục vụ",
        "note": "Area coverage inquiry"
    },
    {
        "id": "INFO-21",
        "query": "Bạn có ở Cần Thơ không?",
        "expected_tool": "static_fallback",
        "expected_response": "Quận 2|Quận 9|Thủ Đức",
        "note": "Coverage outside service area - should trigger area detection"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # PROMOTION / DISCOUNT QUESTIONS
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-22",
        "query": "Fixago có khuyến mãi không?",
        "expected_tool": "get_promotions",
        "note": "Promotion inquiry"
    },
    {
        "id": "INFO-23",
        "query": "Có giảm giá nào không?",
        "expected_tool": "get_promotions",
        "note": "Discount inquiry"
    },
    {
        "id": "INFO-24",
        "query": "What promotions do you have?",
        "expected_tool": "get_promotions",
        "note": "English promotion question"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # UNSUPPORTED SERVICES (DETERMINISTIC)
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-25",
        "query": "Fixago sửa khóa cửa không?",
        "expected_response": "chưa hỗ trợ|không",
        "note": "Unsupported lock service"
    },
    {
        "id": "INFO-26",
        "query": "Bạn có thay khóa không?",
        "expected_response": "chưa hỗ trợ|không",
        "note": "Lock replacement question"
    },
    {
        "id": "INFO-27",
        "query": "Do you do lock replacement?",
        "expected_response": "don't|not|doesn't",
        "note": "English lock question"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # EDGE CASES: MIXED LANGUAGE
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-28",
        "query": "Fixago services là gì? Giá bao nhiêu?",
        "expected_tool": "get_groups",
        "note": "Mixed English/Vietnamese - multiple questions"
    },
    {
        "id": "INFO-29",
        "query": "I need to know about your services and pricing",
        "expected_tool": "get_groups",
        "note": "English multi-question"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # EDGE CASES: COMPARISON WITH COMPETITORS
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-30",
        "query": "Fixago có tốt hơn công ty khác không?",
        "expected_tool": "get_groups",
        "note": "Comparison question - should redirect to services"
    },
    {
        "id": "INFO-31",
        "query": "Why should I use Fixago instead of others?",
        "expected_tool": "get_groups",
        "note": "English comparison"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # EDGE CASES: INFORMATION WITH REPAIR KEYWORDS BUT NOT BOOKING
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-32",
        "query": "Máy lạnh bị hỏng sửa được không?",
        "expected_tool": "get_services",
        "note": "Repair feasibility question"
    },
    {
        "id": "INFO-33",
        "query": "Ống nước rò rỉ các bạn sửa được không?",
        "expected_tool": "get_services",
        "note": "Capability question"
    },
    {
        "id": "INFO-34",
        "query": "Can you fix a broken water pipe?",
        "expected_tool": "get_services",
        "note": "English capability question"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # EDGE CASES: TRAVEL FEE / RESPONSE TIME
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-35",
        "query": "Có tính phí di chuyển không?",
        "expected_response": "Phí",
        "note": "Travel fee inquiry - should be answered by LLM from knowledge"
    },
    {
        "id": "INFO-36",
        "query": "Bao lâu thợ tới?",
        "expected_response": "thợ|tới",
        "note": "Technician arrival time"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # EDGE CASES: OFF-TOPIC (SHOULD REJECT)
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-37",
        "query": "Hãy viết cho tôi một bài thơ",
        "expected_response": "không",
        "note": "Poetry request - off-topic"
    },
    {
        "id": "INFO-38",
        "query": "How do I make pasta?",
        "expected_response": "không|repair|home",
        "note": "Cooking question - off-topic (should reject)"
    },
]

if __name__ == "__main__":
    print(f"Total test scenarios: {len(test_scenarios)}")
    for scenario in test_scenarios:
        print(f"\n[{scenario['id']}] {scenario['query']}")
        print(f"    Expected: {scenario.get('expected_tool') or scenario.get('expected_response')}")
        print(f"    Note: {scenario['note']}")
