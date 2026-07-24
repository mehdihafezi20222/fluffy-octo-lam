import os
import io
import random
import logging
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
ADMIN_IDS = set(map(int, os.environ.get("ADMIN_IDS", "").split(","))) if os.environ.get("ADMIN_IDS") else set()

# --- تنظیمات صفحه بازی ---
LADDERS = {1: 38, 4: 14, 9: 31, 21: 42, 28: 84, 36: 44, 51: 67, 71: 91, 80: 100}
SNAKES = {16: 6, 47: 26, 49: 11, 56: 53, 62: 19, 64: 60, 87: 24, 93: 73, 95: 75, 98: 78}
BOARD_SIZE = 100

PLAYER_COLORS = [
    (230, 57, 70), (29, 53, 87), (42, 157, 143),
    (244, 162, 97), (138, 96, 168), (0, 150, 136),
    (255, 193, 7), (233, 30, 99),
]

# --- تنظیمات تصویر ---
CELL = 56
MARGIN = 24
BOARD_PX = CELL * 10
IMG_SIZE = BOARD_PX + MARGIN * 2

games = {}
leaderboard = {}
player_stats = {}

# =====================================================
# 📦 توابع کمکی
# =====================================================

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

def player_line(pos):
    return f"خونه {pos}"

def is_admin(user_id):
    return user_id in ADMIN_IDS

# =====================================================
# 🎨 رندر تخته
# =====================================================

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

    offsets = [
        (-14, -14), (14, -14), (-14, 14), (14, 14),
        (0, -20), (0, 20), (-20, 0), (20, 0)
    ]
    for idx, uid in enumerate(game["order"]):
        p = game["players"][uid]
        pos = max(p["pos"], 1)
        x, y = cell_to_xy(pos)
        ox, oy = offsets[idx % len(offsets)]
        color = PLAYER_COLORS[idx % len(PLAYER_COLORS)]
        draw.ellipse([x + ox - 10, y + oy - 10, x + ox + 10, y + oy + 10], fill=color, outline=(0, 0, 0), width=2)
        
        # علامت جریمه
        if "penalty" in game and uid in game["penalty"]:
            draw.ellipse([x + ox - 14, y + oy - 14, x + ox + 14, y + oy + 14], outline=(255, 0, 0), width=3)
        
        initial = (p["name"][0].upper() if p["name"] else "?")
        draw.text((x + ox - 4, y + oy - 7), initial, fill="white", font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# =====================================================
# ⌨️ کیبورد
# =====================================================

def build_keyboard(chat_id, user_id=None):
    game = get_game(chat_id)
    
    # منوی اصلی
    if not game:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🎮 بازی جدید", callback_data="newgame")],
            [InlineKeyboardButton("🏆 جدول امتیازات", callback_data="leaderboard")]
        ])
    
    if not game["started"]:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ ورود به بازی", callback_data="join")],
            [InlineKeyboardButton("▶️ شروع بازی", callback_data="startgame")],
        ])
    
    # دکمه‌های اصلی
    buttons = [
        [InlineKeyboardButton("🎲 پرتاب تاس", callback_data="roll")],
        [InlineKeyboardButton("📊 وضعیت", callback_data="board")],
        [InlineKeyboardButton("↩️ برگشت", callback_data="undo")],
    ]
    
    # دکمه‌های مدیریت (فقط ادمین)
    if user_id and is_admin(user_id):
        buttons.append([
            InlineKeyboardButton("🔨 جریمه", callback_data="penalty_menu"),
            InlineKeyboardButton("⚡ پاک‌سازی", callback_data="reset_all"),
        ])
    
    buttons.append([InlineKeyboardButton("🏳️ پایان", callback_data="endgame")])
    
    return InlineKeyboardMarkup(buttons)

# =====================================================
# 📊 جدول امتیازات
# =====================================================

