import asyncio
import os
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from PIL import Image, ImageDraw, ImageFont

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN не найден. Проверь .env или переменные Bothost")

# ========== НАСТРОЙКИ ==========
FONT_PATH = "fonts/PT-Sans-Narrow-Bold.ttf"

RESOLUTIONS = {
    "hd":   {"w": 1920, "h": 1080, "label": "🖥 1920×1080 (HD)"},
    "qhd":  {"w": 2560, "h": 1440, "label": "🖥 2560×1440 (QHD)"},
    "uhd":  {"w": 3840, "h": 2160, "label": "🖥 3840×2160 (4K)"},
    "vert": {"w": 1080, "h": 1350, "label": "📱 1080×1350 (вертикально)"},
}

BG_COLOR = (13, 13, 13)
HEADER_COLOR = (255, 122, 0)
TEXT_COLOR = (255, 255, 255)
MUTED_COLOR = (150, 150, 150)
DIVIDER_COLOR = (70, 70, 70)

MAX_COLUMNS = 4           # максимум столбцов
MAX_CHARS_PER_COLUMN = 7000  # лимит на один столбец
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


def calc_column_height(items: list[str], max_chars: int, line_h: int, item_gap: int) -> int:
    total = 0
    for item in items:
        lines = wrap_text(item, max_chars)
        total += len(lines) * line_h + item_gap
    return total


