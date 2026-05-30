#!/bin/bash

questions=(
"em hỏi máy lạnh nhà em chảy nước"
"công ty em có thể cung cấp dịch vụ gì"
"chi phí cụ thể các dịch vụ thể nào"
"công ty của em ở đâu"
"thời gian đáp ứng và cách đặt lịch ra sao"
"làm sao biết đúng thợ sẽ đến"
"chi phí này bao gồm chi phí di chuyển chưa"
"anh muốn sửa chữa phòng bếp nhà anh"
"anh muốn thay bóng đèn trên trần nhà"
"anh muốn lắp đặt máy lạnh mới mua"
"anh muốn thay thế ống nước vừa bị bể gấp"
"bên em có hỗ trợ thay khóa cửa không"
"thanh toán bằng cách nào"
"can you introduce about your company and services"
"how long for you to confirm"
"how about the pricing"
)

echo "BẮT ĐẦU TEST BỘ CÂU HỎI CỦA SẾP (Qwen2.5 3B Q5_0):"
echo "======================================================"

for i in "${!questions[@]}"; do
    q="${questions[$i]}"
    echo -e "\n[Câu $((i+1))]: $q"
    
    res=$(curl -s -X POST http://localhost:8081/api/v1/rag/query \
      -H "Content-Type: application/json" \
      -d "{\"query\": \"$q\", \"history\": []}")
    
    ans=$(echo "$res" | jq -r '.response // empty')
    
    # fallback to raw if jq fails
    if [ -z "$ans" ]; then
        echo "=> (Raw response): $res"
    else
        echo "=> $ans"
    fi
done
