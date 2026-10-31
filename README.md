# CUỘC ĐỜI TÔI Telegram Bot

## Tính năng
- Xóa tin nhắn có URL của thành viên thường; bỏ qua quản trị viên.
- AI trả lời qua `/ask`, khi reply tin nhắn của bot hoặc nhắc @username bot.
- Thống kê tổng thành viên và lượt tham gia/rời nhóm ghi nhận từ lúc bot chạy.
- `/button Nội dung nút | https://example.com`
- `/photo https://example.com/image.jpg | Nội dung ảnh`
- `/post nội dung`
- `/warn`, `/mute`, `/unmute`, `/ban`, `/unban user_id` (lệnh quản trị).

## Triển khai bằng Render
1. Tải ZIP, giải nén trên iPhone (ứng dụng Tệp).
2. Tạo repository mới trên GitHub, tải lên `bot.py`, `requirements.txt`, `render.yaml`.
3. Trong Telegram mở @BotFather, gửi `/setprivacy`, chọn bot, chọn `Disable`.
4. Lấy Group ID bằng cách tạm thời thêm `@RawDataBot` vào nhóm hoặc dùng bot lấy ID đáng tin cậy; gỡ bot phụ sau đó. Group ID thường là số âm bắt đầu `-100`.
5. Tạo tài khoản Render, chọn New + > Blueprint, kết nối GitHub repo và deploy.
6. Trong Render > service > Environment, nhập:
   - `BOT_TOKEN`: token từ BotFather
   - `OPENAI_API_KEY`: API key từ OpenAI Platform (để trống nếu chưa bật AI)
   - `GROUP_ID`: ID nhóm, ví dụ `-1001234567890`
   - `WELCOME_PHOTO_URL`: URL ảnh công khai (không bắt buộc)
7. Deploy/redeploy. Dùng Logs để kiểm tra `Bot is starting`.

## Lưu ý
- Render Background Worker gói trả phí và Persistent Disk có thể phát sinh phí. Kiểm tra giá trước khi xác nhận.
- Bot cần quyền xóa tin nhắn, hạn chế thành viên, cấm thành viên và mời người dùng phù hợp với lệnh bạn muốn dùng.
- Tắt Privacy Mode để bot đọc tin nhắn thường trong nhóm. Bot vẫn nhận lệnh bắt đầu bằng `/` khi privacy bật, nhưng không thể tự lọc mọi link.
- Không chia sẻ BOT_TOKEN hoặc OPENAI_API_KEY. Nếu lộ, vào @BotFather dùng `/revoke` để đổi token.
- Thống kê lịch sử chỉ bắt đầu từ lúc bot chạy; lượt join/leave được Telegram gửi đến khi bot là admin.
- SQLite được lưu trên disk `/var/data` để tránh mất dữ liệu khi deploy lại.
- Chức năng lọc URL không thể đảm bảo phát hiện mọi kiểu link bị làm biến dạng; nên kiểm tra trong nhóm thử nghiệm trước.
