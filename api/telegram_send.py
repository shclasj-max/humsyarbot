"""📤 ارسال فایل به کاربر از طریق ربات تلگرام (مستقیم از بک‌اند API)"""
import os
import httpx

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"


async def send_document_to_user(chat_id: int, file_id: str, caption: str = "") -> bool:
    """
    فایل رو با file_id از طریق ربات مستقیماً برای chat_id ارسال می‌کنه.
    خروجی True/False برمی‌گردونه تا اندپوینت بتونه در صورت خطا به فرانت‌اند اطلاع بده.
    """
    if not BOT_TOKEN:
        return False
    if not file_id:
        return False

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{API_BASE}/sendDocument",
            json={
                "chat_id": chat_id,
                "document": file_id,
                "caption": caption,
            },
        )
    if resp.status_code != 200:
        return False
    data = resp.json()
    return bool(data.get("ok"))
