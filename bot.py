import asyncio
import os
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from PIL import Image, ImageDraw, ImageFont

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN не найден. Проверь .env или переменные Bothost")

# ========== НАСТРОЙКИ ==========
FONT_PATH = "fonts/PT-Sans-Narrow-Bold.ttf"

RESOLUTIONS = {
    "hd":   {"w": 1920, "h": 1080, "label": "🖥 1920×1080 (HD)"},
    "qhd":  {"w": 2560, "h": 1440, "label": "🖥 2560×1440 (QHD)"},
    "vert": {"w": 1080, "h": 1350, "label": "📱 1080×1350 (вертикально)"},
    "uhd":  {"w": 3840, "h": 2160, "label": "🖥 3840×2160 (4K, для 20k символов)"},
}

BG_COLOR = (13, 13, 13)
HEADER_COLOR = (255, 122, 0)
TEXT_COLOR = (255, 255, 255)
MUTED_COLOR = (150, 150, 150)

MAX_TOTAL_CHARS = 20000


# ========== ХЕЛПЕРЫ ==========
def wrap_text(text: str, max_chars: int) -> list[str]:
    words = text.split()
    lines, current = [], ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current += (" " if current else "") + word
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def measure_block(draw, items, font, max_chars, line_h, item_gap):
    """Считает итоговую высоту, которую займёт текст."""
    total_h = 0
    for item in items:
        lines = wrap_text(item, max_chars)
        total_h += len(lines) * line_h + item_gap
    return total_h


def render_card(title: str, items: list[str], resolution_key: str = "hd") -> bytes:
    """Рисует ОДНУ картинку, автоматически подбирая размер шрифта."""
    res = RESOLUTIONS.get(resolution_key, RESOLUTIONS["hd"])
    W, H = res["w"], res["h"]

    scale = W / 1920
    margin = int(60 * scale)
    header_h = int(140 * scale)

    # Границы для автоподбора
    min_font = max(10, int(12 * scale))   # минимальный размер шрифта тела
    max_font = int(48 * scale)            # максимальный
    title_size = int(70 * scale)
    small_size = int(30 * scale)

    # Доступная высота под текст
    body_top = margin + header_h + int(60 * scale)
    body_bottom = H - int(120 * scale)
    available_h = body_bottom - body_top

    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype(FONT_PATH, title_size)
        font_small = ImageFont.truetype(FONT_PATH, small_size)
    except Exception as e:
        print(f"⚠️ Шрифт не загрузился: {e}")
        font_title = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # ----- АВТОПОДБОР РАЗМЕРА ШРИФТА -----
    chosen_font = None
    chosen_line_h = 0
    chosen_item_gap = 0
    chosen_max_chars = 0

    for size in range(max_font, min_font - 1, -2):
        try:
            font_body = ImageFont.truetype(FONT_PATH, size)
        except Exception:
            continue

        # Сколько символов влезет в строку при данном размере
        max_chars = int((W - 2 * margin - int(60 * scale)) / (size * 0.42))
        if max_chars < 10:
            continue

        line_h = int(size * 1.35)
        item_gap = int(size * 0.35)

        total_h = measure_block(draw, items, font_body, max_chars, line_h, item_gap)
        if total_h <= available_h:
            chosen_font = font_body
            chosen_line_h = line_h
            chosen_item_gap = item_gap
            chosen_max_chars = max_chars
            break

    # Если даже минимальный не влез — берём минимальный и обрезаем
    if chosen_font is None:
        chosen_font = ImageFont.truetype(FONT_PATH, min_font)
        chosen_line_h = int(min_font * 1.35)
        chosen_item_gap = int(min_font * 0.35)
        chosen_max_chars = int((W - 2 * margin - int(60 * scale)) / (min_font * 0.42))

    # ----- ШАПКА -----
    draw.rounded_rectangle(
        [(margin, margin), (W - margin, margin + header_h)],
        radius=int(20 * scale),
        fill=HEADER_COLOR,
    )
    title_text = title.upper()
    bbox = draw.textbbox((0, 0), title_text, font=font_title)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    title_x = margin + (W - 2 * margin - text_w) // 2
    title_y = margin + (header_h - text_h) // 2 - int(6 * scale)
    draw.text((title_x, title_y), title_text, font=font_title, fill=BG_COLOR)

    # ----- ТЕЛО -----
    y = body_top
    for item in items:
        lines = wrap_text(item, chosen_max_chars)
        for i, line in enumerate(lines):
            prefix = "• " if i == 0 else "   "
            draw.text(
                (margin + int(30 * scale), y),
                prefix + line,
                font=chosen_font,
                fill=TEXT_COLOR,
            )
            y += chosen_line_h
            if y > body_bottom:
                break
        y += chosen_item_gap
        if y > body_bottom:
            break

    # ----- ПОДПИСЬ -----
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
        "📖 *Как использовать:*\n"
        "1. Отправь /make\n"
        "2. Введи текст. Формат:\n"
        "```\n"
        "Заголовок: Основания для задержания\n"
        "1. Если лицо в розыске — Ст. 4.9.4.2.П.2\n"
        "2. При проникновении на объект — Ст. 4.9.4.2.П.4\n"
        "```\n"
        "3. Если текст длинный — отправь его частями, потом напиши `/done`\n"
        "4. Выбери разрешение — бот подберёт размер шрифта и пришлёт картинку.\n\n"
        f"📊 Максимум: {MAX_TOTAL_CHARS} символов. Всё влезет в одну картинку.",
        parse_mode="Markdown",
    )


@dp.message(Command("make"))
async def cmd_make(message: types.Message):
    user_data[message.from_user.id] = {"step": "awaiting_text", "text": ""}
    await message.answer(
        "📝 Отправь текст подсказки.\n\n"
        "Формат:\n"
        "```\n"
        "Заголовок: ...\n"
        "1. ...\n"
        "2. ...\n"
        "```\n\n"
        "Если текст длинный — отправляй частями, потом `/done`.",
        parse_mode="Markdown",
    )


@dp.message(Command("done"))
async def cmd_done(message: types.Message):
    uid = message.from_user.id
    state = user_data.get(uid, {})
    text = state.get("text", "").strip()

    if not text:
        await message.answer("❌ Ты ещё ничего не отправил. Используй /make чтобы начать.")
        return

    user_data[uid] = {"step": "awaiting_resolution", "text": text}
    await message.answer(
        f"📥 Принято {len(text)} символов.\n🎯 Выбери разрешение:",
        reply_markup=resolution_keyboard(),
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
            caption=f"✅ {title} · {len(text)} символов · {RESOLUTIONS[res_key]['label']}",
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

    text_part = (message.text or "").strip()
    if not text_part:
        return

    current = state.get("text", "")
    new_text = (current + "\n" + text_part) if current else text_part

    if len(new_text) > MAX_TOTAL_CHARS:
        await message.answer(
            f"⚠️ Превышен лимит {MAX_TOTAL_CHARS} символов. "
            f"Сейчас: {len(new_text)}. Напиши /done чтобы закончить."
        )
        return

    user_data[uid] = {"step": "awaiting_text", "text": new_text}

    if not current and len(new_text) < 1000 and "заголовок:" in new_text.lower():
        user_data[uid] = {"step": "awaiting_resolution", "text": new_text}
        await message.answer(
            f"📥 Принято {len(new_text)} символов.\n🎯 Выбери разрешение:",
            reply_markup=resolution_keyboard(),
        )
    else:
        await message.answer(
            f"➕ Добавлено. Всего: {len(new_text)} символов.\n"
            f"Отправь ещё или напиши /done."
        )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())