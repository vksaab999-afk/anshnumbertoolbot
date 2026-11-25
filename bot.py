import os
import logging
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden, RetryAfter, TelegramError
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ChatJoinRequestHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Logging Setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")

if not BOT_TOKEN or not MONGO_URI:
    raise ValueError("Missing critical environment variables: BOT_TOKEN or MONGO_URI")

# Multiple Admins Support
ADMIN_IDS = [5785924075, 6443525890]

# Default Source Chat & Message IDs
DEFAULT_SOURCE_CHAT_ID = 5785924075
DEFAULT_CONFIG = {
    "video_chat_id": DEFAULT_SOURCE_CHAT_ID,
    "video_msg_id": 2832,
    "apk_chat_id": DEFAULT_SOURCE_CHAT_ID,
    "apk_msg_id": 2909,
    "new_post_chat_id": DEFAULT_SOURCE_CHAT_ID,
    "new_post_msg_id": 2838,
    "audio_chat_id": DEFAULT_SOURCE_CHAT_ID,
    "audio_msg_id": 7
}

# Default Button Links
DEFAULT_BUTTON_LINKS = {
    "vip_url": "https://t.me/+TlBymC-xLIVhYTE9",
    "reg_url": "https://maanwin27.com/register?inviteCode=4TFQGGN&from=web",
    "recovery_url": "https://t.me/m/baC_7DarOGY1"
}

# Custom Emoji IDs for Buttons
EMOJI_VIP = "5001508545976337554"
EMOJI_REG = "5271604874419647061"
EMOJI_RECOVERY = "6111716252932119427"
EMOJI_GIFT = "6069089247980165250"
# =======================================================

# --- MONGODB SETUP ---
try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
    db = mongo_client["telegram_bot_db"]
    users_collection = db["users"]
    config_collection = db["bot_config"]
    btn_config_collection = db["btn_config"]
    admin_states = db["admin_states"]
    logger.info("MongoDB Initialized Successfully")
except Exception as e:
    logger.error(f"MongoDB Initial Connection Error: {e}")

def save_user_to_mongo(user_id: int, first_name: str, username: str):
    try:
        users_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "user_id": user_id,
                    "first_name": first_name,
                    "username": username
                }
            },
            upsert=True
        )
    except Exception as e:
        logger.error(f"MongoDB Error saving user {user_id}: {e}")

def get_bot_config():
    try:
        config = config_collection.find_one({"type": "welcome_config"})
        if not config:
            return DEFAULT_CONFIG
        merged = DEFAULT_CONFIG.copy()
        merged.update(config)
        return merged
    except Exception as e:
        logger.error(f"MongoDB Config Fetch Error: {e}")
        return DEFAULT_CONFIG

def get_button_links():
    try:
        config = btn_config_collection.find_one({"type": "btn_config"})
        if not config:
            return DEFAULT_BUTTON_LINKS
        merged = DEFAULT_BUTTON_LINKS.copy()
        merged.update(config)
        return merged
    except Exception as e:
        logger.error(f"MongoDB Button Config Fetch Error: {e}")
        return DEFAULT_BUTTON_LINKS

# --- KEEP-ALIVE WEB SERVER ---
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(bytes("<html><body><h1>Bot is Live!</h1></body></html>", "utf-8"))

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

    def log_message(self, format, *args):
        return

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    try:
        server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
        logger.info(f"Web server bound to port {port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Web Server Error: {e}")

# --- STYLED BUTTON HELPER ---
def styled_button(text, *, style, icon_custom_emoji_id=None, url=None, callback_data=None):
    action = {"url": url} if url else {"callback_data": callback_data or "noop"}
    modern = {"text": text, **action, "style": style}
    if icon_custom_emoji_id:
        modern["icon_custom_emoji_id"] = icon_custom_emoji_id

    try:
        return InlineKeyboardButton(**modern)
    except TypeError:
        api_kwargs = {"style": style}
        if icon_custom_emoji_id:
            api_kwargs["icon_custom_emoji_id"] = icon_custom_emoji_id
        try:
            return InlineKeyboardButton(text=text, api_kwargs=api_kwargs, **action)
        except TypeError:
            return InlineKeyboardButton(text=text, **action)

