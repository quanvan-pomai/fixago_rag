"""
Test non-booking information queries about Fixago.
Focus: Service overview, pricing, hours, payment, area, promotions, unsupported services.
Including: Multi-question queries, edge cases, comparison questions, capability questions.
No booking confirmations expected - pure information gathering.
"""

test_scenarios = [
    # ─────────────────────────────────────────────────────────────────────────────
    # SECTION 1: SERVICE OVERVIEW QUESTIONS
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
    {
        "id": "INFO-04A",
        "query": "Giới thiệu về công ty Fixago đi",
        "expected_tool": "get_groups",
        "note": "Company introduction request"
    },
    {
        "id": "INFO-04B",
        "query": "Tell me about Fixago",
        "expected_tool": "get_groups",
        "note": "English company introduction"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # SECTION 2: PRICING QUESTIONS (WITH SPECIFIC SERVICES)
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
    {
        "id": "INFO-09A",
        "query": "Báo giá sửa xây dựng",
        "expected_tool": "get_services",
        "note": "Construction service pricing"
    },
    {
        "id": "INFO-09B",
        "query": "What's the cost range for your services?",
        "expected_tool": "get_services",
        "note": "English pricing range question"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # SECTION 3: WORKING HOURS QUESTIONS (DETERMINISTIC)
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
    {
        "id": "INFO-13A",
        "query": "Có làm việc vào ban đêm không?",
        "expected_response": "24/7",
        "note": "Night service inquiry"
    },
    {
        "id": "INFO-13B",
        "query": "Do you work on weekends?",
        "expected_response": "24/7|weekend",
        "note": "English weekend inquiry"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # SECTION 4: PAYMENT METHOD QUESTIONS (DETERMINISTIC)
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
        "expected_response": "cash|bank",
        "note": "English payment question"
    },
    {
        "id": "INFO-17",
        "query": "Có chấp nhận thẻ tín dụng không?",
        "expected_response": "tiền mặt|chuyển khoản",
        "note": "Credit card payment inquiry"
    },
    {
        "id": "INFO-17A",
        "query": "Nhận thanh toán online được không?",
        "expected_response": "chuyển khoản|online",
        "note": "Online payment inquiry"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # SECTION 5: SERVICE AREA / LOCATION QUESTIONS
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
        "expected_response": "Quận 2|Quận 9|Thủ Đức",
        "note": "Coverage outside service area"
    },
    {
        "id": "INFO-21A",
        "query": "Em sống ở Biên Hòa, có phục vụ không?",
        "expected_response": "Quận 2|Quận 9|Thủ Đức|chưa",
        "note": "Out-of-area city inquiry"
    },
    {
        "id": "INFO-21B",
        "query": "Are you available in District 1?",
        "expected_response": "Quận 2|Quận 9|Thủ Đức",
        "note": "English location inquiry"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # SECTION 6: PROMOTION / DISCOUNT QUESTIONS
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
    {
        "id": "INFO-24A",
        "query": "Xin voucher hoặc mã giảm giá",
        "expected_tool": "get_promotions",
        "note": "Direct voucher request"
    },
    {
        "id": "INFO-24B",
        "query": "Có event ưu đãi gì hôm nay không?",
        "expected_tool": "get_promotions",
        "note": "Daily promotion check"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # SECTION 7: UNSUPPORTED SERVICES (DETERMINISTIC)
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
    {
        "id": "INFO-27A",
        "query": "Có sửa tủ lạnh không?",
        "expected_response": "chưa|không|dịch vụ khác",
        "note": "Refrigerator repair (likely unsupported)"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # SECTION 8: MULTI-QUESTION QUERIES (MAIN FOCUS)
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-28",
        "query": "Fixago có những dịch vụ gì và giá bao nhiêu?",
        "expected_tool": "get_groups|get_services",
        "note": "Two questions: services + pricing (should handle both)"
    },
    {
        "id": "INFO-28A",
        "query": "Fixago ở đâu, mấy giờ làm việc, thanh toán bằng cách nào?",
        "expected_response": "Quận 2|24/7|tiền mặt|chuyển khoản",
        "note": "Three deterministic questions in one message"
    },
    {
        "id": "INFO-28B",
        "query": "Bạn có dịch vụ gì, giá thế nào, có khuyến mãi không?",
        "expected_tool": "get_groups|get_services|get_promotions",
        "note": "Three-part info query: services, pricing, promotions"
    },
    {
        "id": "INFO-28C",
        "query": "Services là gì? Pricing bao nhiêu? Ở đâu? Mấy giờ?",
        "expected_response": "dịch vụ|giá|Quận|24/7",
        "note": "Mixed English/Vietnamese multi-question"
    },
    {
        "id": "INFO-29",
        "query": "I need to know about your services and pricing",
        "expected_tool": "get_groups|get_services",
        "note": "English multi-question query"
    },
    {
        "id": "INFO-29A",
        "query": "Tell me: what do you repair, how much it costs, and where you operate?",
        "expected_tool": "get_groups|get_services|location",
        "note": "Detailed English multi-question"
    },
    {
        "id": "INFO-29B",
        "query": "công ty em là gì? bạn làm gì? giá bao nhiêu? ở đâu?",
        "expected_response": "Fixago|dịch vụ|giá|Quận",
        "note": "Four separate questions in Vietnamese"
    },
    {
        "id": "INFO-29C",
        "query": "Sửa điện được không, bao nhiêu tiền, có khuyến mãi không?",
        "expected_tool": "get_services|get_promotions",
        "note": "Service capability + pricing + promotion"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # SECTION 9: COMPARISON & DIFFERENTIATION QUESTIONS
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
    {
        "id": "INFO-31A",
        "query": "So sánh Fixago với các công ty sửa chữa khác",
        "expected_tool": "get_groups",
        "note": "Direct comparison request"
    },
    {
        "id": "INFO-31B",
        "query": "Fixago khác gì với mấy công ty khác, sao tôi nên chọn?",
        "expected_tool": "get_groups",
        "note": "Multi-part comparison question"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # SECTION 10: CAPABILITY & FEASIBILITY QUESTIONS (NO BOOKING INTENT)
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
    {
        "id": "INFO-34A",
        "query": "Bạn có khả năng sửa điện không?",
        "expected_tool": "get_services",
        "note": "Capability check for electrical"
    },
    {
        "id": "INFO-34B",
        "query": "Sửa được lắp máy lạnh mới không?",
        "expected_tool": "get_services",
        "note": "Installation capability question"
    },
    {
        "id": "INFO-34C",
        "query": "Do you handle emergency repairs?",
        "expected_tool": "get_services|hours",
        "note": "Emergency service capability"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # SECTION 11: SERVICE DETAILS & PROCESS QUESTIONS
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-35",
        "query": "Có tính phí di chuyển không?",
        "expected_response": "phí|di chuyển|bao gồm",
        "note": "Travel fee inquiry"
    },
    {
        "id": "INFO-36",
        "query": "Bao lâu thợ tới?",
        "expected_response": "thợ|tới|phút|giờ",
        "note": "Technician arrival time"
    },
    {
        "id": "INFO-36A",
        "query": "Quá trình sửa chữa mất bao lâu?",
        "expected_response": "60|phút|giờ|thời gian",
        "note": "Service duration inquiry"
    },
    {
        "id": "INFO-36B",
        "query": "Làm sao để đặt lịch?",
        "expected_response": "đặt|lịch|thông tin|tên|điện thoại",
        "note": "Booking process inquiry (info only)"
    },
    {
        "id": "INFO-36C",
        "query": "What's the process to hire your technician?",
        "expected_response": "process|book|contact",
        "note": "English process inquiry"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # SECTION 12: WARRANTY & GUARANTEE QUESTIONS
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-37",
        "query": "Có bảo hành không?",
        "expected_response": "bảo hành|warranty|thợ",
        "note": "Warranty inquiry"
    },
    {
        "id": "INFO-37A",
        "query": "Nếu sửa xong vẫn lỗi thì sao?",
        "expected_response": "liên hệ|thợ|bảo hành",
        "note": "Quality guarantee question"
    },
    {
        "id": "INFO-37B",
        "query": "Do you guarantee your work?",
        "expected_response": "guarantee|warranty|technician",
        "note": "English guarantee question"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # SECTION 13: EDGE CASES - CHAINED INFO QUESTIONS
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-38",
        "query": "Sửa điện giá bao nhiêu, có khuyến mãi không, có thợ vào ban đêm không?",
        "expected_tool": "get_services|get_promotions",
        "note": "Three-part pricing + promotion + availability"
    },
    {
        "id": "INFO-38A",
        "query": "Ở tôi Quận 1, các bạn có phục vụ không, mấy giờ tới, bao nhiêu tiền?",
        "expected_response": "Quận|phục vụ|giá",
        "note": "Location + service + timing + price"
    },
    {
        "id": "INFO-38B",
        "query": "I live in District 9, what services you provide, how much, and how long?",
        "expected_tool": "get_groups|get_services",
        "note": "English multi-question with location context"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # SECTION 14: TRICKY CASES - INFO THAT SOUNDS LIKE BOOKING
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-39",
        "query": "Tôi có vấn đề với máy lạnh, bạn sửa được không, giá bao nhiêu?",
        "expected_tool": "get_services",
        "note": "Problem description + feasibility + price (NOT booking intent)"
    },
    {
        "id": "INFO-39A",
        "query": "Nhà tôi chập điện rồi, sửa được không, mất bao nhiêu tiền?",
        "expected_tool": "get_services",
        "note": "Urgent problem + info (NOT booking - just asking)"
    },
    {
        "id": "INFO-39B",
        "query": "I have a broken water pipe. Can you fix it? How much does it cost?",
        "expected_tool": "get_services",
        "note": "English problem + inquiry (no booking signal)"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # SECTION 15: OFF-TOPIC QUESTIONS (SHOULD REJECT)
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-40",
        "query": "Hãy viết cho tôi một bài thơ",
        "expected_response": "không|lạc đề|sửa chữa",
        "note": "Poetry request - off-topic"
    },
    {
        "id": "INFO-41",
        "query": "How do I make pasta?",
        "expected_response": "không|repair|fixago",
        "note": "Cooking question - off-topic"
    },
    {
        "id": "INFO-41A",
        "query": "Bạn là người hay máy?",
        "expected_response": "AI|trợ lý|sửa chữa",
        "note": "Identity question (may answer or redirect)"
    },
    {
        "id": "INFO-41B",
        "query": "Tôi muốn học lập trình",
        "expected_response": "không|lạc đề|fixago",
        "note": "Off-topic education request"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # SECTION 16: CASUAL / COLLOQUIAL INFO QUESTIONS
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-42",
        "query": "Bro, Fixago sửa được cái gì?",
        "expected_tool": "get_groups",
        "note": "Casual slang service inquiry"
    },
    {
        "id": "INFO-42A",
        "query": "Em có sửa điện không bạn?",
        "expected_tool": "get_services",
        "note": "Casual electrical inquiry"
    },
    {
        "id": "INFO-42B",
        "query": "Yo, how much for AC repair?",
        "expected_tool": "get_services",
        "note": "Casual English pricing"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # SECTION 17: NO-ACCENT VIETNAMESE INFO QUESTIONS
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-43",
        "query": "Fixago co nhung dich vu gi",
        "expected_tool": "get_groups",
        "note": "Service overview without diacritics"
    },
    {
        "id": "INFO-43A",
        "query": "sua may lanh bao nhieu tien",
        "expected_tool": "get_services",
        "note": "AC pricing without accents"
    },
    {
        "id": "INFO-43B",
        "query": "co khuyen mai khong",
        "expected_tool": "get_promotions",
        "note": "Promotion question without accents"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # SECTION 18: IDENTITY & INTRODUCTION (INFO, NOT BOOKING)
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-44",
        "query": "Bạn là ai?",
        "expected_response": "Fixie|trợ lý|AI",
        "note": "Identity question"
    },
    {
        "id": "INFO-44A",
        "query": "Công ty Fixago là gì?",
        "expected_tool": "get_groups",
        "note": "Company introduction"
    },
    {
        "id": "INFO-44B",
        "query": "Who runs Fixago?",
        "expected_response": "Fixago|company|sửa chữa",
        "note": "English company inquiry"
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # SECTION 19: STRESS TEST - "ẢO MA CANADA" (CHAOS MULTI-INTENT)
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "INFO-45",
        "query": "Nhà anh bị hư ống nước với gãy luôn chìa khóa trong ổ, bên em thông cống giá sao, tiện thể bẻ luôn ổ khóa thì tổng bill nhiêu?",
        "expected_tool": "get_services",
        "expected_response": "từ chối sửa khóa",
        "note": "TRICKY: Trộn lẫn dịch vụ hỗ trợ (ống nước/giá) và dịch vụ cấm (sửa khóa) trong cùng 1 câu hỏi giá."
    },
    {
        "id": "INFO-46",
        "query": "Đêm Giao thừa 3h sáng mưa bão ở Thủ Đức có thợ qua sửa chập điện không? Ngày Lễ thì có xài được voucher không hay lại charge thêm phí di chuyển?",
        "expected_tool": "get_services|get_promotions",
        "expected_response": "24/7|miễn phí di chuyển",
        "note": "EXTREME EDGE CASE: Test policy (giờ giấc, lễ Tết, phí di chuyển) + check khuyến mãi + hỏi năng lực sửa điện."
    },
    {
        "id": "INFO-47",
        "query": "yo bot, ac nha minh khong lanh, fix cai nay mat nhieu time khong? do you take transfer hay chi cash vay b?",
        "expected_tool": "get_services",
        "expected_response": "tiền mặt|chuyển khoản",
        "note": "PARSING HELL: Trộn 3 ngôn ngữ (Việt không dấu, tiếng Anh, tiếng lóng) + hỏi thời gian + hỏi phương thức thanh toán."
    },
    {
        "id": "INFO-48",
        "query": "Ủa lỡ thợ bên em qua làm bể thêm cái bồn cầu thì ai đền? Mà sẵn cho hỏi giá thông bồn nghẹt mỡ là nhiêu, có tính phí thợ chạy qua coi rồi không làm không?",
        "expected_tool": "get_services",
        "expected_response": "bảo hành|phí di chuyển",
        "note": "THE INTERROGATOR: Đặt câu hỏi giả định (bắt đền/bảo hành) + hỏi giá cụ thể + hỏi policy phí kiểm tra."
    },
    {
        "id": "INFO-49",
        "query": "Tường nhà đang thấm nước thành vũng to đùng luôn rồi cứu với! Cho anh hỏi công ty em chi nhánh ở đâu, có làm ngay bây giờ được không và giá rổ thế nào để anh chuẩn bị lúa?",
        "expected_tool": "get_services",
        "expected_response": "Quận|24/7",
        "note": "PANIC MODE: Đưa bối cảnh khẩn cấp (thấm nước) giấu Intent bên trong + hỏi chi nhánh + hỏi giờ làm + hỏi giá bằng tiếng lóng (lúa)."
    },
    {
        "id": "INFO-50",
        "query": "Dịch vụ bên em gồm những gì dợ, có nhận dán giấy dán tường với sơn lại ban công không, tài chính sinh viên thì có bớt chút đỉnh không shop?",
        "expected_tool": "get_groups|get_services|get_promotions",
        "note": "THE NEGOTIATOR: Hỏi tổng quan (get_groups) + hỏi chi tiết ngách (xây dựng) + xin giảm giá ngầm (bớt chút đỉnh)."
    },
    {
        "id": "INFO-51",
        "query": "Làm thơ tặng anh đi rồi anh book lịch. Đùa thôi, Fixago của bạn khác gì thợ đụng ngoài đường, và trả tiền qua Momo được ko?",
        "expected_tool": "get_groups",
        "expected_response": "chuyển khoản|từ chối làm thơ",
        "note": "THE JOKER: Mở đầu bằng Off-topic (làm thơ) + Phủ định ngay lập tức + Hỏi so sánh + Hỏi phương thức thanh toán ví điện tử."
    },
    {
        "id": "INFO-52",
        "query": "My house in District 1 has a broken AC and a broken lock. Can you come at 2 AM? How much for both?",
        "expected_tool": "get_services",
        "expected_response": "District 2, 9, Thu Duc|not support lock|24/7",
        "note": "ENGLISH COMBO BREAKER: Ngoài vùng phục vụ (Q1) + Dịch vụ cấm (lock) + Giờ khắc nghiệt (2 AM) + Hỏi giá."
    },
    {
        "id": "INFO-53",
        "query": "sua dien voi sua nuoc cai nao re hon, va cho hoi cong ty co nhan thuc tap sinh IT khong?",
        "expected_tool": "get_services",
        "expected_response": "không|từ chối",
        "note": "UNEXPECTED PIVOT: Hỏi so sánh giá 2 dịch vụ cùng lúc + hỏi tuyển dụng (Off-topic cực gắt)."
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # SECTION 20: REAL-WORLD CUSTOMER DUMPS (KỂ LỂ, HỎI DỒN DẬP, KÈM ĐIỀU KIỆN)
    # ─────────────────────────────────────────────────────────────────────────────
    {
        "id": "REAL-01",
        "query": "Ống nước trên lầu rỉ ướt hết tường rồi chập luôn ổ cắm điện xẹt lửa lụp bụp nãy giờ. Thợ qua ngay bây giờ được không, báo giá trọn gói nhé chứ đừng tới nơi mới vẽ thêm bệnh lấy thêm tiền.",
        "expected_tool": "get_services(nước) | get_services(điện)",
        "expected_response": "24/7",
        "note": "URGENT + MULTI-SERVICE + CONSTRAINT: Khách bị 2 lỗi chéo nhau (Điện + Nước), có yếu tố khẩn cấp (xẹt lửa - cần trigger Guardrail an toàn), và rào trước chuyện 'báo giá trọn gói'."
    },
    {
        "id": "REAL-02",
        "query": "Sửa lỗi máy lạnh chớp đèn quạt không quay cỡ bao nhiêu shop? Sinh viên cuối tháng còn đúng 300k tiền mặt, nếu đắt hơn thì cho cà thẻ hay nợ sang đầu tháng được không?",
        "expected_tool": "get_services(máy lạnh)",
        "expected_response": "tiền mặt|chuyển khoản|từ chối nợ",
        "note": "BUDGET CONSTRAINT: Khách đưa ra ngân sách giới hạn, hỏi giá máy lạnh, và đưa ra phương thức thanh toán cực đoan (nợ/cà thẻ)."
    },
    {
        "id": "REAL-03",
        "query": "Hôm bữa gọi thợ ngoài sửa cái tủ lạnh dỏm 3 ngày hư lại, bực mình ghê. Bên em sửa điện lạnh có bảo hành đàng hoàng giấy tờ không, và lỡ thợ làm hỏng thêm đồ thì công ty giải quyết sao?",
        "expected_tool": "get_services(máy lạnh)",
        "expected_response": "bảo hành|cam kết",
        "note": "TRAUMATIZED CUSTOMER: Bắt đầu bằng việc kể lể bực tức. Không có ý định đặt lịch ngay mà muốn check độ uy tín (bảo hành, đền bù) + hỏi gián tiếp dịch vụ điện lạnh."
    },
    {
        "id": "REAL-04",
        "query": "Vợ anh kêu cái máy giặt nó kêu rầm rầm lúc vắt với bồn cầu nhấn nước không trôi, qua kiểm tra không sửa thì có thu phí không em? Chiều 6h anh mới đi làm về nha, lúc đó thợ còn làm không?",
        "expected_tool": "get_services(máy lạnh) | get_services(nước)",
        "expected_response": "phí kiểm tra|24/7",
        "note": "THE PROXY (Người gọi thay): Kể bệnh qua lời người khác + 2 dịch vụ không liên quan (Máy giặt + Bồn cầu) + Hỏi phí kiểm tra + Check giờ làm việc sau giờ hành chính."
    },
    {
        "id": "REAL-05",
        "query": "Anh ở chung cư cao cấp bên Quận 2, quy định ban quản lý là cuối tuần không cho khoan đục ồn ào. Chủ nhật thợ qua sơn lại tường với đóng thạch cao được không? Đội bên em có bao dọn dẹp vệ sinh sau khi làm không?",
        "expected_tool": "get_services(xây dựng) | get_services(thạch cao)",
        "expected_response": "Quận 2|cuối tuần",
        "note": "LOGISTICS & RULES: Đưa ra ngữ cảnh phức tạp của chung cư + Hỏi dịch vụ thi công nặng (xây dựng, thạch cao) + Hỏi về policy dọn dẹp (edge case rất hay gặp ngoài đời)."
    },
    {
        "id": "REAL-06",
        "query": "Thợ bên em biết lắp tivi treo tường không? Với lại cái ổ khóa cửa phòng ngủ bị kẹt cứng nhốt con mèo ở trỏng, qua phá giùm anh rồi anh gửi tiền nước, báo giá luôn nhanh lên.",
        "expected_tool": "get_services(điện/all)",
        "expected_response": "không hỗ trợ sửa khóa",
        "note": "MIXED SUPPORTED & UNSUPPORTED: Yêu cầu lắp TV (thường thuộc thợ điện) + Yêu cầu phá khóa (không hỗ trợ) + Thái độ hối thúc."
    },
    {
        "id": "REAL-07",
        "query": "Mình muốn cải tạo lại ban công, lót gạch mới, làm lại đường ống thoát nước chỗ máy giặt cho khỏi nghẹt. Cho mình hỏi quy trình làm việc bên bạn sao, bao lâu có thợ qua khảo sát?",
        "expected_tool": "get_services(xây dựng) | get_services(nước)",
        "expected_response": "quy trình|khảo sát|15-30 phút",
        "note": "PROJECT PLANNING: Dự án mini gồm lót gạch (Xây dựng) + Ống nước (Nước). Khách không hỏi giá mà hỏi về Quy trình (Process) và Thời gian khảo sát (SLA)."
    },
    {
        "id": "REAL-08",
        "query": "Dạo này công ty có mã giảm giá nào cho khách cũ không em, anh tính kêu thợ qua vệ sinh 3 cái máy lạnh với bơm gas, nếu làm nhiều vậy có được bớt tiền di chuyển không?",
        "expected_tool": "get_promotions | get_services(máy lạnh)",
        "expected_response": "phí di chuyển đã bao gồm",
        "note": "BULK ORDER NEGOTIATION: Hỏi khuyến mãi + Báo số lượng lớn (3 máy) + Hỏi để mặc cả phí di chuyển (cần bot nhớ policy là free phí di chuyển)."
    }
]

def print_categories_summary():
    """Print test scenarios grouped by category."""
    categories = {}
    for scenario in test_scenarios:
        scenario_id = scenario["id"]
        category = scenario_id.rsplit("-", 1)[0]  # e.g., "INFO-01" -> "INFO"
        if category not in categories:
            categories[category] = []
        categories[category].append(scenario)

    print("\n" + "="*80)
    print("INFORMATION QUERIES TEST SUITE - COMPREHENSIVE")
    print("="*80)

    # Count by section
    section_counts = {}
    for scenario in test_scenarios:
        note = scenario["note"]
        # Extract section from note or use generic counting
        if "Service overview" in note or "introduction" in note:
            section = "Service Overview"
        elif "pricing" in note or "cost" in note or "Pricing" in note:
            section = "Pricing"
        elif "hours" in note or "Hours" in note or "weekend" in note:
            section = "Business Hours"
        elif "payment" in note or "Payment" in note:
            section = "Payment Methods"
        elif "location" in note or "area" in note or "Area" in note:
            section = "Service Area"
        elif "promotion" in note or "Promotion" in note:
            section = "Promotions"
        elif "unsupported" in note or "lock" in note:
            section = "Unsupported Services"
        elif "multi" in note or "Multiple" in note or "two|three|four" in note:
            section = "Multi-Question"
        elif "comparison" in note or "Comparison" in note:
            section = "Comparison"
        elif "capability" in note or "Capability" in note or "feasibility" in note:
            section = "Capability"
        elif "process" in note or "Process" in note or "travel|fee" in note:
            section = "Service Details"
        elif "warranty" in note or "guarantee" in note:
            section = "Warranty"
        elif "casual" in note or "Casual" in note or "slang" in note:
            section = "Casual/Colloquial"
        elif "accent" in note or "diacritic" in note:
            section = "No-Accent Vietnamese"
        elif "identity" in note or "Identity" in note or "introduction" in note:
            section = "Identity/Intro"
        elif "off-topic" in note or "OFF-TOPIC" in note:
            section = "Off-Topic"
        else:
            section = "Other"

        if section not in section_counts:
            section_counts[section] = 0
        section_counts[section] += 1

    print(f"\n📊 TOTAL SCENARIOS: {len(test_scenarios)}\n")
    for section, count in sorted(section_counts.items(), key=lambda x: -x[1]):
        print(f"  • {section}: {count} scenarios")

    print("\n" + "="*80)
    print("TEST SCENARIOS BY CATEGORY")
    print("="*80)


if __name__ == "__main__":
    print_categories_summary()

    print("\nAll Scenarios:")
    for scenario in test_scenarios:
        print(f"\n[{scenario['id']}] {scenario['query']}")
        print(f"    Expected: {scenario.get('expected_tool') or scenario.get('expected_response')}")
        print(f"    Note: {scenario['note']}")

    print(f"\n\n{'='*80}")
    print(f"TOTAL: {len(test_scenarios)} information query test scenarios")
    print(f"{'='*80}")
