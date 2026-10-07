import asyncio
import os
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from PIL import Image, ImageDraw, ImageFont

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN не найден. Проверь .env или переменные Bothost")

# ========== НАСТРОЙКИ ==========
FONT_PATH = "fonts/PT-Sans-Narrow-Bold.ttf"

# ⚠️ ЗАМЕНИ на username своего бота
BOT_USERNAME = "@amzhelp_bot"

RESOLUTIONS = {
    "hd":   {"w": 1920, "h": 1080, "label": "🖥 1920×1080 (HD)"},
    "qhd":  {"w": 2560, "h": 1440, "label": "🖥 2560×1440 (QHD)"},
    "uhd":  {"w": 3840, "h": 2160, "label": "🖥 3840×2160 (4K)"},
    "vert": {"w": 1080, "h": 1350, "label": "📱 1080×1350 (вертикально)"},
}

BG_COLOR = (13, 13, 13)
TEXT_COLOR = (255, 255, 255)
DIVIDER_COLOR = (55, 55, 55)

# Рекламная плашка
AD_BG_COLOR = (255, 122, 0)
AD_TEXT_COLOR = (13, 13, 13)

MAX_CHARS_PER_COLUMN = 15000
MAX_TOTAL_CHARS = 40000

MIN_FONT_FLOOR = 8
ABS_MIN_FONT = 6

# Отступы
EDGE_MARGIN = 10
BOTTOM_RESERVE = 70   # резерв снизу под плашку


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


def calc_column_height(items: list[str], max_chars: int, line_h: int, item_gap: int) -> int:
    total = 0
    for item in items:
        lines = wrap_text(item, max_chars)
        total += len(lines) * line_h + item_gap
    return total


def draw_ad_block(draw, W, H, scale: float):
    """Маленькая плашка в правом нижнем углу: made with @username."""
    try:
        font_ad = ImageFont.truetype(FONT_PATH, int(18 * scale))
    except Exception:
        font_ad = ImageFont.load_default()

    text = f"made with {BOT_USERNAME}"
    pad_x = int(12 * scale)
    pad_y = int(8 * scale)

    bbox = draw.textbbox((0, 0), text, font=font_ad)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    box_w = text_w + pad_x * 2
    box_h = text_h + pad_y * 2

    box_x2 = W - EDGE_MARGIN
    box_x1 = box_x2 - box_w
    box_y2 = H - EDGE_MARGIN
    box_y1 = box_y2 - box_h

    # Лёгкая тень
    shadow = int(2 * scale)
    draw.rounded_rectangle(
        [(box_x1 + shadow, box_y1 + shadow), (box_x2 + shadow, box_y2 + shadow)],
        radius=int(6 * scale),
        fill=(0, 0, 0),
    )
    # Оранжевая плашка
    draw.rounded_rectangle(
        [(box_x1, box_y1), (box_x2, box_y2)],
        radius=int(6 * scale),
        fill=AD_BG_COLOR,
    )
    # Текст
    draw.text(
        (box_x1 + pad_x, box_y1 + pad_y - int(2 * scale)),
        text,
        font=font_ad,
        fill=AD_TEXT_COLOR,
    )


