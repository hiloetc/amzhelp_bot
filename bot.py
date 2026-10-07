import asyncio
import os
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from PIL import Image, ImageDraw, ImageFont

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN не найден. Проверь файл .env")

# ========== НАСТРОЙКИ ==========
FONT_PATH = "fonts/PT-Sans-Narrow-Bold.ttf"

# Доступные разрешения
RESOLUTIONS = {
    "hd":    {"w": 1920, "h": 1080, "label": "🖥 1920×1080 (HD)"},
    "qhd":   {"w": 2560, "h": 1440, "label": "🖥 2560×1440 (QHD)"},
    "vert":  {"w": 1080, "h": 1350, "label": "📱 1080×1350 (вертикально)"},
}

# Цвета
BG_COLOR = (13, 13, 13)
HEADER_COLOR = (255, 122, 0)
TEXT_COLOR = (255, 255, 255)
MUTED_COLOR = (150, 150, 150)


# ========== РЕНДЕР КАРТИНКИ ==========
def wrap_text(text: str, max_chars: int) -> list[str]:
    words = text.split()
    lines, current = [], ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current += (" " if current else "") + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_card(title: str, items: list[str], resolution_key: str = "hd") -> bytes:
    """Рисует карточку под заданное разрешение."""
    res = RESOLUTIONS.get(resolution_key, RESOLUTIONS["hd"])
    W, H = res["w"], res["h"]

    # Масштаб — все размеры привязаны к ширине 1920 как базовой
    scale = W / 1920

    margin = int(60 * scale)
    header_h = int(140 * scale)
    title_size = int(72 * scale)
    body_size = int(48 * scale)
    small_size = int(34 * scale)
    line_h = int(70 * scale)
    item_gap = int(20 * scale)

    # Фон
    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Шрифты
    try:
        font_title = ImageFont.truetype(FONT_PATH, title_size)
        font_body = ImageFont.truetype(FONT_PATH, body_size)
        font_small = ImageFont.truetype(FONT_PATH, small_size)
    except Exception as e:
        print(f"⚠️ Шрифт не загрузился: {e}. Использую дефолтный.")
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # --- Шапка ---
    draw.rounded_rectangle(
        [(margin, margin), (W - margin, margin + header_h)],
        radius=int(20 * scale),
        fill=HEADER_COLOR,
    )
    # Центрируем текст заголовка по вертикали в плашке
    try:
        bbox = draw.textbbox((0, 0), title.upper(), font=font_title)
        text_h = bbox[3] - bbox[1]
    except Exception:
        text_h = title_size
    title_y = margin + (header_h - text_h) // 2 - int(8 * scale)
    draw.text((margin + int(40 * scale), title_y), title.upper(), font=font_title, fill=BG_COLOR)

    # --- Тело ---
    y = margin + header_h + int(60 * scale)
    max_chars = int((W - 2 * margin - int(80 * scale)) / (body_size * 0.55))

    for item in items:
        lines = wrap_text(item, max_chars)
        for i, line in enumerate(lines):
            prefix = "• " if i == 0 else "   "
            draw.text((margin + int(30 * scale), y), prefix + line, font=font_body, fill=TEXT_COLOR)
            y += line_h
        y += item_gap
        if y > H - int(120 * scale):
            break

    # --- Подпись снизу ---
    draw.text(
        (margin, H - int(70 * scale)),
        "AMAZING HUD · Незнание закона не освобождает от ответственности",
        font=font_small,
        fill=MUTED_COLOR,
    )

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()


# ========== БОТ ==========
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# user_id -> {"step": "awaiting_text" | "awaiting_resolution", "text": "..."}
user_data = {}


def resolution_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, data in RESOLUTIONS.items():
        kb.button(text=data["label"], callback_data=f"res:{key}")
    kb.adjust(1)
    return kb.as_markup()


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я генерирую подсказки в стиле AMAZING HUD.\n\n"
        "Как использовать:\n"
        "1. Отправь /make\n"
        "2. Введи текст в формате:\n"
        "```\n"
        "Заголовок: Основания для задержания\n"
        "1. Если лицо в розыске — Ст. 4.9.4.2.П.2\n"
        "2. При проникновении на объект — Ст. 4.9.4.2.П.4\n"
        "```\n"
        "3. Выбери разрешение — бот пришлёт готовую картинку.",
        parse_mode="Markdown",
    )


@dp.message(Command("make"))
async def cmd_make(message: types.Message):
    user_data[message.from_user.id] = {"step": "awaiting_text"}
    await message.answer(
        "📝 Отправь текст подсказки в формате:\n"
        "```\n"
        "Заголовок: ...\n"
        "1. ...\n"
        "2. ...\n"
        "```",
        parse_mode="Markdown",
    )


@dp.callback_query(lambda c: c.data and c.data.startswith("res:"))
async def on_resolution(callback: types.CallbackQuery):
    uid = callback.from_user.id
    state = user_data.get(uid, {})
    text = state.get("text")
    if not text:
        await callback.answer("Сначала отправь текст через /make", show_alert=True)
        return

    res_key = callback.data.split(":")[1]
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("🎨 Генерирую картинку...")

    try:
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        title = "ПОДСКАЗКА"
        items = []
        for line in lines:
            if line.lower().startswith("заголовок:"):
                title = line.split(":", 1)[1].strip()
            else:
                items.append(line)
        if not items:
            items, title = [title], "ПОДСКАЗКА"

        img_bytes = render_card(title, items, res_key)
        photo = BufferedInputFile(img_bytes, filename="hud.png")
        await callback.message.answer_photo(
            photo,
            caption=f"✅ {title} · {RESOLUTIONS[res_key]['label']}",
        )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")

    user_data.pop(uid, None)
    await callback.answer()


@dp.message()
async def handle_text(message: types.Message):
    uid = message.from_user.id
    state = user_data.get(uid, {})

    if state.get("step") != "awaiting_text":
        await message.answer("Используй /make чтобы создать подсказку.")
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Пустой текст. Попробуй ещё раз.")
        return

    user_data[uid] = {"step": "awaiting_resolution", "text": text}
    await message.answer("🎯 Выбери разрешение:", reply_markup=resolution_keyboard())


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())