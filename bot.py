import os
import io
import random
import json
import logging
import asyncio
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")

def get_admin_ids():
    admin_str = os.environ.get("ADMIN_IDS", "")
    if not admin_str:
        return set()
    return set(map(int, admin_str.split(","))) if admin_str else set()

ADMIN_IDS = get_admin_ids()

# =====================================================
# 🎮 تنظیمات بازی
# =====================================================

BOARD_SIZE = 100
CELL_SIZE = 58
MARGIN = 30
BOARD_PX = CELL_SIZE * 10
IMG_SIZE = BOARD_PX + MARGIN * 2

# نقشه پیشرفته با نردبان‌ها و مارهای بیشتر
LADDERS = {
    2: 23, 8: 37, 15: 55, 22: 41, 28: 76, 36: 52, 
    44: 69, 53: 88, 61: 81, 71: 94, 78: 99
}
SNAKES = {
    14: 4, 19: 7, 26: 10, 35: 17, 42: 30, 48: 18,
    57: 39, 65: 46, 72: 58, 84: 64, 92: 73, 97: 79
}

PLAYER_COLORS = [
    "#E63946", "#1D3557", "#2A9D8F", "#F4A261",
    "#9B5DE5", "#00B4D8", "#F15BB5", "#FEE440",
    "#06D6A0", "#EF476F"
]

# =====================================================
# 📦 دیتابیس درون‌حافظه
# =====================================================

games = {}
leaderboard = {}
player_stats = {}
tournaments = {}
pending_invites = {}

# =====================================================
# 🎨 رندرینگ حرفه‌ای
# =====================================================

def create_dice_emoji(value):
    dice_faces = {
        1: "⚀", 2: "⚁", 3: "⚂",
        4: "⚃", 5: "⚄", 6: "⚅"
    }
    return dice_faces.get(value, "🎲")

def get_theme_colors(theme="dark"):
    themes = {
        "dark": {
            "bg": "#1a1a2e", "cell_odd": "#16213e", "cell_even": "#0f3460",
            "border": "#533483", "text": "#e94560", "grid": "#2a2a4a",
            "ladder": "#00ff88", "snake": "#ff4444"
        },
        "classic": {
            "bg": "#f5f0e8", "cell_odd": "#faf0e6", "cell_even": "#e8dcc8",
            "border": "#8b7355", "text": "#2c1810", "grid": "#d4c4a8",
            "ladder": "#228B22", "snake": "#DC143C"
        },
        "neon": {
            "bg": "#0a0a0a", "cell_odd": "#1a0033", "cell_even": "#0d001a",
            "border": "#ff00ff", "text": "#00ffff", "grid": "#330066",
            "ladder": "#00ff00", "snake": "#ff0066"
        }
    }
    return themes.get(theme, themes["dark"])