def render_card(columns: list[list[str]], resolution_key: str = "hd"):
    """Рисует карточку. Без шапки и подписи. Плашка — в правом нижнем углу."""
    active_columns = [c for c in columns if c]
    num_cols = len(active_columns)
    if num_cols == 0:
        active_columns = [["(пусто)"]]
        num_cols = 1

    res = RESOLUTIONS.get(resolution_key, RESOLUTIONS["hd"])
    W, H = res["w"], res["h"]
    scale = W / 1920

    margin = EDGE_MARGIN
    gap_between_cols = int(30 * scale)

    body_top = margin
    body_bottom = H - margin - int(BOTTOM_RESERVE * scale)
    available_h = body_bottom - body_top

    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    col_width = (W - 2 * margin - (num_cols - 1) * gap_between_cols) // num_cols

    # ----- ПОДБОР РАЗМЕРА ШРИФТА -----
    min_font = max(ABS_MIN_FONT, int(MIN_FONT_FLOOR * scale))
    max_font = int(44 * scale)

    chosen = None
    for size in range(max_font, min_font - 1, -1):
        try:
            font_body = ImageFont.truetype(FONT_PATH, size)
        except Exception:
            continue

        max_chars = int(col_width / (size * 0.42))
        if max_chars < 6:
            continue

        line_h = int(size * 1.30)
        item_gap = int(size * 0.28)

        heights = [calc_column_height(col, max_chars, line_h, item_gap) for col in active_columns]
        max_col_h = max(heights) if heights else 0

        if max_col_h <= available_h:
            chosen = {
                "font_body": font_body,
                "size": size,
                "max_chars": max_chars,
                "line_h": line_h,
                "item_gap": item_gap,
            }
            break

    overflow = False
    if not chosen:
        overflow = True
        font_body = ImageFont.truetype(FONT_PATH, min_font)
        chosen = {
            "font_body": font_body,
            "size": min_font,
            "max_chars": int(col_width / (min_font * 0.42)),
            "line_h": int(min_font * 1.30),
            "item_gap": int(min_font * 0.28),
        }

    # ----- КОЛОНКИ -----
    rendered_count = 0
    for col_idx, col_items in enumerate(active_columns):
        col_x = margin + col_idx * (col_width + gap_between_cols)
        y = body_top

        for item in col_items:
            lines = wrap_text(item, chosen["max_chars"])
            item_height = len(lines) * chosen["line_h"]
            if y + item_height > body_bottom:
                overflow = True
                break

            for i, line in enumerate(lines):
                prefix = "• " if i == 0 else "   "
                draw.text(
                    (col_x, y),
                    prefix + line,
                    font=chosen["font_body"],
                    fill=TEXT_COLOR,
                )
                y += chosen["line_h"]
            y += chosen["item_gap"]
            rendered_count += 1

        if col_idx < num_cols - 1:
            line_x = col_x + col_width + gap_between_cols // 2
            draw.line(
                [(line_x, body_top), (line_x, body_bottom)],
                fill=DIVIDER_COLOR,
                width=max(1, int(2 * scale)),
            )

    # ----- ПЛАШКА -----
    draw_ad_block(draw, W, H, scale)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)

    return buf.read(), rendered_count, sum(len(c) for c in active_columns), overflow


# ========== БОТ ==========
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

user_data = {}


def columns_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text="1️⃣ Столбец 1")
    kb.button(text="2️⃣ Столбец 2")
    kb.button(text="3️⃣ Столбец 3")
    kb.button(text="4️⃣ Столбец 4")
    kb.button(text="✅ Готово")
    kb.button(text="🗑 Очистить столбец")
    kb.button(text="❌ Отмена")
    kb.adjust(2, 2, 1, 2)
    return kb.as_markup(resize_keyboard=True)


def resolutions_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, data in RESOLUTIONS.items():
        kb.button(text=data["label"], callback_data=f"res:{key}")
    kb.adjust(1)
    return kb.as_markup()


def make_state():
    return {
        "step": "awaiting_text",
        "columns": [[], [], [], []],
        "active_col": 0,
    }


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я генерирую подсказки в стиле AMAZING HUD.\n\n"
        "📖 *Как использовать:*\n"
        "1. Отправь /make\n"
        "2. Выбери столбец (1–4) и вставь текст\n"
        "3. Переключайся между столбцами, заполняй их\n"
        "4. Нажми «✅ Готово»\n"
        "5. Выбери разрешение",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )


@dp.message(Command("make"))
async def cmd_make(message: types.Message):
    user_data[message.from_user.id] = make_state()
    await message.answer(
        "📝 Выбери столбец кнопкой ниже и вставь текст.\n"
        "Активен *Столбец 1* по умолчанию.",
        parse_mode="Markdown",
        reply_markup=columns_keyboard(),
    )


@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message):
    user_data.pop(message.from_user.id, None)
    await message.answer("❌ Отменено.", reply_markup=ReplyKeyboardRemove())


@dp.message(lambda m: m.text == "❌ Отмена")
async def on_cancel_btn(message: types.Message):
    user_data.pop(message.from_user.id, None)
    await message.answer("❌ Отменено.", reply_markup=ReplyKeyboardRemove())