def render_card(title: str, columns: list[list[str]], resolution_key: str = "hd") -> bytes:
    """
    columns — список столбцов, каждый столбец это список строк (пунктов).
    Пустые столбцы ([]) игнорируются.
    """
    # Оставляем только непустые столбцы
    active_columns = [c for c in columns if c]
    num_cols = len(active_columns)
    if num_cols == 0:
        active_columns = [["(пусто)"]]
        num_cols = 1

    res = RESOLUTIONS.get(resolution_key, RESOLUTIONS["hd"])
    W, H = res["w"], res["h"]

    scale = W / 1920
    margin = int(50 * scale)
    header_h = int(130 * scale)
    gap_between_cols = int(40 * scale)

    title_size = int(66 * scale)
    small_size = int(28 * scale)

    body_top = margin + header_h + int(50 * scale)
    body_bottom = H - int(110 * scale)
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

    # ----- ПОДБОР РАЗМЕРА ШРИФТА -----
    min_font = max(10, int(12 * scale))
    max_font = int(44 * scale)

    col_width = (W - 2 * margin - (num_cols - 1) * gap_between_cols) // num_cols

    best = None
    for size in range(max_font, min_font - 1, -2):
        try:
            font_body = ImageFont.truetype(FONT_PATH, size)
        except Exception:
            continue

        max_chars = int(col_width / (size * 0.42))
        if max_chars < 8:
            continue

        line_h = int(size * 1.32)
        item_gap = int(size * 0.30)

        heights = [calc_column_height(col, max_chars, line_h, item_gap) for col in active_columns]
        max_col_h = max(heights) if heights else 0

        if max_col_h <= available_h:
            best = {
                "font_body": font_body,
                "size": size,
                "max_chars": max_chars,
                "line_h": line_h,
                "item_gap": item_gap,
            }
            break

    if not best:
        font_body = ImageFont.truetype(FONT_PATH, min_font)
        best = {
            "font_body": font_body,
            "size": min_font,
            "max_chars": int(col_width / (min_font * 0.42)),
            "line_h": int(min_font * 1.32),
            "item_gap": int(min_font * 0.30),
        }

    # ----- ШАПКА -----
    draw.rounded_rectangle(
        [(margin, margin), (W - margin, margin + header_h)],
        radius=int(18 * scale),
        fill=HEADER_COLOR,
    )
    title_text = title.upper()
    bbox = draw.textbbox((0, 0), title_text, font=font_title)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    title_x = margin + (W - 2 * margin - text_w) // 2
    title_y = margin + (header_h - text_h) // 2 - int(6 * scale)
    draw.text((title_x, title_y), title_text, font=font_title, fill=BG_COLOR)

    # ----- КОЛОНКИ -----
    for col_idx, col_items in enumerate(active_columns):
        col_x = margin + col_idx * (col_width + gap_between_cols)
        y = body_top

        for item in col_items:
            lines = wrap_text(item, best["max_chars"])
            for i, line in enumerate(lines):
                prefix = "• " if i == 0 else "   "
                draw.text(
                    (col_x, y),
                    prefix + line,
                    font=best["font_body"],
                    fill=TEXT_COLOR,
                )
                y += best["line_h"]
                if y > body_bottom:
                    break
            y += best["item_gap"]
            if y > body_bottom:
                break

        if col_idx < num_cols - 1:
            line_x = col_x + col_width + gap_between_cols // 2
            draw.line(
                [(line_x, body_top), (line_x, body_bottom - int(20 * scale))],
                fill=DIVIDER_COLOR,
                width=max(1, int(2 * scale)),
            )

    # ----- ПОДПИСЬ -----
    total_items = sum(len(c) for c in active_columns)
    info = f"AMAZING HUD · {num_cols} столбц. · {total_items} п. · {best['size']}px"
    draw.text(
        (margin, H - int(65 * scale)),
        info,
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

# user_id -> {"step": "...", "title": "...", "columns": [[], [], [], []], "active_col": 0}
user_data = {}


def columns_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура выбора столбца + действия."""
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


def make_state(title: str = "ПОДСКАЗКА"):
    return {
        "step": "awaiting_title",
        "title": title,
        "columns": [[], [], [], []],
        "active_col": 0,
    }


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я генерирую подсказки в стиле AMAZING HUD.\n\n"
        "📖 *Как использовать:*\n"
        "1. Отправь /make\n"
        "2. Введи заголовок (одной строкой)\n"
        "3. Выбери столбец кнопкой (1–4) — и вставь в него текст\n"
        "4. Переключайся между столбцами и заполняй их\n"
        "5. Нажми «✅ Готово»\n"
        "6. Выбери разрешение — получишь картинку\n\n"
        "Можно использовать 1, 2, 3 или 4 столбца — пустые не отобразятся.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )


@dp.message(Command("make"))
async def cmd_make(message: types.Message):
    user_data[message.from_user.id] = make_state()
    await message.answer(
        "📝 Введи *заголовок* подсказки (одной строкой):\n"
        "Например: `Основания для задержания`",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )


@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message):
    user_data.pop(message.from_user.id, None)
    await message.answer("❌ Отменено.", reply_markup=ReplyKeyboardRemove())


@dp.message(lambda m: m.text == "❌ Отмена")
async def on_cancel_btn(message: types.Message):
    user_data.pop(message.from_user.id, None)
    await message.answer("❌ Отменено.", reply_markup=ReplyKeyboardRemove())


@dp.message(lambda m: m.text and m.text.startswith("1️⃣ Столбец"))
@dp.message(lambda m: m.text and m.text.startswith("2️⃣ Столбец"))
@dp.message(lambda m: m.text and m.text.startswith("3️⃣ Столбец"))
@dp.message(lambda m: m.text and m.text.startswith("4️⃣ Столбец"))
async def on_select_column(message: types.Message):
    uid = message.from_user.id
    state = user_data.get(uid)
    if not state or state.get("step") != "awaiting_text":
        await message.answer("Сначала отправь /make")
        return

    # "1️⃣ Столбец 1" -> берём первую цифру
    col_num = int(message.text.strip()[0]) - 1
    state["active_col"] = col_num

    filled = len(state["columns"][col_num])
    await message.answer(
        f"✏️ Активен *Столбец {col_num + 1}*. Вставь текст.\n"
        f"Сейчас в нём: {filled} строк.",
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
    await message.answer(
        f"✅ Заполнено столбцов: {len(filled)} ({', '.join(map(str, filled))}).\n"
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
        img_bytes = render_card(state["title"], state["columns"], res_key)
        photo = BufferedInputFile(img_bytes, filename="hud.png")
        total = sum(len(c) for c in state["columns"])
        await callback.message.answer_photo(
            photo,
            caption=f"✅ {state['title']} · {total} строк · {RESOLUTIONS[res_key]['label']}",
        )
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

    # Шаг 1: получение заголовка
    if state.get("step") == "awaiting_title":
        state["title"] = text[:80]  # ограничим длину заголовка
        state["step"] = "awaiting_text"
        state["active_col"] = 0
        await message.answer(
            f"✅ Заголовок: *{state['title']}*\n\n"
            f"Теперь выбери столбец кнопкой ниже и вставь в него текст.\n"
            f"Активен *Столбец 1* по умолчанию.",
            parse_mode="Markdown",
            reply_markup=columns_keyboard(),
        )
        return

    # Шаг 2: получение текста в активный столбец
    if state.get("step") == "awaiting_text":
        col = state["active_col"]
        current_len = sum(len(line) for line in state["columns"][col])
        if current_len + len(text) > MAX_CHARS_PER_COLUMN:
            await message.answer(
                f"⚠️ Столбец {col + 1} переполнен "
                f"({current_len + len(text)} / {MAX_CHARS_PER_COLUMN}).\n"
                f"Выбери другой столбец или нажми «✅ Готово»."
            )
            return

        # Разбиваем по строкам, каждую строку — отдельный пункт
        for line in text.split("\n"):
            line = line.strip()
            if line:
                state["columns"][col].append(line)

        total = sum(len(c) for c in state["columns"])
        await message.answer(
            f"➕ Добавлено в *Столбец {col + 1}*. "
            f"Всего строк: {len(state['columns'][col])}.\n"
            f"Всего во всех столбцах: {total}.",
            parse_mode="Markdown",
        )
        return

    # На этапе awaiting_resolution тексты не принимаем
    await message.answer("Нажми кнопку разрешения выше или начни заново /make.")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())