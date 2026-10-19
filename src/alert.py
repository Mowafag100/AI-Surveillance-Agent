import logging
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

import requests
from src.config import Config

logger = logging.getLogger(__name__)

class Alert:
    def __init__(self):
        self.last_alert_time = 0

    def send_telegram(self, image_path, message):
        """إرسال تنبيه عبر Telegram مع صورة (أو رسالة نصية فقط عند image_path=None)
        — يقرأ التوكن ديناميكياً من Config"""
        token = Config.TELEGRAM_BOT_TOKEN
        chat_id = Config.TELEGRAM_CHAT_ID
        if not token or not chat_id:
            logger.error("❌ Telegram credentials missing")
            return False

        if image_path:
            url = f"https://api.telegram.org/bot{token}/sendPhoto"
            try:
                with open(image_path, "rb") as f:
                    files = {"photo": f}
                    data = {"chat_id": chat_id, "caption": message}
                    resp = requests.post(url, files=files, data=data, timeout=10)
                    if resp.status_code == 200:
                        logger.info("✅ تم إرسال التنبيه إلى Telegram")
                        return True
                    else:
                        logger.error(f"❌ فشل الإرسال: {resp.text}")
            except Exception as e:
                logger.error(f"❌ خطأ في الإرسال: {e}")
            return False

        # بلا صورة: رسالة نصية عبر sendMessage (تُستخدم لتنبيهات انقطاع الكاميرات)
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={"chat_id": chat_id, "text": message},
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info("✅ تم إرسال تنبيه نصي إلى Telegram")
                return True
            logger.error(f"❌ فشل الإرسال: {resp.text}")
        except Exception as e:
            logger.error(f"❌ خطأ في الإرسال: {e}")
        return False

    def send_email_alert(self, image_path, message):
        """إرسال تنبيه بريدي عبر SMTP مع صورة الحدث كمرفق.

        يقرأ الإعدادات ديناميكياً من Config (Hot Reload): SMTP_HOST/PORT/USER/
        PASSWORD/ALERT_EMAIL_TO — يعمل فقط عند ENABLE_EMAIL_ALERTS.
        Image path اختياري: بلا صورة تُرسل رسالة نصية فقط."""
        if not Config.ENABLE_EMAIL_ALERTS:
            logger.debug("ℹ️ تنبيهات البريد معطّلة (ENABLE_EMAIL_ALERTS=false)")
            return False

        host = str(Config.SMTP_HOST or "").strip()
        to_address = str(Config.ALERT_EMAIL_TO or "").strip()
        if not host or not to_address:
            logger.error("❌ إعدادات البريد ناقصة (SMTP_HOST أو ALERT_EMAIL_TO فارغة)")
            return False

        port = int(Config.SMTP_PORT or 587)
        user = str(Config.SMTP_USER or "").strip()
        password = str(Config.SMTP_PASSWORD or "")
        from_address = user or f"surveillance@{host}"

        msg = EmailMessage()
        msg["From"] = formataddr(("AI Surveillance", from_address))
        msg["To"] = to_address
        msg["Subject"] = "🚨 تنبيه مراقبة ذكي"
        msg.set_content(message)

        if image_path:
            try:
                path = Path(image_path)
                if path.is_file():
                    data = path.read_bytes()
                    subtype = path.suffix.lstrip(".").lower() or "jpeg"
                    if subtype in ("jpg", "jpeg"):
                        subtype = "jpeg"
                    elif subtype not in ("png", "gif", "webp"):
                        subtype = "jpeg"
                    msg.add_attachment(
                        data,
                        maintype="image",
                        subtype=subtype,
                        filename=path.name,
                    )
            except OSError as exc:
                logger.warning(f"⚠️ تعذّر إرفاق الصورة ({image_path}): {exc}")

        try:
            if port == 465:
                # SMTPS المباشر (SSL من لحظة الاتصال) — استخدمه مع Gmail: 465
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(host, port, context=context, timeout=15) as smtp:
                    if user:
                        smtp.login(user, password)
                    smtp.send_message(msg)
            else:
                # STARTTLS (Gmail: 587) — دون تشفير فقط إذا استُخدم منفذ 25 عمداً
                with smtplib.SMTP(host, port, timeout=15) as smtp:
                    try:
                        smtp.starttls(context=ssl.create_default_context())
                    except smtplib.SMTPNotSupportedError:
                        logger.warning("⚠️ الخادم لا يدعم STARTTLS — الإرسال دون تشفير")
                    if user:
                        smtp.login(user, password)
                    smtp.send_message(msg)
            logger.info(f"✅ تم إرسال تنبيه البريد إلى {to_address}")
            return True
        except Exception as e:
            logger.error(f"❌ فشل إرسال تنبيه البريد: {e}")
            return False

    def is_cooldown_over(self):
        """تأكد من مرور وقت كافٍ بين التنبيهات"""
        from time import time
        if time() - self.last_alert_time > Config.ALERT_COOLDOWN:
            self.last_alert_time = time()
            return True
        return False