@dp.message(lambda m: m.text and m.text[0] in "1234" and "Столбец" in m.text)
async def on_select_column(message: types.Message):
    uid = message.from_user.id
    state = user_data.get(uid)
    if not state or state.get("step") != "awaiting_text":
        await message.answer("Сначала отправь /make")
        return

    try:
        col_num = int(message.text.strip()[0]) - 1
    except (ValueError, IndexError):
        await message.answer("Не понял, какой столбец. Используй кнопки.")
        return

    state["active_col"] = col_num
    filled = len(state["columns"][col_num])
    chars = sum(len(l) for l in state["columns"][col_num])
    await message.answer(
        f"✏️ Активен *Столбец {col_num + 1}*. Вставь текст.\n"
        f"Сейчас: {filled} строк, {chars} символов.",
        parse_mode="Markdown",
    )


@dp.message(lambda m: m.text == "🗑 Очистить столбец")
async def on_clear_column(message: types.Message):
    uid = message.from_user.id
    state = user_data.get(uid)
    if not state or state.get("step") != "awaiting_text":
        await message.answer("Сначала отправь /make")
        return
    col_num = state["active_col"]
    state["columns"][col_num] = []
    await message.answer(f"🗑 Столбец {col_num + 1} очищен.")


@dp.message(lambda m: m.text == "✅ Готово")
async def on_done_btn(message: types.Message):
    uid = message.from_user.id
    state = user_data.get(uid)
    if not state or state.get("step") != "awaiting_text":
        await message.answer("Сначала отправь /make")
        return

    if not any(state["columns"]):
        await message.answer("❌ Все столбцы пусты. Заполни хотя бы один.")
        return

    state["step"] = "awaiting_resolution"
    filled = [i + 1 for i, c in enumerate(state["columns"]) if c]
    total = sum(len(c) for c in state["columns"])
    chars = sum(sum(len(l) for l in c) for c in state["columns"] if c)
    await message.answer(
        f"✅ Заполнено столбцов: {len(filled)} ({', '.join(map(str, filled))}).\n"
        f"Всего пунктов: {total}, символов: {chars}.\n"
        f"🎯 Выбери разрешение:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("👇", reply_markup=resolutions_keyboard())


@dp.callback_query(lambda c: c.data and c.data.startswith("res:"))
async def on_resolution(callback: types.CallbackQuery):
    uid = callback.from_user.id
    state = user_data.get(uid)
    if not state or state.get("step") != "awaiting_resolution":
        await callback.answer("Сначала отправь /make и заполни столбцы", show_alert=True)
        return

    res_key = callback.data.split(":")[1]
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("🎨 Генерирую картинку...")

    try:
        img_bytes, rendered, total, overflow = render_card(state["columns"], res_key)
        photo = BufferedInputFile(img_bytes, filename="hud.png")

        caption = f"✅ {rendered}/{total} строк · {RESOLUTIONS[res_key]['label']}"
        if overflow:
            caption += f"\n⚠️ {total - rendered} строк не влезло — выбери 4K."

        await callback.message.answer_photo(photo, caption=caption)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")

    user_data.pop(uid, None)
    await callback.answer()


@dp.message()
async def handle_text(message: types.Message):
    uid = message.from_user.id
    state = user_data.get(uid)

    if not state:
        await message.answer("Используй /make чтобы начать.")
        return

    text = (message.text or "").strip()
    if not text:
        return

    if state.get("step") == "awaiting_text":
        col = state["active_col"]
        current_len = sum(len(line) for line in state["columns"][col])

        if current_len + len(text) > MAX_CHARS_PER_COLUMN:
            await message.answer(
                f"⚠️ Столбец {col + 1} переполнен. Сократи текст или нажми «✅ Готово»."
            )
            return

        total_before = sum(sum(len(l) for l in c) for c in state["columns"])
        if total_before + len(text) > MAX_TOTAL_CHARS:
            await message.answer(
                f"⚠️ Общий лимит {MAX_TOTAL_CHARS} символов превышен. Нажми «✅ Готово»."
            )
            return

        added = 0
        for line in text.split("\n"):
            line = line.strip()
            if line:
                state["columns"][col].append(line)
                added += 1

        total_lines = sum(len(c) for c in state["columns"])
        total_chars = sum(sum(len(l) for l in c) for c in state["columns"])
        await message.answer(
            f"➕ Добавлено *{added}* строк в Столбец {col + 1}.\n"
            f"Всего: {total_lines} строк, {total_chars} символов.",
            parse_mode="Markdown",
        )
        return

    await message.answer("Нажми кнопку разрешения выше или начни заново /make.")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())