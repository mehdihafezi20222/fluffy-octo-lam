import os
import io
import random
import logging
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")

# --- تنظیمات صفحه بازی ---
LADDERS = {1: 38, 4: 14, 9: 31, 21: 42, 28: 84, 36: 44, 51: 67, 71: 91, 80: 100}
SNAKES = {16: 6, 47: 26, 49: 11, 56: 53, 62: 19, 64: 60, 87: 24, 93: 73, 95: 75, 98: 78}
BOARD_SIZE = 100

PLAYER_COLORS = [
    (230, 57, 70), (29, 53, 87), (42, 157, 143),
    (244, 162, 97), (138, 96, 168), (0, 150, 136),
]

# --- تنظیمات تصویر ---
CELL = 56
MARGIN = 24
BOARD_PX = CELL * 10
IMG_SIZE = BOARD_PX + MARGIN * 2

# state هر بازی به ازای chat_id
games = {}


def get_game(chat_id):
    return games.get(chat_id)


def cell_to_xy(n):
    n0 = n - 1
    row = n0 // 10
    col = n0 % 10
    if row % 2 == 1:
        col = 9 - col
    x = MARGIN + col * CELL + CELL // 2
    y = MARGIN + (9 - row) * CELL + CELL // 2
    return x, y


def render_board(game):
    img = Image.new("RGB", (IMG_SIZE, IMG_SIZE), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
    except Exception:
        font = ImageFont.load_default()
        font_small = font

    for n in range(1, 101):
        x, y = cell_to_xy(n)
        row = (n - 1) // 10
        color = (255, 250, 235) if row % 2 == 0 else (232, 244, 255)
        draw.rectangle(
            [x - CELL // 2, y - CELL // 2, x + CELL // 2, y + CELL // 2],
            fill=color, outline=(190, 190, 190)
        )
        draw.text((x - CELL // 2 + 4, y - CELL // 2 + 3), str(n), fill=(130, 130, 130), font=font_small)

    for a, b in LADDERS.items():
        x1, y1 = cell_to_xy(a)
        x2, y2 = cell_to_xy(b)
        draw.line([x1, y1, x2, y2], fill=(46, 125, 50), width=5)
        draw.ellipse([x1 - 5, y1 - 5, x1 + 5, y1 + 5], fill=(46, 125, 50))
        draw.ellipse([x2 - 5, y2 - 5, x2 + 5, y2 + 5], fill=(46, 125, 50))

    for a, b in SNAKES.items():
        x1, y1 = cell_to_xy(a)
        x2, y2 = cell_to_xy(b)
        draw.line([x1, y1, x2, y2], fill=(198, 40, 40), width=5)
        draw.ellipse([x1 - 6, y1 - 6, x1 + 6, y1 + 6], fill=(198, 40, 40))
        draw.ellipse([x2 - 4, y2 - 4, x2 + 4, y2 + 4], fill=(198, 40, 40))

    offsets = [(-11, -11), (11, -11), (-11, 11), (11, 11), (0, 0), (0, -16)]
    for idx, uid in enumerate(game["order"]):
        p = game["players"][uid]
        pos = max(p["pos"], 1)
        x, y = cell_to_xy(pos)
        ox, oy = offsets[idx % len(offsets)]
        color = PLAYER_COLORS[idx % len(PLAYER_COLORS)]
        draw.ellipse([x + ox - 10, y + oy - 10, x + ox + 10, y + oy + 10], fill=color, outline=(0, 0, 0), width=2)
        initial = (p["name"][0].upper() if p["name"] else "?")
        draw.text((x + ox - 4, y + oy - 7), initial, fill="white", font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def build_keyboard(chat_id):
    game = get_game(chat_id)
    if not game:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🎮 بازی جدید", callback_data="newgame")]])
    if not game["started"]:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ ورود به بازی", callback_data="join")],
            [InlineKeyboardButton("▶️ شروع بازی", callback_data="startgame")],
        ])
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎲 پرتاب تاس", callback_data="roll"),
            InlineKeyboardButton("📊 وضعیت", callback_data="board"),
        ],
        [InlineKeyboardButton("🏳️ پایان بازی", callback_data="endgame")],
    ])