# --- WELCOME MESSAGES SENDER FUNCTION ---
async def send_welcome_content(context: ContextTypes.DEFAULT_TYPE, user_id: int, first_name: str):
    try:
        cfg = get_bot_config()
        btn_links = get_button_links()

        bot_info = await context.bot.get_me()
        gift_start_link = f"https://t.me/{bot_info.username}?start=claim_gift"

        # 1. Welcome Text
        welcome_text = f"👋🏻 𝐖𝐄𝐋𝐂𝐎𝐌𝐄 {first_name} ❤️‍🔥TO OUR PRIVATE SERVER 🔥\n\n"
        await context.bot.send_message(chat_id=user_id, text=welcome_text)

        # 2. Video Message
        video_keyboard = [
            [styled_button(" VIP CHANNEL", style="primary", icon_custom_emoji_id=EMOJI_VIP, url=btn_links["vip_url"])],
            [styled_button(" REGISTRATION LINK", style="success", icon_custom_emoji_id=EMOJI_REG, url=btn_links["reg_url"])]
        ]
        await context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=cfg.get("video_chat_id", DEFAULT_SOURCE_CHAT_ID),
            message_id=int(cfg.get("video_msg_id", 2832)),
            reply_markup=InlineKeyboardMarkup(video_keyboard)
        )

        # 3. APK File
        await context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=cfg.get("apk_chat_id", DEFAULT_SOURCE_CHAT_ID),
            message_id=int(cfg.get("apk_msg_id", 2909))
        )

        # 4. New Post
        await context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=cfg.get("new_post_chat_id", DEFAULT_SOURCE_CHAT_ID),
            message_id=int(cfg.get("new_post_msg_id", 2838))
        )

        # 5. Audio Message
        audio_keyboard = [
            [styled_button(" DM FOR LOSS RECOVERY", style="danger", icon_custom_emoji_id=EMOJI_RECOVERY, url=btn_links["recovery_url"])],
            [styled_button(" CLAIM GIFT CODE", style="success", icon_custom_emoji_id=EMOJI_GIFT, url=gift_start_link)]
        ]
        await context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=cfg.get("audio_chat_id", DEFAULT_SOURCE_CHAT_ID),
            message_id=int(cfg.get("audio_msg_id", 7)),
            reply_markup=InlineKeyboardMarkup(audio_keyboard)
        )

    except Exception as e:
        logger.error(f"Could not send welcome content to user {user_id}: {e}")

# --- START COMMAND ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user_to_mongo(user.id, user.first_name, user.username)

    if context.args and context.args[0] == "claim_gift":
        reply_text = "Aapka gift code jaldi hi aapko mil jayega tab tak ke liye hack ka use karke profit banao 🔥"
        await update.message.reply_text(reply_text)
    else:
        await send_welcome_content(context, user.id, user.first_name)

# --- JOIN REQUEST HANDLER ---
async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    request = update.chat_join_request
    user = request.from_user
    save_user_to_mongo(user.id, user.first_name, user.username)
    await send_welcome_content(context, user.id, user.first_name)

# --- ADMIN COMMAND: /update ---
async def cmd_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    admin_states.update_one(
        {"admin_id": user_id},
        {"$set": {"mode": "UPDATE_FLOW", "step": "VIDEO", "temp_data": {}}},
        upsert=True
    )
    await update.message.reply_text("⚙️ **Welcome Content Update Mode Started!**\n\n**Step 1:** Naya **Video Message** bhejein ya forward karein:\n\n*(Kahi bhi **done** likhne par itna update save ho jayega)*", parse_mode="Markdown")

