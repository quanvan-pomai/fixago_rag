"""
Fixago tool definitions — OpenAI-compatible function calling schema.
Optimized for low-latency & minimal token context (Token Golfing).
"""

FIXAGO_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_groups",
            "description": "CRITICAL: Call this tool FIRST when user asks about services. Matches: 'what services', 'dịch vụ gì', 'những dịch vụ', 'làm gì', 'Fixago có gì', 'có những dịch vụ nào'. Returns all service categories (Điện, Nước, Máy lạnh, Xây dựng, Thạch cao). MUST call before asking for contact info.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_services",
            "description": "CALL THIS TOOL when user asks about price/cost OR describes repair issue. INFER category: 'ổ cắm'/socket/outlet/electrical → 'điện'; 'nước'/water/leak/rò rỉ → 'nước'; 'máy lạnh'/AC/cold → 'máy lạnh'; 'xây dựng'/construction/build → 'xây dựng'; 'thạch cao'/drywall → 'thạch cao'. Use 'all' if unclear.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["điện", "nước", "máy lạnh", "xây dựng", "thạch cao", "all"],
                        "description": (
                            "Choose category from context: điện (electrical), nước (plumbing), máy lạnh (AC), "
                            "xây dựng (construction), thạch cao (drywall), or 'all' if unsure."
                        ),
                    }
                },
                "required": ["category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_promotions",
            "description": "Tra khuyến mãi, giảm giá, voucher, ưu đãi.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_booking",
            "description": "Tạo đơn đặt lịch. CHỈ gọi khi CÓ ĐỦ tên, SĐT, địa chỉ VÀ khách ĐÃ XÁC NHẬN (ok, chốt, đặt đi).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Họ tên khách.",
                    },
                    "phone": {
                        "type": "string",
                        "description": "SĐT liên hệ (10-11 số).",
                    },
                    "address": {
                        "type": "string",
                        "description": "Địa chỉ sửa chữa.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Mô tả lỗi ngắn gọn.",
                    },
                },
                "required": ["name", "phone", "address", "description"],
            },
        },
    },
]