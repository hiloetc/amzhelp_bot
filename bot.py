import asyncio
import os
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile
from PIL import Image, ImageDraw, ImageFont

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN не найден. Проверь файл .env")

# ========== НАСТРОЙКИ ==========
TEMPLATE_PATH = "template.png"
FONT_PATH = "fonts/Oswald-Bold.otf"

# Размеры карточки (можно менять)
CARD_W, CARD_H = 1080, 1350
HEADER_H = 180          # Высота "шапки" с иконкой
MARGIN = 60             # Отступы по краям
LINE_H = 55             # Высота строки текста
MAX_CHARS_PER_LINE = 42 # Символов в строке (подбирается под шрифт)

# Цвета
BG_COLOR = (13, 13, 13)
HEADER_COLOR = (255, 122, 0)      # Оранжевый как на фото
TEXT_COLOR = (255, 255, 255)
SHADOW_COLOR = (0, 0, 0, 120)


# ========== РЕНДЕР КАРТИНКИ ==========
def wrap_text(text: str, max_chars: int) -> list[str]:
    """Переносит длинный текст на строки."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current += (" " if current else "") + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_card(title: str, items: list[str]) -> bytes:
    """Рисует карточку и возвращает PNG в байтах."""
    # Фон
    img = Image.new("RGB", (CARD_W, CARD_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Загрузка шрифтов
    try:
        font_title = ImageFont.truetype(FONT_PATH, 52)
        font_body = ImageFont.truetype(FONT_PATH, 38)
        font_small = ImageFont.truetype(FONT_PATH, 30)
    except Exception:
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # --- Шапка: плашка с оранжевым заголовком ---
    draw.rounded_rectangle(
        [(MARGIN, MARGIN), (CARD_W - MARGIN, MARGIN + 90)],
        radius=16,
        fill=HEADER_COLOR,
    )
    draw.text((MARGIN + 30, MARGIN + 18), title.upper(), font=font_title, fill=BG_COLOR)

    # --- Тело: пункты ---
    y = MARGIN + 90 + 50
    for item in items:
        # Номер и текст
        lines = wrap_text(item, MAX_CHARS_PER_LINE)
        for i, line in enumerate(lines):
            prefix = "" if i > 0 else "• "
            draw.text((MARGIN + 20, y), prefix + line, font=font_body, fill=TEXT_COLOR)
            y += LINE_H
        y += 15  # Отступ между пунктами

        if y > CARD_H - 100:
            break

    # --- Подпись снизу ---
    draw.text(
        (MARGIN, CARD_H - 60),
        "AMAZING HUD · P.S. Незнание закона не освобождает от ответственности",
        font=font_small,
        fill=(150, 150, 150),
    )

    # В байты
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


# ========== БОТ ==========
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хранилище состояний (простое, в памяти)
user_data = {}


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я генерирую подсказки в стиле AMAZING HUD.\n\n"
        "Отправь текст в формате:\n"
        "```\n"
        "Заголовок: Основания для задержания\n"
        "1. Если лицо в розыске — Ст. 4.9.4.2.П.2\n"
        "2. При проникновении на объект — Ст. 4.9.4.2.П.4\n"
        "3. Совершивших правонарушение — Ст. 9.4.2.П.5\n"
        "```\n"
        "Или отправь /make и введи текст в следующем сообщении.",
        parse_mode="Markdown",
    )


@dp.message(Command("make"))
async def cmd_make(message: types.Message):
    await message.answer("Отправь текст подсказки в формате:\n`Заголовок: ...\n1. ...\n2. ...`", parse_mode="Markdown")
    user_data[message.from_user.id] = {"step": "awaiting_text"}


@dp.message()
async def handle_text(message: types.Message):
    state = user_data.get(message.from_user.id, {})
    if state.get("step") != "awaiting_text":
        await message.answer("Используй /make чтобы создать подсказку.")
        return

    text = message.text or ""
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    if not lines:
        await message.answer("Пустой текст. Попробуй ещё раз.")
        return

    # Парсим заголовок
    title = "ПОДСКАЗКА"
    items = []
    for line in lines:
        if line.lower().startswith("заголовок:"):
            title = line.split(":", 1)[1].strip()
        else:
            items.append(line)

    if not items:
        items = [title]
        title = "ПОДСКАЗКА"

    # Рендерим
    await message.answer("🎨 Генерирую картинку...")
    try:
        img_bytes = render_card(title, items)
        photo = BufferedInputFile(img_bytes, filename="hud.png")
        await message.answer_photo(photo, caption=f"✅ {title}")
    except Exception as e:
        await message.answer(f"Ошибка при генерации: {e}")

    # Сброс состояния
    user_data.pop(message.from_user.id, None)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())