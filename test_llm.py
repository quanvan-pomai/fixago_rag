import requests

URL = "http://127.0.0.1:8080/v1/chat/completions"

messages = [
    {"role": "system", "content": """Bạn là nhân viên CSKH của Fixago.
QUY TRÌNH ĐẶT LỊCH:
1. Khi khách CÓ Ý ĐỊNH đặt lịch, TUYỆT ĐỐI CHƯA TẠO ĐƠN NGAY. Bạn phải hỏi đầy đủ 3 thông tin: Tên, SĐT, và Địa chỉ.
2. Sau khi khách cung cấp đủ thông tin, bạn phải TỔNG HỢP LẠI (Tên, SĐT, Địa chỉ, Lỗi) và hỏi khách có CHẮC CHẮN xác nhận đặt thợ không.
3. CHỈ KHI khách trả lời 'Có', 'Đồng ý', 'Xác nhận' sau bảng tổng hợp, bạn mới ĐƯỢC PHÉP trả về dòng: CALL_TOOL: create_booking(name="tên", phone="sdt", address="địa chỉ", description="lỗi")
LƯU Ý: Không được giải thích gì thêm khi gọi Tool."""},
    {"role": "user", "content": "Nhà tôi bị chập điện, đặt lịch thợ tới sửa giúp tôi"},
    {"role": "assistant", "content": "Dạ vâng, để em đặt lịch cho anh/chị. Xin vui lòng cung cấp Tên, Số điện thoại và Địa chỉ ạ."},
    {"role": "user", "content": "Tôi tên Toàn, sđt 0987654321, nhà ở 123 Lê Lợi"},
    {"role": "assistant", "content": "Dạ em xác nhận anh Toàn, SĐT 0987654321, Địa chỉ 123 Lê Lợi. Lỗi chập điện. Anh xác nhận tạo đơn chứ ạ?"},
    {"role": "user", "content": "Xác nhận tạo đơn đi bạn"}
]

resp = requests.post(URL, json={"messages": messages, "temperature": 0.1})
print(resp.json()["choices"][0]["message"]["content"])
