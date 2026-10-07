import asyncio
import os
import hashlib
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

import aiohttp
import catalog

BOT_TOKEN = os.getenv("BOT_TOKEN")
VT_API_KEY = os.getenv("VIRUSTOTAL_API_KEY")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN не найден")
if not VT_API_KEY:
    raise SystemExit("❌ VIRUSTOTAL_API_KEY не найден")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
catalog.init_db()

CATEGORIES = {
    "fps": "🚀 FPS-буст",
    "gos": "🚔 Для госников",
    "capt": "🏆 Для каптов",
    "crim": "💰 Для криминала",
    "ui": "🎨 UI / интерфейс",
    "other": "📦 Другое",
}


# ========== VIRUSTOTAL (без изменений) ==========
VT_API_URL = "https://www.virustotal.com/api/v3/files/{}"


async def check_file_hash(sha256: str) -> dict:
    headers = {"x-apikey": VT_API_KEY}
    url = VT_API_URL.format(sha256)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            elif resp.status == 404:
                return {"error": "not_found"}
            else:
                return {"error": resp.status, "message": (await resp.text())[:200]}


def format_vt_report(result: dict, sha256: str) -> str:
    attrs = result["data"]["attributes"]
    stats = attrs.get("last_analysis_stats", {})
    malicious = stats.get("malicious", 0)
    suspicious = stats.get("suspicious", 0)
    undetected = stats.get("undetected", 0)
    harmless = stats.get("harmless", 0)
    total = malicious + suspicious + undetected + harmless

    if malicious >= 5:
        verdict = "🔴 ОПАСНО"
    elif malicious >= 1:
        verdict = "🟠 ПОДОЗРИТЕЛЬНО"
    else:
        verdict = "🟢 ЧИСТО"

    threats = []
    for engine, data in attrs.get("last_analysis_results", {}).items():
        if data.get("category") == "malicious":
            threats.append(f"• {engine}: {data.get('result', '?')}")

    threat_text = "\n".join(threats[:5]) if threats else "Угроз не обнаружено"

    return (
        f"{verdict}\n\n"
        f"📊 {malicious}/{total} антивирусов нашли угрозы\n"
        f"🔎 {threat_text}\n\n"
        f"🔗 [Полный отчёт](https://www.virustotal.com/gui/file/{sha256})"
    )


# ========== КЛАВИАТУРЫ КАТАЛОГА ==========
def categories_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, label in CATEGORIES.items():
        kb.button(text=label, callback_data=f"cat:{key}")
    kb.adjust(2)
    return kb.as_markup()


