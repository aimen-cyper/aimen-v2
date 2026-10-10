"""
إعدادات التشغيل — تُقرأ من ملف .env ولا تُكتب أبداً داخل الكود.

هذا الملف مسؤول عن:
    • تحميل متغيرات البيئة من ملف .env.
    • التحقق من وجود القيم الإلزامية وإعطاء رسالة خطأ واضحة عند نقصها.
    • تجهيز المسارات (قاعدة البيانات، اللوقات، النسخ الاحتياطية) وإنشاء مجلداتها.

ملاحظة أمنية: لا تُطبع أي قيمة سرية (التوكن/مفتاح التشفير) في اللوقات أو عند الطباعة.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv

from utils.channel_ref import ChannelRefError, normalize_chat_ref
from utils.fs_security import sensitive_paths as _sensitive_paths
from utils.security import register_secret

# المجلد الجذر للمشروع (حيث يوجد هذا الملف)
BASE_DIR: Path = Path(__file__).resolve().parent


class ConfigError(Exception):
    """خطأ في ملف الإعدادات أو في متغيرات البيئة."""


def _get_str(key: str, default: str | None = None) -> str | None:
    """قراءة متغير نصي من البيئة مع تجاهل الفراغات والقيم الفارغة."""
    value = os.getenv(key, default)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _get_int(key: str) -> int | None:
    """قراءة متغير رقمي اختياري من البيئة، وإرجاع None إن لم يكن موجوداً أو صالحاً."""
    raw = _get_str(key)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"القيمة في المتغير {key} يجب أن تكون رقماً صحيحاً.") from exc


def _get_chat_ref(key: str) -> int | str | None:
    """
    قراءة معرّف قناة/محادثة اختياري من البيئة (`-100…` أو `@username` أو `t.me/name`).

    يُصحَّح الخطأ الشائع (رقم قناة بلا `-100`) ويُرفض ما لا يُصلَح برسالة تشرح السبب — بدل أن يظهر
    لاحقاً كـ«Chat not found» عند أول إرسال.
    """
    raw = _get_str(key)
    if raw is None:
        return None
    try:
        return normalize_chat_ref(raw, allow_user_ids=True)
    except ChannelRefError as exc:
        raise ConfigError(f"القيمة في المتغير {key} غير صالحة: {exc}") from exc


def _get_port(key: str) -> int | None:
    """قراءة منفذ اختياري (1..65535)؛ الفراغ ⇒ None."""
    value = _get_int(key)
    if value is None:
        return None
    if not 1 <= value <= 65535:
        raise ConfigError(f"القيمة في المتغير {key} يجب أن تكون منفذاً بين 1 و65535.")
    return value


def _get_ids(key: str) -> tuple[int, ...]:
    """قراءة قائمة معرفات تيليجرام مفصولة بفواصل (مثال: 111,222)."""
    raw = _get_str(key)
    if not raw:
        return ()
    ids: list[int] = []
    # تسامح مع أخطاء اللصق الشائعة في لوحات الاستضافة: أقواس، علامات اقتباس، مسافات، فاصلة عربية
    cleaned = raw.translate(str.maketrans({"[": " ", "]": " ", "'": " ", '"': " ", "،": ","}))
    for part in cleaned.replace(";", ",").replace(" ", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError as exc:
            raise ConfigError(
                f"المتغير {key} يجب أن يحتوي معرفات رقمية مفصولة بفواصل، والقيمة «{part}» غير صالحة."
            ) from exc
    return tuple(ids)


#: صيغة توكن بوت تيليجرام: معرّف رقمي ثم نقطتان ثم نص طويل
_BOT_TOKEN_RE = re.compile(r"\d{6,12}:[A-Za-z0-9_\-]{30,}")


def _validate_secrets(bot_token: str | None, encryption_key: str | None) -> None:
    """
    فحص صيغة الأسرار عند التحميل لاكتشاف الخطأ قبل أول استخدام.

    الاستثناءات:
        ConfigError : توكن بصيغة خاطئة، أو مفتاح تشفير ليس مفتاح Fernet صالحاً.
                      (الرسالة لا تحتوي القيمة نفسها أبداً.)
    """
    if bot_token and not _BOT_TOKEN_RE.fullmatch(bot_token):
        raise ConfigError(
            "قيمة BOT_TOKEN بصيغة غير صحيحة — انسخها كاملة من @BotFather "
            "(مثال الشكل: 123456789:AA... بلا مسافات أو علامات اقتباس)."
        )
    if encryption_key:
        try:
            Fernet(encryption_key.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise ConfigError(
                "قيمة ENCRYPTION_KEY ليست مفتاح Fernet صالحاً — ولّد واحداً بالأمر: "
                "python -m scripts.init_db --gen-key"
            ) from exc


def _validate_admin_ids(ids: tuple[int, ...]) -> None:
    """معرفات تيليجرام للأشخاص أعداد موجبة؛ السالب/الصفر خطأ إدخال (المجموعات والقنوات سالبة)."""
    bad = [value for value in ids if value <= 0]
    if bad:
        raise ConfigError("SUPER_ADMIN_IDS يجب أن تكون معرفات مستخدمين موجبة (ليس معرف مجموعة أو قناة).")


def _resolve(path_value: str, default_relative: str) -> Path:
    """تحويل مسار نصي إلى مسار مطلق نسبةً لجذر المشروع."""
    raw = path_value or default_relative
    path = Path(raw)
    return path if path.is_absolute() else (BASE_DIR / path)


@dataclass(frozen=True)
class Config:
    """حاوية إعدادات التشغيل (غير قابلة للتعديل بعد التحميل)."""

    bot_token: str | None
    super_admin_ids: tuple[int, ...]
    encryption_key: str | None
    database_path: Path
    log_level: str
    log_file: Path
    backup_dir: Path
    data_dir: Path
    timezone: str
    admin_alert_chat_id: int | str | None
    backup_channel_id: int | str | None
    health_port: int | None = None             # PORT من الاستضافة (Render): يفعّل خادم الصحة الاختياري

    # ------------------------------------------------------------------ #

    @classmethod
    def load(cls, *, require_bot_token: bool = False, env_file: str | Path | None = None) -> "Config":
        """
        تحميل الإعدادات من ملف .env ومن متغيرات البيئة.

        المدخلات:
            require_bot_token : اجعلها True عند تشغيل البوت نفسه (main.py)،
                                واتركها False لأدوات قاعدة البيانات والاختبارات.
            env_file          : مسار ملف بيئة بديل (يُستخدم في الاختبارات).

        المخرجات: كائن Config جاهز.

        الاستثناءات:
            ConfigError : عند نقص قيمة إلزامية أو وجود قيمة غير صالحة.
        """
        load_dotenv(env_file or (BASE_DIR / ".env"), override=False)

        bot_token = _get_str("BOT_TOKEN")
        if require_bot_token and not bot_token:
            raise ConfigError(
                "المتغير BOT_TOKEN غير موجود. انسخ ملف .env.example إلى .env ثم ضع توكن البوت."
            )

        database_path = _resolve(_get_str("DATABASE_PATH") or "", "data/smm_bot.db")
        log_file = _resolve(_get_str("LOG_FILE") or "", "logs/bot.log")
        backup_dir = _resolve(_get_str("BACKUP_DIR") or "", "backups")

        log_level = (_get_str("LOG_LEVEL") or "INFO").upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigError("قيمة LOG_LEVEL يجب أن تكون إحدى: DEBUG/INFO/WARNING/ERROR/CRITICAL")

        encryption_key = _get_str("ENCRYPTION_KEY")
        super_admin_ids = _get_ids("SUPER_ADMIN_IDS")
        _validate_secrets(bot_token, encryption_key)
        _validate_admin_ids(super_admin_ids)
        # تسجيل الأسرار ليُحذف أي ظهور حرفي لها من اللوقات وحقول الأخطاء المخزَّنة
        register_secret(bot_token)
        register_secret(encryption_key)

        return cls(
            bot_token=bot_token,
            super_admin_ids=super_admin_ids,
            encryption_key=encryption_key,
            database_path=database_path,
            log_level=log_level,
            log_file=log_file,
            backup_dir=backup_dir,
            data_dir=database_path.parent,
            timezone=_get_str("TIMEZONE") or "Asia/Aden",
            admin_alert_chat_id=_get_chat_ref("ADMIN_ALERT_CHAT_ID"),
            backup_channel_id=_get_chat_ref("BACKUP_CHANNEL_ID"),
            health_port=_get_port("PORT"),
        )

    def ensure_directories(self) -> None:
        """إنشاء المجلدات المطلوبة (البيانات/اللوقات/النسخ الاحتياطية) إن لم تكن موجودة."""
        for directory in (self.data_dir, self.log_file.parent, self.backup_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def sensitive_paths(self, env_file: Path | None = None) -> list[tuple[Path, str, int]]:
        """المسارات الحسّاسة (بيئة/قاعدة/نسخ/لوق) مع الصلاحية المطلوبة لكل منها."""
        return _sensitive_paths(
            env_file=env_file or (BASE_DIR / ".env"),
            database_path=self.database_path,
            data_dir=self.data_dir,
            backup_dir=self.backup_dir,
            log_dir=self.log_file.parent,
        )

    def safe_summary(self) -> dict[str, str]:
        """ملخص آمن للطباعة — بدون أي قيمة سرية."""
        return {
            "database_path": str(self.database_path),
            "log_file": str(self.log_file),
            "backup_dir": str(self.backup_dir),
            "timezone": self.timezone,
            "log_level": self.log_level,
            "bot_token": "✓ موجود" if self.bot_token else "✗ غير موجود",
            "encryption_key": "✓ موجود" if self.encryption_key else "✗ غير موجود",
            "super_admins": str(len(self.super_admin_ids)),
        }
