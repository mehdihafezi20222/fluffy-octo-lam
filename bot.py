import os
import random
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
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

# state هر بازی به ازای chat_id
# games[chat_id] = {
#   "players": {user_id: {"name": str, "pos": int}},
#   "order": [user_id, ...],
#   "turn": index,
#   "started": bool,
#   "mode": "group" | "private",
# }
games = {}


def get_game(chat_id):
    return games.get(chat_id)


def player_line(pos):
    return f"خونه {pos}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🐍🎲 به ربات بازی مار و پله خوش اومدی!\n\n"
        "دستورات:\n"
        "/newgame - شروع بازی جدید\n"
        "/join - پیوستن به بازی (فقط توی گروه)\n"
        "/startgame - شروع رسمی بازی (فقط توی گروه، بعد از join همه)\n"
        "/roll - انداختن تاس\n"
        "/board - نمایش وضعیت فعلی\n"
        "/endgame - پایان دادن به بازی"
    )


async def newgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    user = update.effective_user

    if chat_id in games and games[chat_id]["started"]:
        await update.message.reply_text("یه بازی هنوز در حال انجامه! اول /endgame بزن.")
        return

    if chat_type == "private":
        # حالت تک‌نفره: خودش شروع می‌کنه
        games[chat_id] = {
            "players": {user.id: {"name": user.first_name, "pos": 0}},
            "order": [user.id],
            "turn": 0,
            "started": True,
            "mode": "private",
        }
        await update.message.reply_text(
            f"بازی شروع شد {user.first_name}! برای انداختن تاس /roll بزن."
        )
    else:
        # حالت گروهی: لابی ساخته می‌شه و باید افراد join کنن
        games[chat_id] = {
            "players": {},
            "order": [],
            "turn": 0,
            "started": False,
            "mode": "group",
        }
        await update.message.reply_text(
            "بازی جدید توی گروه ساخته شد!\n"
            "همه بازیکن‌ها با دستور /join وارد بازی بشن.\n"
            "وقتی همه آماده بودن، هر کسی /startgame رو بزنه تا بازی شروع بشه."
        )


async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = get_game(chat_id)

    if update.effective_chat.type == "private":
        await update.message.reply_text("توی چت خصوصی نیازی به /join نیست، مستقیم /newgame بزن.")
        return

    if not game:
        await update.message.reply_text("هنوز بازی‌ای ساخته نشده. اول /newgame بزن.")
        return

    if game["started"]:
        await update.message.reply_text("بازی از قبل شروع شده، نمی‌تونی الان join کنی.")
        return

    if user.id in game["players"]:
        await update.message.reply_text("قبلاً join کردی!")
        return

    game["players"][user.id] = {"name": user.first_name, "pos": 0}
    game["order"].append(user.id)
    await update.message.reply_text(f"{user.first_name} به بازی پیوست ✅ (تعداد بازیکن‌ها: {len(game['order'])})")


async def startgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = get_game(chat_id)

    if update.effective_chat.type == "private":
        await update.message.reply_text("توی چت خصوصی بازی خودکار با /newgame شروع می‌شه.")
        return

    if not game:
        await update.message.reply_text("هنوز بازی‌ای ساخته نشده. اول /newgame بزن.")
        return

    if game["started"]:
        await update.message.reply_text("بازی از قبل شروع شده.")
        return

    if len(game["order"]) < 2:
        await update.message.reply_text("حداقل ۲ نفر باید join کرده باشن تا بازی شروع بشه.")
        return

    game["started"] = True
    first_player = game["players"][game["order"][0]]["name"]
    await update.message.reply_text(
        f"بازی شروع شد! 🎲\nنوبت اول با {first_player} هست. /roll بزن."
    )


async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = get_game(chat_id)

    if not game or not game["started"]:
        await update.message.reply_text("بازی‌ای در حال انجام نیست. با /newgame شروع کن.")
        return

    current_player_id = game["order"][game["turn"]]

    if game["mode"] == "group" and user.id != current_player_id:
        current_name = game["players"][current_player_id]["name"]
        await update.message.reply_text(f"الان نوبت {current_name} هست، صبر کن!")
        return

    if user.id not in game["players"]:
        await update.message.reply_text("تو توی این بازی نیستی!")
        return

    dice = random.randint(1, 6)
    player = game["players"][user.id]
    new_pos = player["pos"] + dice

    msg = f"🎲 {player['name']} تاس انداخت: {dice}\n"

    if new_pos > BOARD_SIZE:
        msg += f"برای رسیدن به خونه ۱۰۰ باید عدد دقیق بیاری. هنوز توی {player_line(player['pos'])} هستی."
    else:
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
            await update.message.reply_text(msg)
            return

    # نوبت بعدی (فقط در حالت گروهی معنی داره)
    if game["mode"] == "group":
        game["turn"] = (game["turn"] + 1) % len(game["order"])
        next_name = game["players"][game["order"][game["turn"]]]["name"]
        msg += f"\n\nنوبت بعدی: {next_name}"

    await update.message.reply_text(msg)


async def board(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = get_game(chat_id)

    if not game or not game["players"]:
        await update.message.reply_text("بازی‌ای در حال انجام نیست.")
        return

    lines = ["📊 وضعیت فعلی بازی:"]
    for uid in game["order"]:
        p = game["players"][uid]
        lines.append(f"- {p['name']}: {player_line(p['pos'])}")

    await update.message.reply_text("\n".join(lines))


async def endgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in games:
        games.pop(chat_id)
        await update.message.reply_text("بازی پایان یافت.")
    else:
        await update.message.reply_text("بازی‌ای در حال انجام نبود.")


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

    logger.info("ربات در حال اجراست...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