def build_list_keyboard(builds: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for b in builds:
        rating = b.get("rating") or 0
        votes = b.get("votes") or 0
        stars = "⭐" * round(rating) if votes else ""
        kb.button(text=f"{stars} {b['title'][:35]}", callback_data=f"view:{b['id']}")
    kb.button(text="⬅️ Назад", callback_data="cat:back")
    kb.adjust(1)
    return kb.as_markup()


def build_card_keyboard(build_id: int, link: str = "", sha256: str = "") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if link:
        kb.button(text="📥 Скачать", url=link)
    if sha256:
        kb.button(text="🛡 VirusTotal", url=f"https://www.virustotal.com/gui/file/{sha256}")
    kb.button(text="⭐ Оценить", callback_data=f"rate:{build_id}")
    kb.button(text="⬅️ К каталогу", callback_data="cat:back")
    kb.adjust(1)
    return kb.as_markup()


def rating_keyboard(build_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for score in range(1, 6):
        kb.button(text="⭐" * score, callback_data=f"score:{build_id}:{score}")
    kb.adjust(5)
    return kb.as_markup()


def render_build_card(build: dict) -> str:
    rating = build.get("rating") or 0
    votes = build.get("votes") or 0
    stars = "⭐" * round(rating) if votes > 0 else "нет оценок"

    text = (
        f"📦 **{build['title']}**\n\n"
        f"📁 {CATEGORIES.get(build['category'], build['category'])}\n"
        f"👤 {build.get('author') or 'не указан'}\n"
        f"⭐ {stars} ({rating:.1f}/5 · {votes} голосов)\n"
    )
    if build.get("vt_status"):
        text += f"🛡 VT: {build['vt_status']}\n"
    if build.get("description"):
        text += f"\n📝 {build['description']}\n"
    return text


# ========== КЛАВИАТУРЫ АВТОРОВ ==========
def authors_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    authors = catalog.get_all_authors(limit=10)
    for a in authors:
        verified = "✅ " if a.get("verified") else ""
        kb.button(
            text=f"{verified}{a['name']} ({a.get('builds_count', 0)})",
            callback_data=f"author:{a['id']}"
        )
    kb.adjust(1)
    return kb.as_markup()


def author_card_keyboard(author_id: int, telegram: str = "") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if telegram:
        tg = telegram if telegram.startswith("@") else "@" + telegram
        kb.button(text=f"📩 {tg}", url=f"https://t.me/{tg.lstrip('@')}")
    kb.button(text="📦 Сборки автора", callback_data=f"author_builds:{author_id}")
    kb.button(text="⬅️ К авторам", callback_data="authors:list")
    kb.adjust(1)
    return kb.as_markup()


def render_author_card(author: dict) -> str:
    verified = "✅ Проверенный" if author.get("verified") else "⚪ Обычный"
    trust = author.get("trust_score") or 0
    builds = author.get("builds_count") or 0

    text = (
        f"👤 **{author['name']}**\n\n"
        f"📌 Статус: {verified}\n"
        f"⭐ Доверие: {trust:.1f}/5\n"
        f"📦 Сборок: {builds}\n"
    )
    if author.get("telegram"):
        text += f"📩 Telegram: {author['telegram']}\n"
    if author.get("description"):
        text += f"\n📝 {author['description']}\n"
    return text


# ========== КОНСТРУКТОР: клавиатуры ==========
def constructor_categories_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, label in catalog.COMPONENT_CATEGORIES.items():
        kb.button(text=label, callback_data=f"ccat:{key}")
    kb.button(text="✅ Собрать инструкцию", callback_data="cbuild")
    kb.button(text="🗑 Очистить", callback_data="cclear")
    kb.adjust(2, 2, 2, 1, 1)
    return kb.as_markup()


def components_keyboard(category: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    comps = catalog.get_components(category=category)
    for c in comps:
        kb.button(text=f"➕ {c['name']}", callback_data=f"cadd:{c['id']}")
    kb.button(text="⬅️ Назад", callback_data="cback")
    kb.adjust(1)
    return kb.as_markup()


# ========== ХЕНДЛЕРЫ КОМАНД ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🛡 **Бот-Хаб для AMAZING ONLINE**\n\n"
        "🔍 /scan — проверить файл на вирусы\n"
        "📦 /builds — каталог сборок\n"
        "👤 /authors — рейтинг авторов\n"
        "🛠 /constructor — собрать свою сборку\n"
        "➕ /addbuild — добавить сборку (админ)\n"
        "❓ /help — помощь",
        parse_mode="Markdown",
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 **Команды:**\n\n"
        "/scan — проверка файла через VirusTotal\n"
        "/builds — каталог сборок\n"
        "/authors — авторы и их рейтинг\n"
        "/constructor — конструктор своей сборки\n"
        "/addbuild — добавить сборку (админ)\n"
        "/addauthor — добавить автора (админ)\n"
        "/addcomponent — добавить компонент (админ)",
        parse_mode="Markdown",
    )


@dp.message(Command("scan"))
async def cmd_scan(message: types.Message):
    await message.answer("📎 Отправь файл (до 32 МБ) или SHA256-хеш (64 символа).")


@dp.message(Command("builds"))
async def cmd_builds(message: types.Message):
    total = catalog.count_builds()
    if total == 0:
        await message.answer("📭 Каталог пуст. Добавь сборки через /addbuild.")
        return
    await message.answer(
        f"📦 Всего сборок: {total}\n\nВыбери категорию:",
        reply_markup=categories_keyboard(),
    )


@dp.message(Command("authors"))
async def cmd_authors(message: types.Message):
    authors = catalog.get_all_authors(limit=10)
    if not authors:
        await message.answer("📭 Авторов пока нет. Добавь через /addauthor.")
        return
    await message.answer(
        "👤 **Рейтинг авторов**\n\n"
        "✅ — проверенные, ⭐ — рейтинг доверия.\n\nВыбери автора:",
        parse_mode="Markdown",
        reply_markup=authors_keyboard(),
    )


@dp.message(Command("constructor"))
async def cmd_constructor(message: types.Message):
    comps = catalog.get_components()
    if not comps:
        await message.answer("📭 Компонентов нет. Добавь через /addcomponent.")
        return
    await message.answer(
        "🛠 **Конструктор сборки**\n\n"
        "Выбери категорию компонентов. Когда добавишь всё нужное — нажми «✅ Собрать инструкцию».",
        reply_markup=constructor_categories_keyboard(),
    )


@dp.message(Command("addbuild"))
async def cmd_addbuild(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Только для админов.")
        return
    await message.answer(
        "➕ **Добавление сборки**\n\n"
        "Формат:\n"
        "```\n"
        "title: Название\n"
        "category: fps|gos|capt|crim|ui|other\n"
        "author: Автор\n"
        "link: https://...\n"
        "sha256: опционально\n"
        "description: Описание\n"
        "```",
        parse_mode="Markdown",
    )


@dp.message(Command("addauthor"))
async def cmd_addauthor(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Только для админов.")
        return
    await message.answer(
        "➕ **Добавление автора**\n\n"
        "Формат:\n"
        "```\n"
        "name: Имя автора\n"
        "telegram: @username\n"
        "description: Описание\n"
        "verified: 1 (или 0)\n"
        "```",
        parse_mode="Markdown",
    )


@dp.message(Command("addcomponent"))
async def cmd_addcomponent(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Только для админов.")
        return
    cats = ", ".join(catalog.COMPONENT_CATEGORIES.keys())
    await message.answer(
        "➕ **Добавление компонента**\n\n"
        f"Категории: `{cats}`\n\n"
        "Формат:\n"
        "```\n"
        "name: Название\n"
        "category: fps_boost\n"
        "description: Описание\n"
        "link: https://...\n"
        "sha256: опционально\n"
        "author: Автор\n"
        "```",
        parse_mode="Markdown",
    )


# ========== CALLBACK: КАТАЛОГ ==========
@dp.callback_query(F.data.startswith("cat:"))
async def on_category(callback: CallbackQuery):
    cat = callback.data.split(":")[1]

    if cat == "back":
        await callback.message.edit_text(
            "📦 Выбери категорию:",
            reply_markup=categories_keyboard(),
        )
        await callback.answer()
        return

    builds = catalog.get_builds(category=cat, limit=5)
    if not builds:
        await callback.answer("В этой категории пусто", show_alert=True)
        return

    await callback.message.edit_text(
        f"📁 **{CATEGORIES.get(cat)}** — {len(builds)} шт.\n\nВыбери:",
        parse_mode="Markdown",
        reply_markup=build_list_keyboard(builds),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("view:"))
async def on_view_build(callback: CallbackQuery):
    build_id = int(callback.data.split(":")[1])
    build = catalog.get_build(build_id)
    if not build:
        await callback.answer("Не найдено", show_alert=True)
        return
    await callback.message.edit_text(
        render_build_card(build),
        parse_mode="Markdown",
        reply_markup=build_card_keyboard(build_id, build.get("link", ""), build.get("sha256", "")),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("rate:"))
async def on_rate(callback: CallbackQuery):
    build_id = int(callback.data.split(":")[1])
    await callback.message.edit_reply_markup(reply_markup=rating_keyboard(build_id))
    await callback.answer("Поставь оценку:")


@dp.callback_query(F.data.startswith("score:"))
async def on_score(callback: CallbackQuery):
    _, build_id, score = callback.data.split(":")
    build_id, score = int(build_id), int(score)
    catalog.rate_build(build_id, callback.from_user.id, score)

    build = catalog.get_build(build_id)
    if build and build.get("author"):
        catalog.update_author_stats(build["author"])

    await callback.answer(f"Спасибо! {score} ⭐")
    await callback.message.edit_text(
        render_build_card(build),
        parse_mode="Markdown",
        reply_markup=build_card_keyboard(build_id, build.get("link", ""), build.get("sha256", "")),
    )


# ========== CALLBACK: АВТОРЫ ==========
@dp.callback_query(F.data == "authors:list")
async def on_authors_list(callback: CallbackQuery):
    await callback.message.edit_text(
        "👤 **Рейтинг авторов**\n\nВыбери автора:",
        parse_mode="Markdown",
        reply_markup=authors_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("author:"))
async def on_author_view(callback: CallbackQuery):
    author_id = int(callback.data.split(":")[1])
    author = catalog.get_author(author_id)
    if not author:
        await callback.answer("Автор не найден", show_alert=True)
        return
    await callback.message.edit_text(
        render_author_card(author),
        parse_mode="Markdown",
        reply_markup=author_card_keyboard(author_id, author.get("telegram", "")),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("author_builds:"))
async def on_author_builds(callback: CallbackQuery):
    author_id = int(callback.data.split(":")[1])
    author = catalog.get_author(author_id)
    if not author:
        await callback.answer("Автор не найден", show_alert=True)
        return

    conn_builds = []
    all_builds = catalog.get_builds(limit=100)
    for b in all_builds:
        if b.get("author") == author["name"]:
            conn_builds.append(b)

    if not conn_builds:
        await callback.answer("У автора нет сборок", show_alert=True)
        return

    await callback.message.edit_text(
        f"📦 Сборки автора **{author['name']}**:",
        parse_mode="Markdown",
        reply_markup=build_list_keyboard(conn_builds),
    )
    await callback.answer()


# ========== CALLBACK: КОНСТРУКТОР ==========
# Хранилище выбранных компонентов в памяти
user_cart = {}  # user_id -> set(component_ids)


@dp.callback_query(F.data.startswith("ccat:"))
async def on_ccat(callback: CallbackQuery):
    cat = callback.data.split(":")[1]
    comps = catalog.get_components(category=cat)
    if not comps:
        await callback.answer("В этой категории пусто", show_alert=True)
        return
    await callback.message.edit_text(
        f"📂 **{catalog.COMPONENT_CATEGORIES.get(cat)}**\n\nВыбери компоненты:",
        parse_mode="Markdown",
        reply_markup=components_keyboard(cat),
    )
    await callback.answer()


@dp.callback_query(F.data == "cback")
async def on_cback(callback: CallbackQuery):
    await callback.message.edit_text(
        "🛠 **Конструктор сборки**\n\nВыбери категорию:",
        reply_markup=constructor_categories_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("cadd:"))
async def on_cadd(callback: CallbackQuery):
    comp_id = int(callback.data.split(":")[1])
    uid = callback.from_user.id
    if uid not in user_cart:
        user_cart[uid] = set()
    user_cart[uid].add(comp_id)

    comp = catalog.get_component(comp_id)
    await callback.answer(f"✅ Добавлено: {comp['name']}")


@dp.callback_query(F.data == "cclear")
async def on_cclear(callback: CallbackQuery):
    user_cart[callback.from_user.id] = set()
    await callback.answer("🗑 Очищено")
    await callback.message.edit_text(
        "🛠 Конструктор пуст. Выбери категорию:",
        reply_markup=constructor_categories_keyboard(),
    )


@dp.callback_query(F.data == "cbuild")
async def on_cbuild(callback: CallbackQuery):
    uid = callback.from_user.id
    cart = user_cart.get(uid, set())
    if not cart:
        await callback.answer("Сначала добавь компоненты", show_alert=True)
        return

    # Собираем данные по выбранным компонентам
    components = []
    for cid in cart:
        c = catalog.get_component(cid)
        if c:
            components.append(c)

    if not components:
        await callback.answer("Компоненты не найдены", show_alert=True)
        return

    # Группируем по категориям
    by_cat = {}
    for c in components:
        by_cat.setdefault(c["category"], []).append(c)

    text = "🛠 **Твоя сборка**\n\n"
    for cat, items in by_cat.items():
        text += f"**{catalog.COMPONENT_CATEGORIES.get(cat, cat)}**\n"
        for c in items:
            text += f"• {c['name']}"
            if c.get("size_kb"):
                text += f" ({c['size_kb']} KB)"
            text += "\n"
            if c.get("description"):
                text += f"  _{c['description'][:80]}_\n"
        text += "\n"

    text += "━━━━━━━━━━━━━━\n"
    text += "**Ссылки для скачивания:**\n"
    for c in components:
        if c.get("link"):
            text += f"• [{c['name']}]({c['link']})\n"

    text += "\n💡 *Не забудь проверить файлы через /scan*"

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )
    await callback.answer()


# ========== ADDBUILD / ADDAUTHOR / ADDCOMPONENT ==========
@dp.message(F.text.startswith("title:"))
async def handle_addbuild_data(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    data = {}
    for line in message.text.split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip().lower()] = value.strip()

    if "title" not in data or "category" not in data:
        await message.answer("❌ Нужны title и category.")
        return
    if data["category"] not in CATEGORIES:
        await message.answer(f"❌ Категория: {', '.join(CATEGORIES.keys())}")
        return

    build_id = catalog.add_build(
        title=data["title"],
        category=data["category"],
        description=data.get("description", ""),
        author=data.get("author", ""),
        link=data.get("link", ""),
        sha256=data.get("sha256", ""),
        added_by=message.from_user.id,
    )
    if data.get("author"):
        catalog.update_author_stats(data["author"])
    await message.answer(f"✅ Сборка добавлена! ID: {build_id}\n\n/builds")


@dp.message(F.text.startswith("name:"))
async def handle_addauthor_or_component(message: types.Message):
    """Обрабатывает и /addauthor, и /addcomponent — они оба начинаются с name:."""
    if message.from_user.id not in ADMIN_IDS:
        return

    data = {}
    for line in message.text.split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip().lower()] = value.strip()

    if "name" not in data:
        return

    # Если есть category — это компонент
    if "category" in data:
        if data["category"] not in catalog.COMPONENT_CATEGORIES:
            await message.answer(
                f"❌ Категории: {', '.join(catalog.COMPONENT_CATEGORIES.keys())}"
            )
            return
        comp_id = catalog.add_component(
            name=data["name"],
            category=data["category"],
            description=data.get("description", ""),
            link=data.get("link", ""),
            sha256=data.get("sha256", ""),
            size_kb=int(data.get("size_kb", 0) or 0),
            author=data.get("author", ""),
        )
        await message.answer(f"✅ Компонент добавлен! ID: {comp_id}\n\n/constructor")
        return

    # Иначе — автор
    author_id = catalog.add_author(
        name=data["name"],
        telegram=data.get("telegram", ""),
        description=data.get("description", ""),
        verified=1 if data.get("verified") in ("1", "true", "yes") else 0,
    )
    await message.answer(f"✅ Автор добавлен! ID: {author_id}\n\n/authors")


# ========== SCAN: файл и хеш ==========
@dp.message(F.document)
async def handle_file(message: types.Message):
    doc = message.document
    if doc.file_size > 32 * 1024 * 1024:
        await message.answer("❌ Файл больше 32 МБ. Отправь SHA256-хеш.")
        return
    await message.answer("⏳ Считаю хеш...")
    file = await bot.get_file(doc.file_id)
    data = (await bot.download_file(file.file_path)).read()
    sha256 = hashlib.sha256(data).hexdigest()
    await process_scan(message, sha256)


@dp.message(F.text)
async def handle_text(message: types.Message):
    text = (message.text or "").strip()
    if len(text) == 64 and all(c in "0123456789abcdef" for c in text.lower()):
        await process_scan(message, text.lower())
        return
    await message.answer("Используй /scan, /builds, /authors, /constructor или /help.")


async def process_scan(message: types.Message, sha256: str):
    await message.answer(f"🔍 Проверяю `{sha256[:16]}...`", parse_mode="Markdown")
    result = await check_file_hash(sha256)
    if "error" in result:
        if result["error"] == "not_found":
            await message.answer("❓ Файл не найден в VirusTotal.")
        else:
            await message.answer(f"❌ Ошибка API: {result.get('message')}")
        return
    await message.answer(
        format_vt_report(result, sha256),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())