def add_win(user_id, user_name, chat_id):
    if user_id not in leaderboard:
        leaderboard[user_id] = {"name": user_name, "wins": 0, "last_win": None}
    leaderboard[user_id]["wins"] += 1
    leaderboard[user_id]["last_win"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    if user_id not in player_stats:
        player_stats[user_id] = {"total_games": 0, "wins": 0}
    player_stats[user_id]["wins"] += 1
    player_stats[user_id]["total_games"] += 1

def get_leaderboard_text():
    if not leaderboard:
        return "🏆 هنوز برد‌ای ثبت نشده!"
    
    sorted_players = sorted(leaderboard.items(), key=lambda x: x[1]["wins"], reverse=True)
    lines = ["🏆 جدول امتیازات (Top 10):"]
    for i, (uid, data) in enumerate(sorted_players[:10], 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🎖️"
        lines.append(f"{medal} {i}. {data['name']}: {data['wins']} برد")
    
    return "\n".join(lines)

# =====================================================
# 💾 تاریخچه (Undo)
# =====================================================

def save_game_state(game):
    if "history" not in game:
        game["history"] = []
    
    state = {
        "players": {uid: p.copy() for uid, p in game["players"].items()},
        "turn": game["turn"],
        "penalty": game.get("penalty", {}).copy(),
        "timestamp": datetime.now()
    }
    game["history"].append(state)
    
    if len(game["history"]) > 10:
        game["history"].pop(0)

def undo_last_move(chat_id):
    game = get_game(chat_id)
    if not game or not game["started"]:
        return "بازی‌ای در حال انجام نیست.", False
    
    if "history" not in game or len(game["history"]) == 0:
        return "هیچ حرکتی برای برگشت نیست!", False
    
    last_state = game["history"].pop()
    game["players"] = last_state["players"]
    game["turn"] = last_state["turn"]
    game["penalty"] = last_state.get("penalty", {})
    
    return "✅ آخرین حرکت برگشت زده شد!", True

# =====================================================
# 🚨 سیستم جریمه (ممنوعه)
# =====================================================

def penalize_player(chat_id, user_id, reason="تخلف"):
    game = get_game(chat_id)
    if not game or not game["started"]:
        return "بازی فعال نیست.", False
    
    if user_id not in game["players"]:
        return "این بازیکن تو بازی نیست.", False
    
    if "penalty" not in game:
        game["penalty"] = {}
    
    game["penalty"][user_id] = {
        "reason": reason,
        "turns": 3,
        "applied": False
    }
    
    # اگه الان نوبت اینه، رد کن
    if game["order"][game["turn"]] == user_id:
        game["turn"] = (game["turn"] + 1) % len(game["order"])
    
    return f"⚠️ {game['players'][user_id]['name']} جریمه شد! دلیل: {reason}", True

def unpenalize_player(chat_id, user_id):
    game = get_game(chat_id)
    if not game:
        return "بازی فعال نیست.", False
    
    if "penalty" not in game or user_id not in game["penalty"]:
        return "این بازیکن جریمه نیست.", False
    
    del game["penalty"][user_id]
    return f"✅ جریمه {game['players'][user_id]['name']} بخشیده شد.", True

def reset_player_position(chat_id, user_id):
    game = get_game(chat_id)
    if not game or not game["started"]:
        return "بازی فعال نیست.", False
    
    if user_id not in game["players"]:
        return "این بازیکن تو بازی نیست.", False
    
    game["players"][user_id]["pos"] = 0
    # پاک کردن جریمه
    if "penalty" in game and user_id in game["penalty"]:
        del game["penalty"][user_id]
    
    return f"🔄 {game['players'][user_id]['name']} به شروع بازی برگشت.", True

# =====================================================
# 🎲 منطق اصلی بازی
# =====================================================

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
            "history": [],
            "penalty": {},
        }
        return f"بازی شروع شد {user.first_name}! تاس بنداز 🎲", True

    games[chat_id] = {
        "players": {},
        "order": [],
        "turn": 0,
        "started": False,
        "mode": "group",
        "history": [],
        "penalty": {},
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
    game = get_game(chat_id)
    if not game or not game["started"]:
        return "بازی‌ای در حال انجام نیست.", False, False

    current_player_id = game["order"][game["turn"]]
    if game["mode"] == "group" and user.id != current_player_id:
        current_name = game["players"][current_player_id]["name"]
        return f"الان نوبت {current_name} هست، صبر کن!", False, False

    if user.id not in game["players"]:
        return "تو توی این بازی نیستی!", False, False

    # 🚨 چک جریمه
    if "penalty" in game and user.id in game["penalty"]:
        penalty = game["penalty"][user.id]
        if penalty["turns"] > 0:
            penalty["turns"] -= 1
            if penalty["turns"] == 0:
                del game["penalty"][user.id]
                msg = f"✅ جریمه {game['players'][user.id]['name']} تموم شد."
            else:
                msg = f"⛔ {game['players'][user.id]['name']} هنوز {penalty['turns']} نوبت جریمه داره."
            game["turn"] = (game["turn"] + 1) % len(game["order"])
            return msg, True, False

    # 💾 ذخیره وضعیت برای undo
    save_game_state(game)

    dice = random.randint(1, 6)
    player = game["players"][user.id]
    new_pos = player["pos"] + dice
    msg = f"🎲 {player['name']} تاس انداخت: {dice}\n"

    if new_pos > BOARD_SIZE:
        msg += f"برای رسیدن به خونه ۱۰۰ باید عدد دقیق بیاری. هنوز توی {player_line(player['pos'])} هستی."
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
        add_win(user.id, player['name'], chat_id)
        games.pop(chat_id, None)
        return msg, True, True

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
        status = ""
        if "penalty" in game and uid in game["penalty"]:
            status = f" ⛔ ({game['penalty'][uid]['turns']} نوبت جریمه)"
        lines.append(f"- {p['name']}: {player_line(p['pos'])}{status}")
    return "\n".join(lines)

def get_penalty_menu_text(chat_id):
    game = get_game(chat_id)
    if not game or not game["started"]:
        return "بازی فعال نیست."
    
    lines = ["🔨 منوی جریمه:"]
    for i, uid in enumerate(game["order"]):
        p = game["players"][uid]
        status = "⛔ جریمه" if "penalty" in game and uid in game["penalty"] else "✅ سالم"
        lines.append(f"{i+1}. {p['name']} — {status}")
    
    lines.append("\nعدد بازیکن رو انتخاب کن (مثلاً /penalty 2)")
    return "\n".join(lines)

# =====================================================
# 📱 هندلرهای دستورات
# =====================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        "🐍🎲 به ربات مار و پله خوش اومدی!\n\n"
        "📋 دستورات:\n"
        "/newgame - بازی جدید\n"
        "/join - ورود به بازی\n"
        "/startgame - شروع بازی\n"
        "/roll - پرتاب تاس\n"
        "/board - دیدن وضعیت\n"
        "/undo - برگشت به حرکت قبلی\n"
        "/leaderboard - جدول امتیازات\n"
        "/stats - آمار شخصی شما\n"
        "/penalty - منوی جریمه (ادمین)\n"
        "/reset - ریست بازیکن (ادمین)\n"
        "/endgame - پایان بازی",
        reply_markup=build_keyboard(update.effective_chat.id, user_id),
    )

async def newgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    msg, _ = do_newgame(chat_id, update.effective_chat.type, update.effective_user)
    await update.message.reply_text(msg, reply_markup=build_keyboard(chat_id, user_id))

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    msg = do_join(chat_id, update.effective_user)
    await update.message.reply_text(msg, reply_markup=build_keyboard(chat_id, user_id))

async def startgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    msg = do_startgame(chat_id)
    await update.message.reply_text(msg, reply_markup=build_keyboard(chat_id, user_id))

async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    msg, send_img, ended = do_roll(chat_id, update.effective_user)
    game = get_game(chat_id)
    if send_img and game:
        await update.message.reply_photo(
            photo=render_board(game),
            caption=msg,
            reply_markup=build_keyboard(chat_id, user_id)
        )
    else:
        await update.message.reply_text(msg, reply_markup=build_keyboard(chat_id, user_id))

async def board(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    game = get_game(chat_id)
    text = get_board_text(chat_id)
    if game:
        await update.message.reply_photo(
            photo=render_board(game),
            caption=text,
            reply_markup=build_keyboard(chat_id, user_id)
        )
    else:
        await update.message.reply_text(text, reply_markup=build_keyboard(chat_id, user_id))

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = get_leaderboard_text()
    await update.message.reply_text(text, reply_markup=build_keyboard(update.effective_chat.id, user_id))

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if user_id not in player_stats:
        await update.message.reply_text(
            "📊 شما هنوز در هیچ بازی شرکت نکردید!",
            reply_markup=build_keyboard(chat_id, user_id)
        )
        return
    
    stats = player_stats[user_id]
    win_rate = (stats["wins"] / stats["total_games"] * 100) if stats["total_games"] > 0 else 0
    
    text = (
        f"📊 آمار شخصی {update.effective_user.first_name}:\n"
        f"🎮 کل بازی‌ها: {stats['total_games']}\n"
        f"🏆 برد‌ها: {stats['wins']}\n"
        f"📈 درصد برد: {win_rate:.1f}%"
    )
    
    await update.message.reply_text(text, reply_markup=build_keyboard(chat_id, user_id))

async def undo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    msg, send_img = undo_last_move(chat_id)
    game = get_game(chat_id)
    if send_img and game:
        await update.message.reply_photo(
            photo=render_board(game),
            caption=msg,
            reply_markup=build_keyboard(chat_id, user_id)
        )
    else:
        await update.message.reply_text(msg, reply_markup=build_keyboard(chat_id, user_id))

async def endgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if chat_id in games:
        games.pop(chat_id)
        await update.message.reply_text("بازی پایان یافت.", reply_markup=build_keyboard(chat_id, user_id))
    else:
        await update.message.reply_text("بازی‌ای در حال انجام نبود.", reply_markup=build_keyboard(chat_id, user_id))

# =====================================================
# 🔨 دستورات مدیریت (ادمین)
# =====================================================

async def penalty_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("⛔ فقط ادمین میتونه از این دستور استفاده کنه.")
        return
    
    args = context.args
    if not args:
        text = get_penalty_menu_text(chat_id)
        await update.message.reply_text(text, reply_markup=build_keyboard(chat_id, user_id))
        return
    
    try:
        player_num = int(args[0]) - 1
        game = get_game(chat_id)
        if not game or not game["started"]:
            await update.message.reply_text("بازی فعال نیست.")
            return
        
        if player_num < 0 or player_num >= len(game["order"]):
            await update.message.reply_text("عدد بازیکن نامعتبر.")
            return
        
        target_id = game["order"][player_num]
        reason = " ".join(args[1:]) if len(args) > 1 else "تخلف"
        msg, _ = penalize_player(chat_id, target_id, reason)
        await update.message.reply_text(msg, reply_markup=build_keyboard(chat_id, user_id))
        
    except ValueError:
        await update.message.reply_text("فرمت: /penalty [عدد] [دلیل اختیاری]")

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("⛔ فقط ادمین میتونه از این دستور استفاده کنه.")
        return
    
    args = context.args
    if not args:
        game = get_game(chat_id)
        if not game or not game["started"]:
            await update.message.reply_text("بازی فعال نیست.")
            return
        
        lines = ["🔄 بازیکن‌ها برای ریست:"]
        for i, uid in enumerate(game["order"]):
            p = game["players"][uid]
            lines.append(f"{i+1}. {p['name']}")
        lines.append("\nعدد بازیکن رو انتخاب کن: /reset [عدد]")
        await update.message.reply_text("\n".join(lines), reply_markup=build_keyboard(chat_id, user_id))
        return
    
    try:
        player_num = int(args[0]) - 1
        game = get_game(chat_id)
        if not game or not game["started"]:
            await update.message.reply_text("بازی فعال نیست.")
            return
        
        if player_num < 0 or player_num >= len(game["order"]):
            await update.message.reply_text("عدد بازیکن نامعتبر.")
            return
        
        target_id = game["order"][player_num]
        msg, _ = reset_player_position(chat_id, target_id)
        await update.message.reply_text(msg, reply_markup=build_keyboard(chat_id, user_id))
        
    except ValueError:
        await update.message.reply_text("فرمت: /reset [عدد]")

# =====================================================
# 🎯 هندلر دکمه‌ها
# =====================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    chat_type = query.message.chat.type
    user_id = update.effective_user.id
    user = update.effective_user
    data = query.data

    if data == "newgame":
        msg, _ = do_newgame(chat_id, chat_type, user)
        await query.message.reply_text(msg, reply_markup=build_keyboard(chat_id, user_id))

    elif data == "join":
        msg = do_join(chat_id, user)
        await query.message.reply_text(msg, reply_markup=build_keyboard(chat_id, user_id))

    elif data == "startgame":
        msg = do_startgame(chat_id)
        await query.message.reply_text(msg, reply_markup=build_keyboard(chat_id, user_id))

    elif data == "roll":
        msg, send_img, ended = do_roll(chat_id, user)
        game = get_game(chat_id)
        if send_img and game:
            await query.message.reply_photo(
                photo=render_board(game),
                caption=msg,
                reply_markup=build_keyboard(chat_id, user_id)
            )
        else:
            await query.message.reply_text(msg, reply_markup=build_keyboard(chat_id, user_id))

    elif data == "board":
        game = get_game(chat_id)
        text = get_board_text(chat_id)
        if game:
            await query.message.reply_photo(
                photo=render_board(game),
                caption=text,
                reply_markup=build_keyboard(chat_id, user_id)
            )
        else:
            await query.message.reply_text(text, reply_markup=build_keyboard(chat_id, user_id))

    elif data == "undo":
        msg, send_img = undo_last_move(chat_id)
        game = get_game(chat_id)
        if send_img and game:
            await query.message.reply_photo(
                photo=render_board(game),
                caption=msg,
                reply_markup=build_keyboard(chat_id, user_id)
            )
        else:
            await query.message.reply_text(msg, reply_markup=build_keyboard(chat_id, user_id))

    elif data == "leaderboard":
        text = get_leaderboard_text()
        await query.message.reply_text(text, reply_markup=build_keyboard(chat_id, user_id))

    elif data == "penalty_menu":
        if not is_admin(user_id):
            await query.message.reply_text("⛔ فقط ادمین.")
            return
        text = get_penalty_menu_text(chat_id)
        await query.message.reply_text(text, reply_markup=build_keyboard(chat_id, user_id))

    elif data == "reset_all":
        if not is_admin(user_id):
            await query.message.reply_text("⛔ فقط ادمین.")
            return
        game = get_game(chat_id)
        if not game or not game["started"]:
            await query.message.reply_text("بازی فعال نیست.")
            return
        for uid in game["order"]:
            game["players"][uid]["pos"] = 0
        game["penalty"] = {}
        await query.message.reply_text("✅ همه بازیکن‌ها به شروع برگشتند.", reply_markup=build_keyboard(chat_id, user_id))

    elif data == "endgame":
        if chat_id in games:
            games.pop(chat_id)
            await query.message.reply_text("بازی پایان یافت.", reply_markup=build_keyboard(chat_id, user_id))
        else:
            await query.message.reply_text("بازی‌ای در حال انجام نبود.", reply_markup=build_keyboard(chat_id, user_id))

# =====================================================
# 🚀 اجرا
# =====================================================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN تنظیم نشده! متغیر محیطی BOT_TOKEN رو ست کن.")
    
    if not ADMIN_IDS:
        logger.warning("⚠️ ADMIN_IDS تنظیم نشده! دستورات مدیریت غیرفعال.")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("newgame", newgame))
    application.add_handler(CommandHandler("join", join))
    application.add_handler(CommandHandler("startgame", startgame))
    application.add_handler(CommandHandler("roll", roll))
    application.add_handler(CommandHandler("board", board))
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("undo", undo_command))
    application.add_handler(CommandHandler("endgame", endgame))
    
    # دستورات مدیریت
    application.add_handler(CommandHandler("penalty", penalty_command))
    application.add_handler(CommandHandler("reset", reset_command))
    
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("ربات در حال اجراست...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