def render_board(game, theme="dark"):
    colors = get_theme_colors(theme)
    
    # تبدیل HEX به RGB
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    bg_rgb = hex_to_rgb(colors["bg"])
    cell_odd_rgb = hex_to_rgb(colors["cell_odd"])
    cell_even_rgb = hex_to_rgb(colors["cell_even"])
    border_rgb = hex_to_rgb(colors["border"])
    text_rgb = hex_to_rgb(colors["text"])
    grid_rgb = hex_to_rgb(colors["grid"])
    ladder_rgb = hex_to_rgb(colors["ladder"])
    snake_rgb = hex_to_rgb(colors["snake"])
    
    img = Image.new("RGB", (IMG_SIZE, IMG_SIZE), bg_rgb)
    draw = ImageDraw.Draw(img)
    
    # فونت‌ها
    try:
        font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
    except:
        font_big = font_small = font_title = ImageFont.load_default()
    
    # رسم سلول‌ها
    for n in range(1, 101):
        x, y = cell_to_xy(n)
        row = (n - 1) // 10
        color = cell_odd_rgb if row % 2 == 0 else cell_even_rgb
        
        # سایه‌ی سلول
        shadow_offset = 2
        draw.rectangle(
            [x - CELL_SIZE//2 + shadow_offset, y - CELL_SIZE//2 + shadow_offset,
             x + CELL_SIZE//2 + shadow_offset, y + CELL_SIZE//2 + shadow_offset],
            fill=(0, 0, 0, 50)
        )
        
        # سلول اصلی
        draw.rectangle(
            [x - CELL_SIZE//2, y - CELL_SIZE//2, x + CELL_SIZE//2, y + CELL_SIZE//2],
            fill=color, outline=border_rgb, width=2
        )
        
        # شماره سلول
        draw.text(
            (x - CELL_SIZE//2 + 4, y - CELL_SIZE//2 + 3),
            str(n), fill=text_rgb, font=font_small
        )
    
    # رسم نردبان‌ها (با افکت نئون)
    for a, b in LADDERS.items():
        x1, y1 = cell_to_xy(a)
        x2, y2 = cell_to_xy(b)
        # خط نردبان با ضخامت بیشتر
        for i in range(3):
            draw.line(
                [x1 - i, y1 - i, x2 - i, y2 - i],
                fill=ladder_rgb, width=6
            )
        # نقطه‌های شروع و پایان
        draw.ellipse([x1 - 8, y1 - 8, x1 + 8, y1 + 8], fill=ladder_rgb)
        draw.ellipse([x2 - 8, y2 - 8, x2 + 8, y2 + 8], fill=ladder_rgb)
        # برچسب نردبان
        draw.text((x1 - 15, y1 - 25), "🪜", font=font_big)
    
    # رسم مارها (با افکت)
    for a, b in SNAKES.items():
        x1, y1 = cell_to_xy(a)
        x2, y2 = cell_to_xy(b)
        for i in range(3):
            draw.line(
                [x1 + i, y1 + i, x2 + i, y2 + i],
                fill=snake_rgb, width=5
            )
        draw.ellipse([x1 - 9, y1 - 9, x1 + 9, y1 + 9], fill=snake_rgb)
        draw.ellipse([x2 - 6, y2 - 6, x2 + 6, y2 + 6], fill=snake_rgb)
        draw.text((x1 + 10, y1 - 20), "🐍", font=font_big)
    
    # رسم بازیکن‌ها با کیفیت بالا
    offsets = [
        (-16, -16), (16, -16), (-16, 16), (16, 16),
        (-16, 0), (16, 0), (0, -16), (0, 16),
        (-20, -20), (20, 20)
    ]
    
    for idx, uid in enumerate(game["order"]):
        p = game["players"][uid]
        pos = max(p["pos"], 1)
        x, y = cell_to_xy(pos)
        ox, oy = offsets[idx % len(offsets)]
        color = hex_to_rgb(PLAYER_COLORS[idx % len(PLAYER_COLORS)])
        
        # سایه مهره
        draw.ellipse(
            [x + ox - 14 + 2, y + oy - 14 + 2, x + ox + 14 + 2, y + oy + 14 + 2],
            fill=(0, 0, 0, 80)
        )
        
        # بدنه مهره
        draw.ellipse(
            [x + ox - 14, y + oy - 14, x + ox + 14, y + oy + 14],
            fill=color, outline=(255, 255, 255), width=3
        )
        
        # افکت درخشش
        draw.ellipse(
            [x + ox - 6, y + oy - 10, x + ox + 6, y + oy - 4],
            fill=(255, 255, 255, 100)
        )
        
        # علامت جریمه
        if "penalty" in game and uid in game["penalty"]:
            draw.ellipse(
                [x + ox - 18, y + oy - 18, x + ox + 18, y + oy + 18],
                outline=(255, 0, 0), width=4
            )
            draw.text((x + ox - 12, y + oy - 20), "⛔", font=font_small)
        
        # حرف اول اسم
        initial = (p["name"][0].upper() if p["name"] else "?")
        draw.text(
            (x + ox - 6, y + oy - 8),
            initial, fill="white", font=font_big
        )
    
    # هدر بازی
    draw.text(
        (MARGIN + 10, 10),
        f"🎲 {game.get('title', 'مار و پله')}",
        fill="#FFFFFF", font=font_title
    )
    
    # فوتر اطلاعات
    turn_name = game["players"][game["order"][game["turn"]]]["name"] if game["started"] else "در انتظار"
    footer_text = f"نوبت: {turn_name} | {len(game['order'])} بازیکن"
    draw.text(
        (MARGIN + 10, IMG_SIZE - 30),
        footer_text, fill="#AAAAAA", font=font_small
    )
    
    # برچسب تیم/گروه
    if "mode" in game:
        mode_label = "👤 خصوصی" if game["mode"] == "private" else "👥 گروهی"
        draw.text(
            (IMG_SIZE - 120, IMG_SIZE - 30),
            mode_label, fill="#888888", font=font_small
        )
    
    buf = io.BytesIO()
    img.save(buf, format="PNG", quality=95)
    buf.seek(0)
    return buf

def cell_to_xy(n):
    n0 = n - 1
    row = n0 // 10
    col = n0 % 10
    if row % 2 == 1:
        col = 9 - col
    x = MARGIN + col * CELL_SIZE + CELL_SIZE // 2
    y = MARGIN + (9 - row) * CELL_SIZE + CELL_SIZE // 2
    return x, y

# =====================================================
# ⌨️ کیبورد پیشرفته
# =====================================================

def build_main_menu(chat_id, user_id=None):
    """منوی اصلی ربات"""
    game = get_game(chat_id)
    
    keyboard = [
        [InlineKeyboardButton("🎮 بازی جدید", callback_data="newgame")],
        [InlineKeyboardButton("🏆 جدول امتیازات", callback_data="leaderboard")],
        [InlineKeyboardButton("📊 آمار من", callback_data="mystats")],
    ]
    
    if game and game["started"]:
        keyboard.insert(0, [InlineKeyboardButton("🎯 ادامه بازی", callback_data="resume")])
    
    return InlineKeyboardMarkup(keyboard)

def build_game_keyboard(chat_id, user_id=None):
    """کیبورد بازی"""
    game = get_game(chat_id)
    if not game:
        return build_main_menu(chat_id, user_id)
    
    if not game["started"]:
        # منوی قبل از شروع
        buttons = [
            [InlineKeyboardButton("➕ ورود به بازی", callback_data="join")],
            [InlineKeyboardButton("👥 دعوت از دوستان", callback_data="invite")],
        ]
        if len(game.get("order", [])) >= 2:
            buttons.append([InlineKeyboardButton("▶️ شروع بازی", callback_data="startgame")])
        return InlineKeyboardMarkup(buttons)
    
    # منوی حین بازی
    is_admin = user_id and user_id in ADMIN_IDS
    current_user = user_id and user_id in game.get("players", {})
    
    # دکمه‌های اصلی
    buttons = [
        [InlineKeyboardButton("🎲 پرتاب تاس", callback_data="roll")],
        [InlineKeyboardButton("📊 وضعیت تخته", callback_data="board")],
    ]
    
    # دکمه‌های اضافی
    extra_row = []
    if current_user:
        extra_row.append(InlineKeyboardButton("↩️ بازگشت", callback_data="undo"))
    extra_row.append(InlineKeyboardButton("📈 امتیازات", callback_data="leaderboard"))
    buttons.append(extra_row)
    
    # دکمه‌های مدیریت (فقط ادمین)
    if is_admin:
        admin_row = [
            InlineKeyboardButton("🔨 جریمه", callback_data="penalty_menu"),
            InlineKeyboardButton("🔄 ریست", callback_data="reset_menu"),
            InlineKeyboardButton("⚡ پاک‌سازی", callback_data="reset_all"),
        ]
        buttons.append(admin_row)
    
    buttons.append([InlineKeyboardButton("🚪 خروج از بازی", callback_data="endgame")])
    
    return InlineKeyboardMarkup(buttons)

def get_game(chat_id):
    return games.get(chat_id)

# =====================================================
# 🎲 منطق بازی (بهینه‌شده)
# =====================================================

def do_newgame(chat_id, chat_type, user, title=None):
    if chat_id in games:
        return "⚠️ یه بازی در حال انجامه! اول تمومش کن.", False
    
    game = {
        "players": {},
        "order": [],
        "turn": 0,
        "started": False,
        "mode": "private" if chat_type == "private" else "group",
        "history": [],
        "penalty": {},
        "title": title or "مار و پله",
        "created_at": datetime.now().isoformat(),
        "last_move": datetime.now().isoformat(),
        "dice_history": [],
        "chat_id": chat_id,
        "max_players": 10,
        "theme": "dark",
        "winner": None,
    }
    
    if chat_type == "private":
        game["players"][user.id] = {"name": user.first_name, "pos": 0}
        game["order"].append(user.id)
        game["started"] = True
        games[chat_id] = game
        return f"🎮 بازی '{game['title']}' شروع شد!\n{user.first_name} تاس بنداز 🎲", True
    
    games[chat_id] = game
    return "🎮 بازی جدید ساخته شد!\nاز دکمه‌ها برای ورود استفاده کن.", False

def do_join(chat_id, user):
    game = get_game(chat_id)
    if not game:
        return "⚠️ بازی‌ای وجود نداره! از /newgame استفاده کن."
    if game["started"]:
        return "⛔ بازی شروع شده! نمی‌تونی وارد شی."
    if user.id in game["players"]:
        return "✅ قبلاً وارد شدی!"
    if len(game["order"]) >= game.get("max_players", 10):
        return "❌ ظرفیت پر شده!"
    
    game["players"][user.id] = {"name": user.first_name, "pos": 0}
    game["order"].append(user.id)
    
    return f"✅ {user.first_name} وارد شد! ({len(game['order'])}/{game.get('max_players', 10)})"

def do_startgame(chat_id):
    game = get_game(chat_id)
    if not game:
        return "⚠️ بازی‌ای وجود نداره!"
    if game["started"]:
        return "⛔ بازی شروع شده!"
    if len(game["order"]) < 2:
        return "❌ حداقل ۲ بازیکن نیازه!"
    
    game["started"] = True
    first = game["players"][game["order"][0]]["name"]
    return f"🎯 بازی شروع شد!\nنوبت اول: {first} 🎲"

def do_roll(chat_id, user):
    game = get_game(chat_id)
    if not game or not game["started"]:
        return "⚠️ بازی شروع نشده!", False, False
    
    current = game["order"][game["turn"]]
    if game["mode"] == "group" and user.id != current:
        return f"⏳ نوبت {game['players'][current]['name']} هست!", False, False
    
    if user.id not in game["players"]:
        return "❌ تو این بازی نیستی!", False, False
    
    # چک جریمه
    if "penalty" in game and user.id in game["penalty"]:
        penalty = game["penalty"][user.id]
        if penalty["turns"] > 0:
            penalty["turns"] -= 1
            if penalty["turns"] == 0:
                del game["penalty"][user.id]
                msg = f"✅ جریمه {game['players'][user.id]['name']} تموم شد!"
            else:
                msg = f"⛔ {penalty['turns']} نوبت دیگه جریمه داری!"
            game["turn"] = (game["turn"] + 1) % len(game["order"])
            return msg, True, False
    
    # ذخیره برای Undo
    save_game_state(game)
    
    # پرتاب تاس
    dice = random.randint(1, 6)
    player = game["players"][user.id]
    old_pos = player["pos"]
    new_pos = old_pos + dice
    
    # تاریخچه تاس
    if "dice_history" not in game:
        game["dice_history"] = []
    game["dice_history"].append({
        "user": user.id,
        "dice": dice,
        "old_pos": old_pos,
        "time": datetime.now().isoformat()
    })
    if len(game["dice_history"]) > 50:
        game["dice_history"] = game["dice_history"][-50:]
    
    msg = f"🎲 {create_dice_emoji(dice)} {player['name']} تاس {dice} اومد!\n"
    msg += f"📍 از {player_line(old_pos)} به "
    
    if new_pos > BOARD_SIZE:
        player["pos"] = old_pos
        msg += f"{player_line(old_pos)} موندی (باید دقیق برسی ۱۰۰)"
        game["turn"] = (game["turn"] + 1) % len(game["order"])
        return msg, True, False
    
    player["pos"] = new_pos
    msg += f"{player_line(new_pos)}"
    
    # چک نردبان و مار
    if new_pos in LADDERS:
        player["pos"] = LADDERS[new_pos]
        msg += f"\n🪜 نردبان! رفت بالا به {player_line(player['pos'])}"
    elif new_pos in SNAKES:
        player["pos"] = SNAKES[new_pos]
        msg += f"\n🐍 مار! افتاد پایین به {player_line(player['pos'])}"
    
    # چک برد
    if player["pos"] == BOARD_SIZE:
        msg += f"\n\n🏆 {player['name']} برنده شد! 🎉"
        game["winner"] = user.id
        add_win(user.id, player['name'], chat_id)
        
        # پاک کردن بازی بعد از ۵ ثانیه
        async def cleanup():
            await asyncio.sleep(5)
            if chat_id in games:
                del games[chat_id]
        asyncio.create_task(cleanup())
        
        return msg, True, True
    
    # نوبت بعدی
    game["turn"] = (game["turn"] + 1) % len(game["order"])
    next_name = game["players"][game["order"][game["turn"]]]["name"]
    msg += f"\n\n⏭ نوبت: {next_name}"
    game["last_move"] = datetime.now().isoformat()
    
    return msg, True, False

def player_line(pos):
    return f"🏠 {pos}"

def save_game_state(game):
    if "history" not in game:
        game["history"] = []
    
    state = {
        "players": {uid: p.copy() for uid, p in game["players"].items()},
        "turn": game["turn"],
        "penalty": game.get("penalty", {}).copy(),
        "timestamp": datetime.now().isoformat()
    }
    game["history"].append(state)
    
    if len(game["history"]) > 10:
        game["history"].pop(0)

def undo_last_move(chat_id):
    game = get_game(chat_id)
    if not game or not game["started"]:
        return "⚠️ بازی فعال نیست!", False
    
    if "history" not in game or len(game["history"]) == 0:
        return "❌ حرکتی برای برگشت نیست!", False
    
    last = game["history"].pop()
    game["players"] = last["players"]
    game["turn"] = last["turn"]
    game["penalty"] = last.get("penalty", {})
    
    return "✅ حرکت قبلی برگشت داده شد!", True

# =====================================================
# 🏆 امتیازات و آمار
# =====================================================

def add_win(user_id, user_name, chat_id):
    if user_id not in leaderboard:
        leaderboard[user_id] = {"name": user_name, "wins": 0, "games": 0}
    leaderboard[user_id]["wins"] += 1
    leaderboard[user_id]["games"] += 1
    
    if user_id not in player_stats:
        player_stats[user_id] = {"total": 0, "wins": 0}
    player_stats[user_id]["total"] += 1
    player_stats[user_id]["wins"] += 1

def get_leaderboard_text():
    if not leaderboard:
        return "🏆 هنوز بردی ثبت نشده!"
    
    sorted_players = sorted(leaderboard.items(), key=lambda x: x[1]["wins"], reverse=True)
    lines = ["🏆 **جدول امتیازات**", "━━━━━━━━━━━━━━━"]
    
    for i, (uid, data) in enumerate(sorted_players[:10], 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        lines.append(f"{medal} {data['name']}: {data['wins']} برد")
    
    return "\n".join(lines)

def get_stats_text(user_id, user_name):
    if user_id not in player_stats:
        return f"📊 {user_name} هنوز بازی نکرده!"
    
    stats = player_stats[user_id]
    win_rate = (stats["wins"] / stats["total"] * 100) if stats["total"] > 0 else 0
    
    return (
        f"📊 **آمار {user_name}**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🎮 کل بازی‌ها: {stats['total']}\n"
        f"🏆 برد‌ها: {stats['wins']}\n"
        f"📈 درصد برد: {win_rate:.1f}%\n"
        f"━━━━━━━━━━━━━━━"
    )

# =====================================================
# 🔨 سیستم جریمه پیشرفته
# =====================================================

def penalize_player(chat_id, user_id, reason="تخلف", turns=3):
    game = get_game(chat_id)
    if not game or not game["started"]:
        return "⚠️ بازی فعال نیست!", False
    
    if user_id not in game["players"]:
        return "❌ بازیکن در بازی نیست!", False
    
    if "penalty" not in game:
        game["penalty"] = {}
    
    game["penalty"][user_id] = {"reason": reason, "turns": turns}
    
    # رد کردن نوبت
    if game["order"][game["turn"]] == user_id:
        game["turn"] = (game["turn"] + 1) % len(game["order"])
    
    return f"🔨 {game['players'][user_id]['name']} جریمه شد!\nدلیل: {reason}\n{turns} نوبت محرومیت", True

def reset_player(chat_id, user_id):
    game = get_game(chat_id)
    if not game or not game["started"]:
        return "⚠️ بازی فعال نیست!", False
    
    if user_id not in game["players"]:
        return "❌ بازیکن در بازی نیست!", False
    
    game["players"][user_id]["pos"] = 0
    if "penalty" in game and user_id in game["penalty"]:
        del game["penalty"][user_id]
    
    return f"🔄 {game['players'][user_id]['name']} به شروع برگشت!", True

# =====================================================
# 🤖 هندلرهای ربات
# =====================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"🐍🎲 سلام {user.first_name}!\n"
        "به **مار و پله‌ی حرفه‌ای** خوش اومدی!\n\n"
        "📋 **دستورات:**\n"
        "/newgame - بازی جدید\n"
        "/join - ورود به بازی\n"
        "/startgame - شروع بازی\n"
        "/roll - پرتاب تاس\n"
        "/board - نمایش تخته\n"
        "/undo - برگشت حرکت\n"
        "/leaderboard - جدول امتیازات\n"
        "/stats - آمار من\n"
        "/endgame - پایان بازی\n\n"
        "🔹 از دکمه‌ها استفاده کن!",
        reply_markup=build_main_menu(update.effective_chat.id, user.id)
    )

async def newgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    # گرفتن عنوان دلخواه
    title = " ".join(context.args) if context.args else None
    
    msg, success = do_newgame(chat_id, update.effective_chat.type, user, title)
    await update.message.reply_text(
        msg,
        reply_markup=build_game_keyboard(chat_id, user.id)
    )

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    msg = do_join(chat_id, user)
    await update.message.reply_text(
        msg,
        reply_markup=build_game_keyboard(chat_id, user.id)
    )

async def startgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    msg = do_startgame(chat_id)
    await update.message.reply_text(
        msg,
        reply_markup=build_game_keyboard(chat_id, user.id)
    )

async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    msg, send_img, ended = do_roll(chat_id, user)
    
    game = get_game(chat_id)
    if send_img and game:
        img = render_board(game)
        await update.message.reply_photo(
            photo=img,
            caption=msg,
            reply_markup=build_game_keyboard(chat_id, user.id)
        )
    else:
        await update.message.reply_text(
            msg,
            reply_markup=build_game_keyboard(chat_id, user.id)
        )

async def board(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = get_game(chat_id)
    
    if not game:
        await update.message.reply_text("⚠️ بازی‌ای وجود نداره!")
        return
    
    img = render_board(game)
    text = get_board_text(chat_id)
    await update.message.reply_photo(
        photo=img,
        caption=text,
        reply_markup=build_game_keyboard(chat_id, user.id)
    )

def get_board_text(chat_id):
    game = get_game(chat_id)
    if not game or not game["players"]:
        return "📊 تخته خالی است!"
    
    lines = ["📊 **وضعیت بازی**", "━━━━━━━━━━━━━━━"]
    for uid in game["order"]:
        p = game["players"][uid]
        status = ""
        if "penalty" in game and uid in game["penalty"]:
            status = f" ⛔ جریمه ({game['penalty'][uid]['turns']})"
        lines.append(f"• {p['name']}: {player_line(p['pos'])}{status}")
    
    return "\n".join(lines)

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = get_leaderboard_text()
    await update.message.reply_text(
        text,
        reply_markup=build_main_menu(update.effective_chat.id, update.effective_user.id)
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = get_stats_text(user.id, user.first_name)
    await update.message.reply_text(
        text,
        reply_markup=build_main_menu(update.effective_chat.id, user.id)
    )

async def undo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    msg, success = undo_last_move(chat_id)
    game = get_game(chat_id)
    
    if success and game:
        img = render_board(game)
        await update.message.reply_photo(
            photo=img,
            caption=msg,
            reply_markup=build_game_keyboard(chat_id, user.id)
        )
    else:
        await update.message.reply_text(
            msg,
            reply_markup=build_game_keyboard(chat_id, user.id)
        )

async def endgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if chat_id in games:
        del games[chat_id]
        await update.message.reply_text(
            "🚪 بازی پایان یافت!",
            reply_markup=build_main_menu(chat_id, user.id)
        )
    else:
        await update.message.reply_text(
            "⚠️ بازی‌ای وجود نداشت!",
            reply_markup=build_main_menu(chat_id, user.id)
        )

# =====================================================
# 🔨 دستورات ادمین
# =====================================================

async def penalty_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ فقط ادمین!")
        return
    
    args = context.args
    if not args:
        game = get_game(chat_id)
        if not game or not game["started"]:
            await update.message.reply_text("⚠️ بازی فعال نیست!")
            return
        
        lines = ["🔨 **بازیکن‌ها برای جریمه**", "━━━━━━━━━━━━━━━"]
        for i, uid in enumerate(game["order"], 1):
            p = game["players"][uid]
            status = "⛔ جریمه" if "penalty" in game and uid in game["penalty"] else "✅ سالم"
            lines.append(f"{i}. {p['name']} — {status}")
        lines.append("\n📝 /penalty [شماره] [دلیل]")
        
        await update.message.reply_text("\n".join(lines))
        return
    
    try:
        num = int(args[0]) - 1
        game = get_game(chat_id)
        if not game or not game["started"]:
            await update.message.reply_text("⚠️ بازی فعال نیست!")
            return
        
        if num < 0 or num >= len(game["order"]):
            await update.message.reply_text("❌ شماره نامعتبر!")
            return
        
        target_id = game["order"][num]
        reason = " ".join(args[1:]) if len(args) > 1 else "تخلف"
        msg, _ = penalize_player(chat_id, target_id, reason)
        
        game = get_game(chat_id)
        if game:
            img = render_board(game)
            await update.message.reply_photo(
                photo=img,
                caption=msg,
                reply_markup=build_game_keyboard(chat_id, user.id)
            )
        else:
            await update.message.reply_text(msg)
            
    except ValueError:
        await update.message.reply_text("❌ فرمت: /penalty [شماره] [دلیل]")

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ فقط ادمین!")
        return
    
    args = context.args
    if not args:
        game = get_game(chat_id)
        if not game or not game["started"]:
            await update.message.reply_text("⚠️ بازی فعال نیست!")
            return
        
        lines = ["🔄 **بازیکن‌ها برای ریست**", "━━━━━━━━━━━━━━━"]
        for i, uid in enumerate(game["order"], 1):
            p = game["players"][uid]
            lines.append(f"{i}. {p['name']} — {player_line(p['pos'])}")
        lines.append("\n📝 /reset [شماره]")
        
        await update.message.reply_text("\n".join(lines))
        return
    
    try:
        num = int(args[0]) - 1
        game = get_game(chat_id)
        if not game or not game["started"]:
            await update.message.reply_text("⚠️ بازی فعال نیست!")
            return
        
        if num < 0 or num >= len(game["order"]):
            await update.message.reply_text("❌ شماره نامعتبر!")
            return
        
        target_id = game["order"][num]
        msg, _ = reset_player(chat_id, target_id)
        
        game = get_game(chat_id)
        if game:
            img = render_board(game)
            await update.message.reply_photo(
                photo=img,
                caption=msg,
                reply_markup=build_game_keyboard(chat_id, user.id)
            )
        else:
            await update.message.reply_text(msg)
            
    except ValueError:
        await update.message.reply_text("❌ فرمت: /reset [شماره]")

# =====================================================
# 🎯 هندلر دکمه‌ها
# =====================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    user = update.effective_user
    data = query.data
    
    # منوی اصلی
    if data == "newgame":
        msg, _ = do_newgame(chat_id, query.message.chat.type, user)
        await query.message.reply_text(
            msg,
            reply_markup=build_game_keyboard(chat_id, user.id)
        )
    
    elif data == "leaderboard":
        text = get_leaderboard_text()
        await query.message.reply_text(
            text,
            reply_markup=build_main_menu(chat_id, user.id)
        )
    
    elif data == "mystats":
        text = get_stats_text(user.id, user.first_name)
        await query.message.reply_text(
            text,
            reply_markup=build_main_menu(chat_id, user.id)
        )
    
    elif data == "resume":
        game = get_game(chat_id)
        if game:
            img = render_board(game)
            await query.message.reply_photo(
                photo=img,
                caption="🎯 ادامه بازی!",
                reply_markup=build_game_keyboard(chat_id, user.id)
            )
        else:
            await query.message.reply_text(
                "⚠️ بازی‌ای وجود نداره!",
                reply_markup=build_main_menu(chat_id, user.id)
            )
    
    # منوی بازی
    elif data == "join":
        msg = do_join(chat_id, user)
        game = get_game(chat_id)
        if game:
            img = render_board(game)
            await query.message.reply_photo(
                photo=img,
                caption=msg,
                reply_markup=build_game_keyboard(chat_id, user.id)
            )
        else:
            await query.message.reply_text(msg)
    
    elif data == "startgame":
        msg = do_startgame(chat_id)
        game = get_game(chat_id)
        if game:
            img = render_board(game)
            await query.message.reply_photo(
                photo=img,
                caption=msg,
                reply_markup=build_game_keyboard(chat_id, user.id)
            )
        else:
            await query.message.reply_text(msg)
    
    elif data == "roll":
        msg, send_img, ended = do_roll(chat_id, user)
        game = get_game(chat_id)
        if send_img and game:
            img = render_board(game)
            await query.message.reply_photo(
                photo=img,
                caption=msg,
                reply_markup=build_game_keyboard(chat_id, user.id)
            )
        else:
            await query.message.reply_text(
                msg,
                reply_markup=build_game_keyboard(chat_id, user.id)
            )
    
    elif data == "board":
        game = get_game(chat_id)
        if game:
            img = render_board(game)
            text = get_board_text(chat_id)
            await query.message.reply_photo(
                photo=img,
                caption=text,
                reply_markup=build_game_keyboard(chat_id, user.id)
            )
        else:
            await query.message.reply_text("⚠️ بازی‌ای وجود نداره!")
    
    elif data == "undo":
        msg, success = undo_last_move(chat_id)
        game = get_game(chat_id)
        if success and game:
            img = render_board(game)
            await query.message.reply_photo(
                photo=img,
                caption=msg,
                reply_markup=build_game_keyboard(chat_id, user.id)
            )
        else:
            await query.message.reply_text(
                msg,
                reply_markup=build_game_keyboard(chat_id, user.id)
            )
    
    elif data == "endgame":
        if chat_id in games:
            del games[chat_id]
            await query.message.reply_text(
                "🚪 بازی پایان یافت!",
                reply_markup=build_main_menu(chat_id, user.id)
            )
        else:
            await query.message.reply_text(
                "⚠️ بازی‌ای وجود نداشت!",
                reply_markup=build_main_menu(chat_id, user.id)
            )
    
    # منوی ادمین
    elif data == "penalty_menu":
        if user.id not in ADMIN_IDS:
            await query.message.reply_text("⛔ فقط ادمین!")
            return
        
        game = get_game(chat_id)
        if not game or not game["started"]:
            await query.message.reply_text("⚠️ بازی فعال نیست!")
            return
        
        lines = ["🔨 **بازیکن‌ها برای جریمه**", "━━━━━━━━━━━━━━━"]
        for i, uid in enumerate(game["order"], 1):
            p = game["players"][uid]
            status = "⛔ جریمه" if "penalty" in game and uid in game["penalty"] else "✅ سالم"
            lines.append(f"{i}. {p['name']} — {status}")
        lines.append("\n📝 از دستور /penalty استفاده کن.")
        
        await query.message.reply_text("\n".join(lines))
    
    elif data == "reset_menu":
        if user.id not in ADMIN_IDS:
            await query.message.reply_text("⛔ فقط ادمین!")
            return
        
        game = get_game(chat_id)
        if not game or not game["started"]:
            await query.message.reply_text("⚠️ بازی فعال نیست!")
            return
        
        lines = ["🔄 **بازیکن‌ها برای ریست**", "━━━━━━━━━━━━━━━"]
        for i, uid in enumerate(game["order"], 1):
            p = game["players"][uid]
            lines.append(f"{i}. {p['name']} — {player_line(p['pos'])}")
        lines.append("\n📝 از دستور /reset استفاده کن.")
        
        await query.message.reply_text("\n".join(lines))
    
    elif data == "reset_all":
        if user.id not in ADMIN_IDS:
            await query.message.reply_text("⛔ فقط ادمین!")
            return
        
        game = get_game(chat_id)
        if not game or not game["started"]:
            await query.message.reply_text("⚠️ بازی فعال نیست!")
            return
        
        for uid in game["order"]:
            game["players"][uid]["pos"] = 0
        game["penalty"] = {}
        
        img = render_board(game)
        await query.message.reply_photo(
            photo=img,
            caption="✅ همه بازیکن‌ها به شروع برگشتند!",
            reply_markup=build_game_keyboard(chat_id, user.id)
        )
    
    elif data == "invite":
        await query.message.reply_text(
            "👥 برای دعوت دوستان:\n"
            "1. لینک گروه رو براشون بفرست\n"
            "2. ازشون بخواه وارد بشن\n"
            "3. بعد از ۲ نفر، بازی رو شروع کن"
        )

# =====================================================
# 🚀 اجرا
# =====================================================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN تنظیم نشده!")
    
    if ADMIN_IDS:
        logger.info(f"✅ ادمین‌ها: {ADMIN_IDS}")
    else:
        logger.warning("⚠️ ADMIN_IDS تنظیم نشده!")
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # دستورات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newgame", newgame))
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("startgame", startgame))
    app.add_handler(CommandHandler("roll", roll))
    app.add_handler(CommandHandler("board", board))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("undo", undo_command))
    app.add_handler(CommandHandler("endgame", endgame))
    app.add_handler(CommandHandler("penalty", penalty_command))
    app.add_handler(CommandHandler("reset", reset_command))
    
    # دکمه‌ها
    app.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("🐍🎲 ربات مار و پله راه‌اندازی شد!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