def player_line(pos):
    return f"خونه {pos}"


# ---------- منطق اصلی بازی (مستقل از نوع پیام) ----------

def do_newgame(chat_id, chat_type, user):
    if chat_id in games and games[chat_id]["started"]:
        return "یه بازی هنوز در حال انجامه! اول پایان بده.", False

    if chat_type == "private":
        games[chat_id] = {
            "players": {user.id: {"name": user.first_name, "pos": 0}},
            "order": [user.id],
            "turn": 0,
            "started": True,
            "mode": "private",
        }
        return f"بازی شروع شد {user.first_name}! تاس بنداز 🎲", True

    games[chat_id] = {
        "players": {},
        "order": [],
        "turn": 0,
        "started": False,
        "mode": "group",
    }
    return "بازی جدید ساخته شد! بازیکن‌ها با دکمه پایین وارد بشن، بعد شروع کنید.", False


def do_join(chat_id, user):
    game = get_game(chat_id)
    if not game:
        return "هنوز بازی‌ای ساخته نشده."
    if game["started"]:
        return "بازی از قبل شروع شده."
    if user.id in game["players"]:
        return "قبلاً join کردی!"
    game["players"][user.id] = {"name": user.first_name, "pos": 0}
    game["order"].append(user.id)
    return f"{user.first_name} به بازی پیوست ✅ (تعداد: {len(game['order'])})"


def do_startgame(chat_id):
    game = get_game(chat_id)
    if not game:
        return "هنوز بازی‌ای ساخته نشده."
    if game["started"]:
        return "بازی از قبل شروع شده."
    if len(game["order"]) < 2:
        return "حداقل ۲ نفر باید join کرده باشن."
    game["started"] = True
    first_name = game["players"][game["order"][0]]["name"]
    return f"بازی شروع شد! نوبت اول با {first_name} 🎲"


def do_roll(chat_id, user):
    """برمی‌گردونه: (متن, ارسال_عکس؟, پایان_بازی؟)"""
    game = get_game(chat_id)
    if not game or not game["started"]:
        return "بازی‌ای در حال انجام نیست.", False, False

    current_player_id = game["order"][game["turn"]]
    if game["mode"] == "group" and user.id != current_player_id:
        current_name = game["players"][current_player_id]["name"]
        return f"الان نوبت {current_name} هست، صبر کن!", False, False

    if user.id not in game["players"]:
        return "تو توی این بازی نیستی!", False, False

    dice = random.randint(1, 6)
    player = game["players"][user.id]
    new_pos = player["pos"] + dice
    msg = f"🎲 {player['name']} تاس انداخت: {dice}\n"

    if new_pos > BOARD_SIZE:
        msg += f"برای رسیدن به خونه ۱۰۰ باید عدد دقیق بیاری. هنوز توی {player_line(player['pos'])} هستی."
        if game["mode"] == "group":
            game["turn"] = (game["turn"] + 1) % len(game["order"])
        return msg, True, False

    player["pos"] = new_pos
    msg += f"رفت به {player_line(new_pos)}"

    if new_pos in LADDERS:
        player["pos"] = LADDERS[new_pos]
        msg += f"\n🪜 نردبان! رفت بالا به {player_line(player['pos'])}"
    elif new_pos in SNAKES:
        player["pos"] = SNAKES[new_pos]
        msg += f"\n🐍 مار! افتاد پایین به {player_line(player['pos'])}"

    if player["pos"] == BOARD_SIZE:
        msg += f"\n\n🏆 {player['name']} برنده شد! تبریک!"
        games.pop(chat_id, None)
        return msg, True, True

    if game["mode"] == "group":
        game["turn"] = (game["turn"] + 1) % len(game["order"])
        next_name = game["players"][game["order"][game["turn"]]]["name"]
        msg += f"\n\nنوبت بعدی: {next_name}"

    return msg, True, False


