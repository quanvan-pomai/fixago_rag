"""
Fixago tool definitions — OpenAI-compatible function calling schema.
Used with cheesebrain cheese-server --jinja (Qwen2.5 Hermes 2 Pro native format).
"""

FIXAGO_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_groups",
            "description": (
                "Lấy danh sách nhóm/danh mục dịch vụ mà Fixago cung cấp. "
                "Gọi khi khách hỏi 'Fixago có dịch vụ gì', 'bên bạn làm những gì', "
                "'có sửa gì không', hoặc muốn biết tổng quan dịch vụ."
            ),
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
            "description": (
                "Tìm kiếm dịch vụ cụ thể, tra giá, xem hạng mục sửa chữa. "
                "Gọi khi khách hỏi giá, hỏi dịch vụ cụ thể, mô tả lỗi cần sửa. "
                "Dùng từ khóa nhóm chính: 'điện', 'nước', 'điện lạnh', 'xây dựng', 'thạch cao'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": (
                            "Từ khóa tìm kiếm dịch vụ. Luôn dùng tên nhóm chính: "
                            "'điện' (ổ cắm, chập điện, aptomat...), "
                            "'nước' (rò nước, nghẹt ống, bồn cầu...), "
                            "'điện lạnh' (máy lạnh, điều hòa, tủ lạnh...), "
                            "'xây dựng' (sơn, chống thấm, ốp lát...), "
                            "'thạch cao' (trần, vách ngăn...)."
                        ),
                        "enum": ["điện", "nước", "điện lạnh", "xây dựng", "thạch cao"],
                    }
                },
                "required": ["search"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_promotions",
            "description": (
                "Lấy danh sách khuyến mãi, mã giảm giá, voucher, ưu đãi hiện có. "
                "Gọi khi khách hỏi về khuyến mãi, giảm giá, mã coupon, ưu đãi."
            ),
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
            "description": (
                "Tạo đơn đặt lịch thợ. CHỈ gọi khi đã có đủ 3 thông tin: "
                "tên khách, số điện thoại, địa chỉ — VÀ khách đã xác nhận rõ ràng "
                "bằng: 'xác nhận', 'ok', 'đặt đi', 'được', 'chốt', 'yes', 'confirm'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Họ tên đầy đủ của khách hàng.",
                    },
                    "phone": {
                        "type": "string",
                        "description": "Số điện thoại liên hệ (10-11 chữ số, bắt đầu 0 hoặc +84).",
                    },
                    "address": {
                        "type": "string",
                        "description": "Địa chỉ cụ thể cần thợ đến sửa.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Mô tả tình trạng lỗi hoặc vấn đề cần sửa.",
                    },
                },
                "required": ["name", "phone", "address", "description"],
            },
        },
    },
]
