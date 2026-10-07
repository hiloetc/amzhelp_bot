import asyncio
import os
import hashlib
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile

import aiohttp

BOT_TOKEN = os.getenv("BOT_TOKEN")
VT_API_KEY = os.getenv("VIRUSTOTAL_API_KEY")

if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN не найден")
if not VT_API_KEY:
    raise SystemExit("❌ VIRUSTOTAL_API_KEY не найден")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ========== VIRUSTOTAL ==========
VT_API_URL = "https://www.virustotal.com/api/v3/files/{}"

async def check_file_hash(sha256: str) -> dict:
    """Проверяет хеш файла через VirusTotal API."""
    headers = {"x-apikey": VT_API_KEY}
    url = VT_API_URL.format(sha256)

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            elif resp.status == 404:
                return {"error": "not_found", "message": "Файл не найден в базе VirusTotal"}
            else:
                text = await resp.text()
                return {"error": resp.status, "message": text[:200]}


# ========== БОТ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🛡 **Сканер безопасности сборок**\n\n"
        "Отправь мне файл сборки (.exe, .zip, .rar), и я проверю его через VirusTotal.\n\n"
        "⚠️ **Важно:** файл должен быть не больше 32 МБ. Если больше — отправь SHA256-хеш файла.\n\n"
        "Команды:\n"
        "/scan — отправить файл на проверку\n"
        "/hash — проверить по хешу",
        parse_mode="Markdown",
    )


@dp.message(Command("scan"))
async def cmd_scan(message: types.Message):
    await message.answer("📎 Отправь файл сборки (до 32 МБ).")


@dp.message(Command("hash"))
async def cmd_hash(message: types.Message):
    await message.answer(
        "🔑 Отправь SHA256-хеш файла (64 символа).\n\n"
        "Как получить хеш:\n"
        "1. Скачай файл\n"
        "2. Открой PowerShell в папке с файлом\n"
        "3. Выполни: `Get-FileHash .\\имя_файла -Algorithm SHA256`\n"
        "4. Скопируй значение",
        parse_mode="Markdown",
    )


@dp.message()
async def handle_file(message: types.Message):
    # Проверка на хеш (если текстовое сообщение из 64 hex-символов)
    if message.text and len(message.text.strip()) == 64:
        sha256 = message.text.strip().lower()
        if all(c in "0123456789abcdef" for c in sha256):
            await process_scan(message, sha256)
            return

    # Проверка на файл
    if message.document:
        doc = message.document
        if doc.file_size > 32 * 1024 * 1024:
            await message.answer("❌ Файл больше 32 МБ. Отправь SHA256-хеш файла.")
            return

        await message.answer("⏳ Скачиваю файл и считаю хеш...")

        file = await bot.get_file(doc.file_id)
        file_bytes = await bot.download_file(file.file_path)
        data = file_bytes.read()

        sha256 = hashlib.sha256(data).hexdigest()
        await process_scan(message, sha256)
        return

    await message.answer("Отправь файл или SHA256-хеш. Используй /scan или /hash.")


async def process_scan(message: types.Message, sha256: str):
    await message.answer(f"🔍 Проверяю хеш `{sha256[:16]}...` в VirusTotal...", parse_mode="Markdown")

    result = await check_file_hash(sha256)

    if "error" in result:
        if result["error"] == "not_found":
            await message.answer(
                "❓ **Файл не найден в базе VirusTotal.**\n\n"
                "Это значит, что файл ещё никто не проверял. "
                "Загрузи его вручную на virustotal.com для полной проверки.",
                parse_mode="Markdown",
            )
        else:
            await message.answer(f"❌ Ошибка API: {result['message']}")
        return

    # Парсим отчёт
    try:
        attrs = result["data"]["attributes"]
        stats = attrs.get("last_analysis_stats", {})

        malicious = stats.get("malicious", 0)
        suspicious = stats.get("suspicious", 0)
        undetected = stats.get("undetected", 0)
        harmless = stats.get("harmless", 0)
        total = malicious + suspicious + undetected + harmless

        # Определяем вердикт
        if malicious >= 5:
            verdict = "🔴 **ОПАСНО!**"
            emoji = "🚨"
        elif malicious >= 1:
            verdict = "🟠 **ПОДОЗРИТЕЛЬНО**"
            emoji = "⚠️"
        else:
            verdict = "🟢 **ЧИСТО**"
            emoji = "✅"

        # Ищем названия угроз
        threat_names = []
        for engine, data in attrs.get("last_analysis_results", {}).items():
            if data.get("category") == "malicious":
                threat_names.append(f"• {engine}: {data.get('result', 'unknown')}")

        threat_text = "\n".join(threat_names[:5]) if threat_names else "Угроз не обнаружено"

        report = (
            f"{emoji} {verdict}\n\n"
            f"📊 **Результат:** {malicious}/{total} антивирусов нашли угрозы\n"
            f"├ Опасных: {malicious}\n"
            f"├ Подозрительных: {suspicious}\n"
            f"├ Чистых: {harmless + undetected}\n\n"
            f"🔎 **Детали:**\n{threat_text}\n\n"
            f"🔗 [Полный отчёт](https://www.virustotal.com/gui/file/{sha256})"
        )

        await message.answer(report, parse_mode="Markdown", disable_web_page_preview=True)

    except Exception as e:
        await message.answer(f"❌ Ошибка при разборе отчёта: {e}")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())