import os
import re
import sqlite3
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ChatMemberHandler,
    ContextTypes, filters,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("cuoc-doi-toi-bot")

BOT_TOKEN = os.environ["BOT_TOKEN"]
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
GROUP_ID = os.getenv("GROUP_ID", "").strip()
WELCOME_TEXT = os.getenv(
    "WELCOME_TEXT",
    "🎉 Chào mừng {name} đến với CUỘC ĐỜI TÔI! Vui lòng đọc nội quy nhóm nhé."
)
WELCOME_PHOTO_URL = os.getenv("WELCOME_PHOTO_URL", "").strip()
DB_PATH = os.getenv("DB_PATH", "/var/data/bot.db")
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "Bạn là trợ lý thân thiện của nhóm Telegram CUỘC ĐỜI TÔI. "
    "Trả lời bằng tiếng Việt, ngắn gọn, lịch sự. Không bịa thông tin."
)

URL_RE = re.compile(r"(?i)(https?://|www\\.|t\\.me/|telegram\\.me/|(?:[a-z0-9-]+\\.)+[a-z]{2,}(?:/\\S*)?)")

def db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        event TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS warnings (
        chat_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        count INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(chat_id, user_id)
    )""")
    con.commit()
    return con

def allowed_chat(chat_id: int) -> bool:
    return not GROUP_ID or str(chat_id) == GROUP_ID

def record(chat_id: int, user_id: int, event: str):
    con = db()
    con.execute(
        "INSERT INTO events(chat_id,user_id,event,created_at) VALUES(?,?,?,?)",
        (chat_id, user_id, event, datetime.now(timezone.utc).isoformat()),
    )
    con.commit()
    con.close()

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.effective_chat or not update.effective_user:
        return False
    try:
        member = await context.bot.get_chat_member(
            update.effective_chat.id, update.effective_user.id
        )
        return member.status in ("administrator", "creator")
    except Exception:
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "Xin chào! Tôi là bot quản lý của CUỘC ĐỜI TÔI. Gõ /help để xem lệnh."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "Lệnh sử dụng:\\n"
        "/stats – thống kê nhóm\\n"
        "/ask câu hỏi – hỏi AI\\n"
        "/button Nội dung | https://example.com – tạo nút liên kết (quản trị viên)\\n"
        "/photo URL_ảnh | nội_dung – gửi ảnh (quản trị viên)\\n"
        "/post nội_dung – gửi thông báo (quản trị viên)\\n"
        "/warn – cảnh cáo người được trả lời (quản trị viên)\\n"
        "/mute – khoá chat người được trả lời (quản trị viên)\\n"
        "/unmute – mở khoá chat người được trả lời (quản trị viên)\\n"
        "/ban – cấm người được trả lời (quản trị viên)\\n"
        "/unban user_id – bỏ cấm theo ID (quản trị viên)\\n\\n"
        "AI cũng trả lời khi bạn reply tin nhắn của bot hoặc nhắc @username bot."
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat or chat.type == ChatType.PRIVATE:
        await update.effective_message.reply_text("Lệnh này dùng trong nhóm.")
        return
    if not allowed_chat(chat.id):
        return
    try:
        total = await context.bot.get_chat_member_count(chat.id)
    except Exception:
        total = "không lấy được"
    con = db()
    today = datetime.now(timezone.utc).date().isoformat()
    joined = con.execute(
        "SELECT COUNT(*) FROM events WHERE chat_id=? AND event='join' AND created_at LIKE ?",
        (chat.id, today + "%"),
    ).fetchone()[0]
    left = con.execute(
        "SELECT COUNT(*) FROM events WHERE chat_id=? AND event='leave' AND created_at LIKE ?",
        (chat.id, today + "%"),
    ).fetchone()[0]
    con.close()
    await update.effective_message.reply_text(
        f"📊 THỐNG KÊ NHÓM\\n👥 Tổng thành viên: {total}\\n"
        f"🟢 Tham gia hôm nay (UTC): {joined}\\n🔴 Rời nhóm hôm nay (UTC): {left}"
    )

async def ask_ai(question: str) -> str:
    if not OPENAI_API_KEY:
        return "AI chưa được cấu hình. Quản trị viên cần thêm OPENAI_API_KEY trên máy chủ."
    import json
    import urllib.request
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question[:6000]},
        ],
        "temperature": 0.5,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            data = json.loads(response.read().decode())
        return data["choices"][0]["message"]["content"].strip()[:4000]
    except Exception as exc:
        log.exception("AI request failed")
        return f"AI đang gặp lỗi khi trả lời. Vui lòng thử lại sau. ({type(exc).__name__})"

async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = " ".join(context.args).strip()
    if not question:
        await update.effective_message.reply_text("Cách dùng: /ask nội dung cần hỏi")
        return
    answer = await ask_ai(question)
    await update.effective_message.reply_text(answer)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat or not user or chat.type == ChatType.PRIVATE:
        return
    if not allowed_chat(chat.id):
        return

    # Không áp dụng lọc link lên quản trị viên.
    admin = await is_admin(update, context)
    entities = (msg.entities or []) + (msg.caption_entities or [])
    has_link_entity = any(str(e.type) in ("url", "text_link") for e in entities)
    text_to_check = msg.text or msg.caption or ""
    has_link = has_link_entity or bool(URL_RE.search(text_to_check))
    if has_link and not admin:
        try:
            await msg.delete()
            await context.bot.send_message(
                chat.id, f"⚠️ {user.first_name}, nhóm không cho phép gửi link quảng cáo."
            )
        except Exception:
            log.exception("Could not delete link message")
        return

    # AI chỉ phản hồi khi gọi /ask, reply bot hoặc nhắc tên bot.
    me = await context.bot.get_me()
    is_reply_to_bot = bool(msg.reply_to_message and msg.reply_to_message.from_user
                           and msg.reply_to_message.from_user.id == me.id)
    mentioned = bool(msg.text and me.username and f"@{me.username.lower()}" in msg.text.lower())
    if is_reply_to_bot or mentioned:
        question = msg.text or msg.caption or ""
        if me.username:
            question = re.sub(rf"@{re.escape(me.username)}", "", question, flags=re.I).strip()
        if question:
            await msg.reply_text(await ask_ai(question))

async def member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    if not result or not allowed_chat(result.chat.id):
        return
    old = result.old_chat_member.status
    new = result.new_chat_member.status
    user = result.new_chat_member.user
    was_member = old in ("member", "administrator", "creator", "restricted")
    is_member = new in ("member", "administrator", "creator", "restricted")
    if not was_member and is_member:
        record(result.chat.id, user.id, "join")
        if user.id != context.bot.id:
            text = WELCOME_TEXT.replace("{name}", user.first_name)
            if WELCOME_PHOTO_URL:
                try:
                    await context.bot.send_photo(result.chat.id, WELCOME_PHOTO_URL, caption=text)
                except Exception:
                    await context.bot.send_message(result.chat.id, text)
            else:
                await context.bot.send_message(result.chat.id, text)
    elif was_member and not is_member:
        record(result.chat.id, user.id, "leave")

def replied_user(update: Update):
    msg = update.effective_message
    return msg.reply_to_message.from_user if msg and msg.reply_to_message else None

async def admin_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not await is_admin(update, context):
        await update.effective_message.reply_text("Lệnh này chỉ dành cho quản trị viên.")
        return False
    if not allowed_chat(update.effective_chat.id):
        await update.effective_message.reply_text("Bot chưa được cấu hình cho nhóm này.")
        return False
    return True

async def post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_guard(update, context): return
    content = " ".join(context.args).strip()
    if not content:
        await update.effective_message.reply_text("Cách dùng: /post nội dung thông báo")
        return
    await context.bot.send_message(update.effective_chat.id, content[:4000])

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_guard(update, context): return
    raw = " ".join(context.args)
    parts = [p.strip() for p in raw.split("|", 1)]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        await update.effective_message.reply_text("Cách dùng: /button Nội dung nút | https://example.com")
        return
    url = parts[1]
    if urlparse(url).scheme not in ("http", "https") or not urlparse(url).netloc:
        await update.effective_message.reply_text("Link phải bắt đầu bằng https:// hoặc http://")
        return
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(parts[0][:64], url=url)]])
    await context.bot.send_message(update.effective_chat.id, "👇 Nhấn nút bên dưới:", reply_markup=keyboard)

async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_guard(update, context): return
    raw = " ".join(context.args)
    parts = [p.strip() for p in raw.split("|", 1)]
    if len(parts) != 2 or not parts[0].startswith(("https://", "http://")):
        await update.effective_message.reply_text("Cách dùng: /photo https://link-anh.jpg | Nội dung ảnh")
        return
    await context.bot.send_photo(update.effective_chat.id, parts[0], caption=parts[1][:1000])

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_guard(update, context): return
    target = replied_user(update)
    if not target:
        await update.effective_message.reply_text("Hãy reply tin nhắn thành viên rồi gửi /warn.")
        return
    con = db()
    con.execute("INSERT INTO warnings(chat_id,user_id,count) VALUES(?,?,1) "
                "ON CONFLICT(chat_id,user_id) DO UPDATE SET count=count+1",
                (update.effective_chat.id, target.id))
    count = con.execute("SELECT count FROM warnings WHERE chat_id=? AND user_id=?",
                        (update.effective_chat.id, target.id)).fetchone()[0]
    con.commit(); con.close()
    await update.effective_message.reply_text(f"⚠️ Đã cảnh cáo {target.first_name}. Tổng cảnh cáo: {count}")

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_guard(update, context): return
    target = replied_user(update)
    if not target:
        await update.effective_message.reply_text("Hãy reply tin nhắn thành viên rồi gửi /mute.")
        return
    from telegram import ChatPermissions
    await context.bot.restrict_chat_member(update.effective_chat.id, target.id,
        ChatPermissions(can_send_messages=False))
    await update.effective_message.reply_text(f"Đã mute {target.first_name}.")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_guard(update, context): return
    target = replied_user(update)
    if not target:
        await update.effective_message.reply_text("Hãy reply tin nhắn thành viên rồi gửi /unmute.")
        return
    from telegram import ChatPermissions
    await context.bot.restrict_chat_member(update.effective_chat.id, target.id,
        ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_documents=True,
                        can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
                        can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
                        can_add_web_page_previews=True))
    await update.effective_message.reply_text(f"Đã unmute {target.first_name}.")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_guard(update, context): return
    target = replied_user(update)
    if not target:
        await update.effective_message.reply_text("Hãy reply tin nhắn thành viên rồi gửi /ban.")
        return
    await context.bot.ban_chat_member(update.effective_chat.id, target.id)
    await update.effective_message.reply_text(f"Đã ban {target.first_name}.")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_guard(update, context): return
    if not context.args or not context.args[0].lstrip("-").isdigit():
        await update.effective_message.reply_text("Cách dùng: /unban user_id")
        return
    await context.bot.unban_chat_member(update.effective_chat.id, int(context.args[0]), only_if_banned=True)
    await update.effective_message.reply_text("Đã bỏ cấm nếu tài khoản này đang bị ban.")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("ask", ai_command))
    app.add_handler(CommandHandler("post", post))
    app.add_handler(CommandHandler("button", button))
    app.add_handler(CommandHandler("photo", photo))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(ChatMemberHandler(member_update, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    log.info("Bot is starting")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