def get_board_text(chat_id):
    game = get_game(chat_id)
    if not game or not game["players"]:
        return "بازی‌ای در حال انجام نیست."
    lines = ["📊 وضعیت فعلی بازی:"]
    for uid in game["order"]:
        p = game["players"][uid]
        lines.append(f"- {p['name']}: {player_line(p['pos'])}")
    return "\n".join(lines)


# ---------- هندلرهای دستورات متنی ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🐍🎲 به ربات بازی مار و پله خوش اومدی!\n"
        "با دکمه زیر بازی جدید بساز، یا از دستورات /newgame /join /startgame /roll /board /endgame استفاده کن.",
        reply_markup=build_keyboard(update.effective_chat.id),
    )


async def newgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    msg, _ = do_newgame(chat_id, update.effective_chat.type, update.effective_user)
    await update.message.reply_text(msg, reply_markup=build_keyboard(chat_id))


async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    msg = do_join(chat_id, update.effective_user)
    await update.message.reply_text(msg, reply_markup=build_keyboard(chat_id))


async def startgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    msg = do_startgame(chat_id)
    await update.message.reply_text(msg, reply_markup=build_keyboard(chat_id))


async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    msg, send_img, _ = do_roll(chat_id, update.effective_user)
    game = get_game(chat_id)
    if send_img and game:
        await update.message.reply_photo(photo=render_board(game), caption=msg, reply_markup=build_keyboard(chat_id))
    else:
        await update.message.reply_text(msg, reply_markup=build_keyboard(chat_id))


async def board(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = get_game(chat_id)
    text = get_board_text(chat_id)
    if game:
        await update.message.reply_photo(photo=render_board(game), caption=text, reply_markup=build_keyboard(chat_id))
    else:
        await update.message.reply_text(text, reply_markup=build_keyboard(chat_id))


async def endgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in games:
        games.pop(chat_id)
        await update.message.reply_text("بازی پایان یافت.", reply_markup=build_keyboard(chat_id))
    else:
        await update.message.reply_text("بازی‌ای در حال انجام نبود.")


# ---------- هندلر دکمه‌های تعاملی ----------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    chat_type = query.message.chat.type
    user = update.effective_user
    data = query.data

    if data == "newgame":
        msg, _ = do_newgame(chat_id, chat_type, user)
        await query.message.reply_text(msg, reply_markup=build_keyboard(chat_id))

    elif data == "join":
        msg = do_join(chat_id, user)
        await query.message.reply_text(msg, reply_markup=build_keyboard(chat_id))

    elif data == "startgame":
        msg = do_startgame(chat_id)
        await query.message.reply_text(msg, reply_markup=build_keyboard(chat_id))

    elif data == "roll":
        msg, send_img, _ = do_roll(chat_id, user)
        game = get_game(chat_id)
        if send_img and game:
            await query.message.reply_photo(photo=render_board(game), caption=msg, reply_markup=build_keyboard(chat_id))
        else:
            await query.message.reply_text(msg, reply_markup=build_keyboard(chat_id))

    elif data == "board":
        game = get_game(chat_id)
        text = get_board_text(chat_id)
        if game:
            await query.message.reply_photo(photo=render_board(game), caption=text, reply_markup=build_keyboard(chat_id))
        else:
            await query.message.reply_text(text, reply_markup=build_keyboard(chat_id))

    elif data == "endgame":
        if chat_id in games:
            games.pop(chat_id)
            await query.message.reply_text("بازی پایان یافت.", reply_markup=build_keyboard(chat_id))
        else:
            await query.message.reply_text("بازی‌ای در حال انجام نبود.")


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN تنظیم نشده! متغیر محیطی BOT_TOKEN رو ست کن.")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("newgame", newgame))
    application.add_handler(CommandHandler("join", join))
    application.add_handler(CommandHandler("startgame", startgame))
    application.add_handler(CommandHandler("roll", roll))
    application.add_handler(CommandHandler("board", board))
    application.add_handler(CommandHandler("endgame", endgame))
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("ربات در حال اجراست...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
