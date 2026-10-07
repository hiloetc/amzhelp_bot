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
    "uhd":  {"w": 3840, "h": 2160, "label": "🖥 3840×2160 (4K)"},
    "vert": {"w": 1080, "h": 1350, "label": "📱 1080×1350 (вертикально)"},
}

BG_COLOR = (13, 13, 13)
HEADER_COLOR = (255, 122, 0)
TEXT_COLOR = (255, 255, 255)
MUTED_COLOR = (150, 150, 150)
DIVIDER_COLOR = (60, 60, 60)

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


def balance_items_into_columns(items: list[str], num_cols: int) -> list[list[str]]:
    """Распределяет пункты по колонкам примерно поровну по количеству символов."""
    total_len = sum(len(it) + 1 for it in items)
    target = total_len / num_cols
    columns = [[] for _ in range(num_cols)]
    col_idx = 0
    current_len = 0
    for item in items:
        item_len = len(item) + 1
        # Если добавление переполнит колонку и есть куда переходить — переходим
        if current_len + item_len > target and col_idx < num_cols - 1 and columns[col_idx]:
            col_idx += 1
            current_len = 0
        columns[col_idx].append(item)
        current_len += item_len
    return columns


def calc_column_height(items: list[str], font, max_chars: int, line_h: int, item_gap: int) -> int:
    """Считает высоту одной колонки при заданном шрифте."""
    total = 0
    for item in items:
        lines = wrap_text(item, max_chars)
        total += len(lines) * line_h + item_gap
    return total


def render_card(title: str, items: list[str], resolution_key: str = "hd") -> bytes:
    """Рисует карточку с автоподбором шрифта и количества колонок."""
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

    # ----- ПОДБОР КОЛИЧЕСТВА КОЛОНОК И РАЗМЕРА ШРИФТА -----
    # Пробуем от 4 колонок к 1, и внутри каждой конфигурации — от большого шрифта к малому.
    best_config = None
    min_font = max(11, int(13 * scale))
    max_font = int(44 * scale)

    for num_cols in (4, 3, 2, 1):
        col_width = (W - 2 * margin - (num_cols - 1) * gap_between_cols) // num_cols
        columns = balance_items_into_columns(items, num_cols)

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

            # Считаем самую длинную колонку
            heights = [calc_column_height(col, font_body, max_chars, line_h, item_gap) for col in columns]
            max_col_h = max(heights) if heights else 0

            if max_col_h <= available_h:
                best_config = {
                    "num_cols": num_cols,
                    "font_body": font_body,
                    "size": size,
                    "columns": columns,
                    "max_chars": max_chars,
                    "line_h": line_h,
                    "item_gap": item_gap,
                    "col_width": col_width,
                }
                break
        if best_config:
            break

    # Если ничего не влезло — берём 4 колонки и минимальный шрифт (обрежется)
    if not best_config:
        num_cols = 4
        col_width = (W - 2 * margin - (num_cols - 1) * gap_between_cols) // num_cols
        columns = balance_items_into_columns(items, num_cols)
        font_body = ImageFont.truetype(FONT_PATH, min_font)
        best_config = {
            "num_cols": num_cols,
            "font_body": font_body,
            "size": min_font,
            "columns": columns,
            "max_chars": int(col_width / (min_font * 0.42)),
            "line_h": int(min_font * 1.32),
            "item_gap": int(min_font * 0.30),
            "col_width": col_width,
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
    col_width = best_config["col_width"]
    font_body = best_config["font_body"]
    max_chars = best_config["max_chars"]
    line_h = best_config["line_h"]
    item_gap = best_config["item_gap"]
    columns = best_config["columns"]
    num_cols = best_config["num_cols"]

    for col_idx, col_items in enumerate(columns):
        col_x = margin + col_idx * (col_width + gap_between_cols)
        y = body_top

        for item in col_items:
            lines = wrap_text(item, max_chars)
            for i, line in enumerate(lines):
                prefix = "• " if i == 0 else "   "
                draw.text(
                    (col_x, y),
                    prefix + line,
                    font=font_body,
                    fill=TEXT_COLOR,
                )
                y += line_h
                if y > body_bottom:
                    break
            y += item_gap
            if y > body_bottom:
                break

        # Разделительная линия между колонками
        if col_idx < num_cols - 1:
            line_x = col_x + col_width + gap_between_cols // 2
            draw.line(
                [(line_x, body_top), (line_x, body_bottom - int(20 * scale))],
                fill=DIVIDER_COLOR,
                width=max(1, int(2 * scale)),
            )

    # ----- ПОДПИСЬ -----
    info = f"AMAZING HUD · {len(items)} п. · {num_cols} кол. · {len(''.join(items))} симв."
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
        "3. Если текст длинный — отправь частями, потом `/done`\n"
        "4. Выбери разрешение — бот автоматически подберёт шрифт и количество колонок (1–4).\n\n"
        f"📊 Максимум: {MAX_TOTAL_CHARS} символов.",
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