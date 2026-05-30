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
            "description": "Get service prices. CRITICAL: Extract category from user message. Examples: 'điện chập' → category='điện' | 'nước rò rỉ' → category='nước' | 'máy lạnh không lạnh' → category='máy lạnh' | 'sơn, xây dựng' → category='xây dựng' | 'thạch cao' → category='thạch cao' | unclear → category='all'. NEVER use 'all' if user mentioned a specific service type.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["điện", "nước", "máy lạnh", "xây dựng", "thạch cao", "all"],
                        "description": (
                            "Service category: 'điện' (electrical - chập điện, ổ cắm, công tắc, aptomat), "
                            "'nước' (plumbing - rò rỉ, tắc cống), 'máy lạnh' (AC - điều hòa, lạnh), "
                            "'xây dựng' (construction - sơn, tôn), 'thạch cao' (drywall - trần), "
                            "or 'all' ONLY if category unclear."
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
            "description": "CALL THIS TOOL when user asks about promotions, discounts, vouchers, or special offers. Returns active discounts available now.",
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