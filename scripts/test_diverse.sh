#!/bin/bash

questions=(
"Cho mình hỏi nếu mình muốn sửa cái tivi bị mất hình thì bên bạn có nhận không?"
"Tôi cần thợ đến ngay bây giờ để sửa đường ống nước bị bể ở Quận 9, khoảng 3 giờ sáng có được không?"
"Bạn là ai và công ty bạn nằm ở quận mấy vậy?"
"Phí di chuyển của thợ là bao nhiêu, và mình có thể trả bằng thẻ tín dụng được không?"
"Tôi muốn biết dịch vụ lắp đặt máy lạnh và sơn lại phòng khách giá bao nhiêu?"
"Bên mình có bảo hành cho dịch vụ sửa chữa điện chập chờn không, và bảo hành bao lâu?"
"Cho mình xin bảng giá tham khảo các dịch vụ sửa chữa bên bạn được không?"
"Tôi bị kẹt cửa ngoài ban công, có thợ nào đến mở khóa gấp giúp tôi không?"
"Can you tell me if you guys work on Sundays and how much is the plumbing service?"
"Dạ alo, nhà mình tự dưng bị cúp điện toàn bộ, gọi thợ mất bao lâu thì tới và có tính thêm tiền đi lại không?"
)

echo "BẮT ĐẦU TEST BỘ CÂU HỎI MỞ RỘNG (Qwen2.5 3B Q5_0):"
echo "======================================================"

for i in "${!questions[@]}"; do
    q="${questions[$i]}"
    echo -e "\n[Câu $((i+1))]: $q"
    
    res=$(curl -s -X POST http://localhost:8081/api/v1/rag/query \
      -H "Content-Type: application/json" \
      -d "{\"query\": \"$q\", \"history\": []}")
    
    ans=$(echo "$res" | jq -r '.response // empty')
    tools=$(echo "$res" | jq -r '.tool_calls[]? // empty' | paste -sd ", ")
    
    if [ -n "$tools" ]; then
        echo "=> (Tools used: $tools)"
    fi

    # fallback to raw if jq fails
    if [ -z "$ans" ]; then
        echo "=> (Raw response): $res"
    else
        echo "=> $ans"
    fi
done