# --- ADMIN COMMAND: /updatebutton ---
async def cmd_updatebutton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    links = get_button_links()
    keyboard = [
        [InlineKeyboardButton("1️⃣ VIP Channel Link", callback_data="btn_vip_url")],
        [InlineKeyboardButton("2️⃣ Registration Link", callback_data="btn_reg_url")],
        [InlineKeyboardButton("3️⃣ Loss Recovery Link", callback_data="btn_recovery_url")],
        [InlineKeyboardButton("❌ Cancel", callback_data="btn_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🔘 **Button Link Update Menu**\n\n"
        "Jiss button ka Link/CTA change karna hai us par click karein:\n\n"
        f"• **VIP Channel Link:** `{links['vip_url']}`\n"
        f"• **Registration Link:** `{links['reg_url']}`\n"
        f"• **Recovery Link:** `{links['recovery_url']}`",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# --- CALLBACK QUERY HANDLER FOR BUTTON UPDATE ---
async def handle_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in ADMIN_IDS:
        return

    data = query.data
    if data == "btn_cancel":
        admin_states.delete_one({"admin_id": user_id})
        await query.edit_message_text("❌ Button update cancel kar diya gaya.")
        return

    target_key = data.replace("btn_", "")
    admin_states.update_one(
        {"admin_id": user_id},
        {"$set": {"mode": "UPDATE_BTN_FLOW", "target_key": target_key}},
        upsert=True
    )

    labels = {
        "vip_url": "VIP Channel Link",
        "reg_url": "Registration Link",
        "recovery_url": "Loss Recovery Link"
    }

    await query.edit_message_text(
        f"✏️ **Updating {labels.get(target_key, 'Button Link')}**\n\n"
        "Kripya naya Link (URL) bhejein:\n"
        "*(Link bhejne ke baad chat me **done** likhein)*",
        parse_mode="Markdown"
    )

# --- ADMIN COMMAND: /cancel ---
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    admin_states.delete_one({"admin_id": user_id})
    await update.message.reply_text("❌ Flow cancel kar diya gaya hai.")

# --- SAVE PARTIAL DATA FUNCTION ---
def save_updates_to_db(temp_data):
    current_cfg = get_bot_config()
    update_dict = {"type": "welcome_config"}

    update_dict["video_chat_id"] = temp_data.get("video_chat_id", current_cfg.get("video_chat_id", DEFAULT_SOURCE_CHAT_ID))
    update_dict["video_msg_id"] = temp_data.get("video_msg_id", current_cfg.get("video_msg_id", 2832))

    update_dict["apk_chat_id"] = temp_data.get("apk_chat_id", current_cfg.get("apk_chat_id", DEFAULT_SOURCE_CHAT_ID))
    update_dict["apk_msg_id"] = temp_data.get("apk_msg_id", current_cfg.get("apk_msg_id", 2909))

    update_dict["new_post_chat_id"] = temp_data.get("new_post_chat_id", current_cfg.get("new_post_chat_id", DEFAULT_SOURCE_CHAT_ID))
    update_dict["new_post_msg_id"] = temp_data.get("new_post_msg_id", current_cfg.get("new_post_msg_id", 2838))

    update_dict["audio_chat_id"] = temp_data.get("audio_chat_id", current_cfg.get("audio_chat_id", DEFAULT_SOURCE_CHAT_ID))
    update_dict["audio_msg_id"] = temp_data.get("audio_msg_id", current_cfg.get("audio_msg_id", 7))

    config_collection.update_one(
        {"type": "welcome_config"},
        {"$set": update_dict},
        upsert=True
    )

# --- ADMIN MESSAGE HANDLER ---
async def handle_admin_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    state = admin_states.find_one({"admin_id": user_id})

    # 1. BUTTON UPDATE FLOW
    if state and state.get("mode") == "UPDATE_BTN_FLOW":
        text = msg.text.strip() if msg.text else ""
        target_key = state.get("target_key")

        if text.lower() == "/cancel":
            admin_states.delete_one({"admin_id": user_id})
            await msg.reply_text("❌ Button link update cancel ho gaya.")
            return

        if text.lower() in ["done", "/done"]:
            new_url = state.get("new_url")
            if not new_url:
                await msg.reply_text("⚠️ Aapne koi naya Link bheja hi nahi! Flow cancel kar diya gaya.")
            else:
                btn_config_collection.update_one(
                    {"type": "btn_config"},
                    {"$set": {"type": "btn_config", target_key: new_url}},
                    upsert=True
                )
                await msg.reply_text("🎉 **Buttons Configuration Updated Successfully!**\nAb se naye link ke saath buttons bheje jayenge.")
            admin_states.delete_one({"admin_id": user_id})
            return

        if text.startswith("http://") or text.startswith("https://"):
            admin_states.update_one(
                {"admin_id": user_id},
                {"$set": {"new_url": text}}
            )
            await msg.reply_text(f"✅ Naya Link Received: `{text}`\n\nIs link ko save karne ke liye **done** likhein.", parse_mode="Markdown")
        else:
            await msg.reply_text("⚠️ Kripya valid URL/Link (https://...) bhejein.")
        return

    # 2. MESSAGE UPDATE FLOW
    if state and state.get("mode") == "UPDATE_FLOW":
        text = msg.text.strip() if msg.text else ""
        step = state.get("step")
        temp_data = state.get("temp_data", {})

        if text.lower() == "/cancel":
            admin_states.delete_one({"admin_id": user_id})
            await msg.reply_text("❌ Update cancel ho gaya.")
            return

        if text.lower() in ["done", "/done"]:
            if not temp_data:
                await msg.reply_text("⚠️ Aapne abhi tak koi naya message nahi bheja hai! Update cancel kar diya gaya.")
            else:
                save_updates_to_db(temp_data)
                await msg.reply_text("🎉 **Update Done!**\nAb aap /start karke test kar sakte hain.")
            admin_states.delete_one({"admin_id": user_id})
            return

        chat_id = msg.chat_id
        msg_id = msg.message_id

        if step == "VIDEO":
            temp_data["video_chat_id"] = chat_id
            temp_data["video_msg_id"] = msg_id
            admin_states.update_one(
                {"admin_id": user_id},
                {"$set": {"step": "APK", "temp_data": temp_data}}
            )
            await msg.reply_text("✅ Video Captured!\n\n**Step 2:** Ab **APK File** Message bhejein ya forward karein:\n*(Aap **done** likh kar sirf video update kar sakte hain)*", parse_mode="Markdown")
            return

        elif step == "APK":
            temp_data["apk_chat_id"] = chat_id
            temp_data["apk_msg_id"] = msg_id
            admin_states.update_one(
                {"admin_id": user_id},
                {"$set": {"step": "POST", "temp_data": temp_data}}
            )
            await msg.reply_text("✅ APK File Captured!\n\n**Step 3:** Ab **Nayi Post** Message bhejein ya forward karein:\n*(Bas **done** likh kar save kar sakte hain)*", parse_mode="Markdown")
            return

        elif step == "POST":
            temp_data["new_post_chat_id"] = chat_id
            temp_data["new_post_msg_id"] = msg_id
            admin_states.update_one(
                {"admin_id": user_id},
                {"$set": {"step": "AUDIO", "temp_data": temp_data}}
            )
            await msg.reply_text("✅ Post Captured!\n\n**Step 4:** Ab **Audio Note** Message bhejein ya forward karein:\n*(Bas **done** likh kar save kar sakte hain)*", parse_mode="Markdown")
            return

        elif step == "AUDIO":
            temp_data["audio_chat_id"] = chat_id
            temp_data["audio_msg_id"] = msg_id
            
            save_updates_to_db(temp_data)
            admin_states.delete_one({"admin_id": user_id})
            await msg.reply_text("🎉 **Update Done!**\nSaare messages update ho chuke hain! Ab aap /start karke test kar sakte hain.")
            return

    # Normal Direct Broadcast
    if not (msg.text and msg.text.startswith("/")):
        await execute_broadcast(msg, context, user_id)

# --- BROADCAST LOGIC ---
async def execute_broadcast(message_to_broadcast, context: ContextTypes.DEFAULT_TYPE, admin_chat_id: int):
    users = list(users_collection.find({"user_id": {"$nin": ADMIN_IDS}}, {"user_id": 1}))
    total_users = len(users)

    if total_users == 0:
        await context.bot.send_message(chat_id=admin_chat_id, text="⚠️ Database me aur koi user nahi hai!")
        return

    success_count = 0
    blocked_count = 0

    for u in users:
        u_id = u["user_id"]
        try:
            await context.bot.copy_message(
                chat_id=u_id,
                from_chat_id=message_to_broadcast.chat_id,
                message_id=message_to_broadcast.message_id
            )
            success_count += 1
            await asyncio.sleep(0.05)

        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
            await context.bot.copy_message(
                chat_id=u_id,
                from_chat_id=message_to_broadcast.chat_id,
                message_id=message_to_broadcast.message_id
            )
            success_count += 1
        except Forbidden:
            users_collection.delete_one({"user_id": u_id})
            blocked_count += 1
        except TelegramError as e:
            logger.error(f"Telegram error sending to {u_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending to {u_id}: {e}")

    await context.bot.send_message(
        chat_id=admin_chat_id,
        text=f"✅ **Broadcast Completed!**\n\n"
             f"📊 Delivered: `{success_count}`\n"
             f"🚫 Removed (Blocked/Deleted): `{blocked_count}`",
        parse_mode="Markdown"
    )

# --- COMMAND BASED BROADCAST ---
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if update.effective_user.id not in ADMIN_IDS:
        return

    if msg.reply_to_message:
        await execute_broadcast(msg.reply_to_message, context, update.effective_user.id)
    else:
        text_after_command = msg.text.replace("/broadcast", "").strip()
        if text_after_command:
            users = list(users_collection.find({"user_id": {"$nin": ADMIN_IDS}}, {"user_id": 1}))
            for u in users:
                try:
                    await context.bot.send_message(chat_id=u["user_id"], text=text_after_command)
                    await asyncio.sleep(0.05)
                except Forbidden:
                    users_collection.delete_one({"user_id": u["user_id"]})
                except Exception:
                    pass
            await msg.reply_text("✅ Broadcast Completed!")
        else:
            await msg.reply_text("⚠️ Kripya message ke sath /broadcast likhein ya kisi message par reply karke /broadcast bhejein.")

# --- STATS COMMAND ---
async def st
