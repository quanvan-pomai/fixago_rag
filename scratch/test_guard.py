import os
import sys

sys.path.insert(0, os.path.abspath("."))

from core.guardrails import is_offtopic, deterministic_business_reply, _is_repair_intent
from core.intent_router import detect_user_language

queries = [
    "Cho mình hỏi nếu mình muốn sửa cái tivi bị mất hình thì bên bạn có nhận không?",
    "Tôi cần thợ đến ngay bây giờ để sửa đường ống nước bị bể ở Quận 9, khoảng 3 giờ sáng có được không?",
    "Bạn là ai và công ty bạn nằm ở quận mấy vậy?",
    "Phí di chuyển của thợ là bao nhiêu, và mình có thể trả bằng thẻ tín dụng được không?",
    "Tôi muốn biết dịch vụ lắp đặt máy lạnh và sơn lại phòng khách giá bao nhiêu?",
    "Bên mình có bảo hành cho dịch vụ sửa chữa điện chập chờn không, và bảo hành bao lâu?",
    "Cho mình xin bảng giá tham khảo các dịch vụ sửa chữa bên bạn được không?",
    "Tôi bị kẹt cửa ngoài ban công, có thợ nào đến mở khóa gấp giúp tôi không?",
    "Can you tell me if you guys work on Sundays and how much is the plumbing service?",
    "Dạ alo, nhà mình tự dưng bị cúp điện toàn bộ, gọi thợ mất bao lâu thì tới và có tính thêm tiền đi lại không?",
]

print("=== KIỂM TRA LOGIC GUARDRAILS MỚI (REPAIR INTENT FILTER) ===")
for i, q in enumerate(queries, 1):
    print(f"\n[Câu {i}]: {q}")
    
    is_repair = _is_repair_intent(q)
    print(f"  -> Có chứa từ khóa sửa chữa (is_repair_intent)? {is_repair}")
    
    offtopic = is_offtopic(q)
    if offtopic:
        print("  -> Bị chặn bởi Offtopic Guardrail? CÓ")
    else:
        print("  -> Bị chặn bởi Offtopic Guardrail? KHÔNG")
        
    business = deterministic_business_reply(q)
    if business:
        print(f"  -> Bị chặn bởi FAQ Guardrail? CÓ. Trả lời: {business}")
    else:
        print("  -> Bị chặn bởi FAQ Guardrail? KHÔNG (Sẽ được đẩy cho LLM xử lý gọi Tool!)")
