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

MAX_COLUMNS = 4
MAX_CHARS_PER_COLUMN = 15000     # Подняли с 7000
MAX_TOTAL_CHARS = 40000          # Общий лимит на все столбцы

MIN_FONT_FLOOR = 8               # Абсолютный минимум шрифта (px)
ABS_MIN_FONT = 6                 # Ниже не опускаемся даже при переполнении


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


def render_card(title: str, columns: list[list[str]], resolution_key: str = "hd"):
    """
    Возвращает (bytes, actual_rendered_items).
    Если текст не влез даже при минимальном шрифте — сообщает об этом.
    """
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
    gap_between_cols = int(36 * scale)

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

    col_width = (W - 2 * margin - (num_cols - 1) * gap_between_cols) // num_cols

    # ----- ПОДБОР РАЗМЕРА ШРИФТА (до абс. минимума) -----
    min_font = max(ABS_MIN_FONT, int(MIN_FONT_FLOOR * scale))
    max_font = int(44 * scale)

    chosen = None
    for size in range(max_font, min_font - 1, -1):  # шаг 1 для точности
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
        # Даже минимум не влез — используем минимум и режем с предупреждением
        overflow = True
        font_body = ImageFont.truetype(FONT_PATH, min_font)
        chosen = {
            "font_body": font_body,
            "size": min_font,
            "max_chars": int(col_width / (min_font * 0.42)),
            "line_h": int(min_font * 1.30),
            "item_gap": int(min_font * 0.28),
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
    rendered_count = 0
    for col_idx, col_items in enumerate(active_columns):
        col_x = margin + col_idx * (col_width + gap_between_cols)
        y = body_top

        for item in col_items:
            lines = wrap_text(item, chosen["max_chars"])
            # Проверяем, влезет ли весь пункт целиком
            item_height = len(lines) * chosen["line_h"]
            if y + item_height > body_bottom:
                overflow = True
                break  # дальше не рисуем в этой колонке

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
                [(line_x, body_top), (line_x, body_bottom - int(20 * scale))],
                fill=DIVIDER_COLOR,
                width=max(1, int(2 * scale)),
            )

    # ----- ПОДПИСЬ -----
    total_items = sum(len(c) for c in active_columns)
    info = f"AMAZING HUD · {num_cols} столбц. · {rendered_count}/{total_items} п. · {chosen['size']}px"
    if overflow:
        info += " ⚠️"
    draw.text(
        (margin, H - int(65 * scale)),
        info,
        font=font_small,
        fill=MUTED_COLOR,
    )

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)

    return buf.read(), rendered_count, total_items, overflow


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
        "2. Введи заголовок\n"
        "3. Выбери столбец кнопкой (1–4) — и вставь текст\n"
        "4. Переключайся между столбцами, заполняй их\n"
        "5. Нажми «✅ Готово»\n"
        "6. Выбери разрешение\n\n"
        f"📊 Лимит: {MAX_CHARS_PER_COLUMN} символов на столбец, {MAX_TOTAL_CHARS} всего.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )


@dp.message(Command("make"))
async def cmd_make(message: types.Message):
    user_data[message.from_user.id] = make_state()
    await message.answer(
        "📝 Введи *заголовок* (одной строкой):\n"
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
        img_bytes, rendered, total, overflow = render_card(
            state["title"], state["columns"], res_key
        )
        photo = BufferedInputFile(img_bytes, filename="hud.png")

        caption = f"✅ {state['title']} · {rendered}/{total} строк · {RESOLUTIONS[res_key]['label']}"
        if overflow:
            caption += (
                f"\n⚠️ Не всё влезло на картинку ({total - rendered} строк обрезано). "
                f"Уменьши текст, раздели на несколько подсказок "
                f"или выбери разрешение побольше (4K)."
            )

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

    if state.get("step") == "awaiting_title":
        state["title"] = text[:80]
        state["step"] = "awaiting_text"
        state["active_col"] = 0
        await message.answer(
            f"✅ Заголовок: *{state['title']}*\n\n"
            f"Теперь выбери столбец кнопкой ниже и вставь текст.\n"
            f"Активен *Столбец 1*.",
            parse_mode="Markdown",
            reply_markup=columns_keyboard(),
        )
        return

    if state.get("step") == "awaiting_text":
        col = state["active_col"]
        current_len = sum(len(line) for line in state["columns"][col])

        if current_len + len(text) > MAX_CHARS_PER_COLUMN:
            await message.answer(
                f"⚠️ Столбец {col + 1} переполнен.\n"
                f"Сейчас: {current_len}, добавляешь: {len(text)}, "
                f"лимит: {MAX_CHARS_PER_COLUMN}.\n\n"
                f"Сократи текст, выбери другой столбец "
                f"или нажми «✅ Готово»."
            )
            return

        total_before = sum(sum(len(l) for l in c) for c in state["columns"])
        if total_before + len(text) > MAX_TOTAL_CHARS:
            await message.answer(
                f"⚠️ Общий лимит {MAX_TOTAL_CHARS} символов превышен. "
                f"Нажми «✅ Готово» и генерируй."
            )
            return

        # Добавляем построчно
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
            f"В столбце: {len(state['columns'][col])} строк, "
            f"{sum(len(l) for l in state['columns'][col])} символов.\n"
            f"Всего по всем: {total_lines} строк, {total_chars} символов.",
            parse_mode="Markdown",
        )
        return

    await message.answer("Нажми кнопку разрешения выше или начни заново /make.")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())