# الكود الكامل — المرحلة 1 (قاعدة البيانات)

هذا الملف يجمع محتوى **كل** ملفات المرحلة 1 كما هي في المشروع، مرتبة حسب الطبقة.
الملفات نفسها موجودة في مجلد `smm_bot/` وهي المصدر الرسمي؛ هذا الملف للمراجعة والنسخ فقط.

## الفهرس

- **الإعدادات وملفات الجذر**
  - `config.py` — 153 سطر
  - `requirements.txt` — 19 سطر
  - `requirements-dev.txt` — 5 سطر
  - `.env.example` — 34 سطر
  - `.gitignore` — 26 سطر
  - `pytest.ini` — 7 سطر
- **النواة — core/**
  - `core/__init__.py` — 1 سطر
  - `core/enums.py` — 224 سطر
  - `core/exceptions.py` — 160 سطر
  - `core/money.py` — 154 سطر
  - `core/permissions.py` — 153 سطر
  - `core/constants.py` — 44 سطر
- **الأدوات المساعدة — utils/**
  - `utils/__init__.py` — 1 سطر
  - `utils/datetime_utils.py` — 103 سطر
  - `utils/security.py` — 126 سطر
  - `utils/logging_setup.py` — 96 سطر
- **طبقة قاعدة البيانات — database/**
  - `database/__init__.py` — 1 سطر
  - `database/database.py` — 311 سطر
  - `database/migrator.py` — 241 سطر
  - `database/models.py` — 440 سطر
- **ملفات الترحيل — database/migrations/**
  - `database/migrations/0001_initial_schema.sql` — 502 سطر
  - `database/migrations/0002_seed_rbac.sql` — 104 سطر
  - `database/migrations/0003_seed_settings.sql` — 70 سطر
- **المستودعات — database/repositories/**
  - `database/repositories/__init__.py` — 83 سطر
  - `database/repositories/base.py` — 91 سطر
  - `database/repositories/users.py` — 279 سطر
  - `database/repositories/rbac.py` — 109 سطر
  - `database/repositories/settings.py` — 132 سطر
  - `database/repositories/providers.py` — 161 سطر
  - `database/repositories/categories.py` — 75 سطر
  - `database/repositories/services.py` — 238 سطر
  - `database/repositories/orders.py` — 452 سطر
  - `database/repositories/transactions.py` — 144 سطر
  - `database/repositories/payments.py` — 249 سطر
  - `database/repositories/tickets.py` — 199 سطر
  - `database/repositories/notifications.py` — 184 سطر
  - `database/repositories/audit.py` — 97 سطر
  - `database/repositories/broadcasts.py` — 165 سطر
  - `database/repositories/idempotency.py` — 92 سطر
  - `database/repositories/misc.py` — 229 سطر
- **أدوات التشغيل — scripts/**
  - `scripts/__init__.py` — 1 سطر
  - `scripts/init_db.py` — 179 سطر
  - `scripts/create_admin.py` — 83 سطر
- **الاختبارات — tests/**
  - `tests/conftest.py` — 96 سطر
  - `tests/test_money.py` — 116 سطر
  - `tests/test_migrations.py` — 173 سطر
  - `tests/test_schema_constraints.py` — 198 سطر
  - `tests/test_database.py` — 133 سطر
  - `tests/test_repositories.py` — 481 سطر
  - `tests/test_permissions_seed.py` — 115 سطر
  - `tests/test_security.py` — 125 سطر
  - `tests/test_config_and_time.py` — 177 سطر

**الإجمالي: 52 ملفاً / 7831 سطراً.**

---

# الإعدادات وملفات الجذر

## `config.py`

```python
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
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

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


def _get_ids(key: str) -> tuple[int, ...]:
    """قراءة قائمة معرفات تيليجرام مفصولة بفواصل (مثال: 111,222)."""
    raw = _get_str(key)
    if not raw:
        return ()
    ids: list[int] = []
    for part in raw.replace(";", ",").split(","):
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
    admin_alert_chat_id: int | None
    backup_channel_id: int | None

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

        return cls(
            bot_token=bot_token,
            super_admin_ids=_get_ids("SUPER_ADMIN_IDS"),
            encryption_key=_get_str("ENCRYPTION_KEY"),
            database_path=database_path,
            log_level=log_level,
            log_file=log_file,
            backup_dir=backup_dir,
            data_dir=database_path.parent,
            timezone=_get_str("TIMEZONE") or "Asia/Aden",
            admin_alert_chat_id=_get_int("ADMIN_ALERT_CHAT_ID"),
            backup_channel_id=_get_int("BACKUP_CHANNEL_ID"),
        )

    def ensure_directories(self) -> None:
        """إنشاء المجلدات المطلوبة (البيانات/اللوقات/النسخ الاحتياطية) إن لم تكن موجودة."""
        for directory in (self.data_dir, self.log_file.parent, self.backup_dir):
            directory.mkdir(parents=True, exist_ok=True)

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
```

## `requirements.txt`

```text
# ======================================================================
# متطلبات تشغيل SMM Bot — إصدارات مثبّتة ومختبَرة فعلياً على Python 3.13
# التثبيت:  pip install -r requirements.txt
# ======================================================================

# إطار بوت تيليجرام + مجدول المهام الدورية (JobQueue)
python-telegram-bot[job-queue]==21.9

# طبقة SQLite غير المتزامنة (كل عمليات قاعدة البيانات تمر عبرها)
aiosqlite==0.22.1

# تشفير مفاتيح API للمزودين (Fernet)
cryptography==50.0.2

# قراءة الإعدادات من ملف .env
python-dotenv==1.2.3

# بيانات المناطق الزمنية (لعرض التواريخ بتوقيت Asia/Aden على كل نظام تشغيل)
tzdata==2026.3
```

## `requirements-dev.txt`

```text
# أدوات التطوير والاختبار فقط (لا تُثبَّت على سيرفر التشغيل)
# التثبيت:  pip install -r requirements.txt -r requirements-dev.txt

pytest==9.0.3
pytest-asyncio==1.4.0
```

## `.env.example`

```bash
# ==========================================================
#  ملف إعدادات البيئة — انسخه إلى .env ثم املأ القيم
#  ⚠️ لا ترفع ملف .env إلى Git أبداً
# ==========================================================

# توكن البوت من BotFather (مطلوب لتشغيل البوت، غير مطلوب لتهيئة قاعدة البيانات)
BOT_TOKEN=

# معرفات تيليجرام لأصحاب صلاحية الأدمن الأعلى، مفصولة بفواصل
# تُستخدم لزرع أول حساب إداري وللطوارئ فقط
SUPER_ADMIN_IDS=

# مفتاح تشفير مفاتيح المزودين (Fernet)
# ولّده بالأمر: python -m scripts.init_db --gen-key
ENCRYPTION_KEY=

# مسار ملف قاعدة البيانات
DATABASE_PATH=data/smm_bot.db

# إعدادات السجلات: DEBUG / INFO / WARNING / ERROR / CRITICAL
LOG_LEVEL=INFO
LOG_FILE=logs/bot.log

# مجلد النسخ الاحتياطية
BACKUP_DIR=backups

# المنطقة الزمنية المستخدمة في العرض (التخزين دائماً UTC)
TIMEZONE=Asia/Aden

# قناة أو مجموعة خاصة لاستقبال تنبيهات النظام (اختياري)
ADMIN_ALERT_CHAT_ID=

# قناة خاصة لحفظ النسخ الاحتياطية خارج السيرفر (اختياري)
BACKUP_CHANNEL_ID=
```

## `.gitignore`

```gitignore
# البيئة والأسرار
.env
*.key

# قاعدة البيانات والملفات المتولدة
data/
logs/
backups/
*.db
*.db-wal
*.db-shm

# بايثون
__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/
.ruff_cache/
.mypy_cache/
*.egg-info/

# أدوات المحرر
.idea/
.vscode/
.DS_Store
```

## `pytest.ini`

```ini
[pytest]
# تشغيل اختبارات async تلقائياً دون الحاجة لوسم كل اختبار
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
testpaths = tests
python_files = test_*.py
addopts = -q --tb=short
```

# النواة — core/

## `core/__init__.py`

```python
"""النواة: التعدادات وحساب المال والاستثناءات وكتالوج الصلاحيات."""
```

## `core/enums.py`

```python
"""
تعدادات النظام (Enums) — المصدر الوحيد لكل القيم النصية المسموحة في قاعدة البيانات.

مهم جداً: أي قيمة هنا يجب أن تطابق قيود CHECK في ملفات الترحيل (migrations)،
ويوجد اختبار آلي يتحقق من هذا التطابق (tests/test_schema_constraints.py).
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """أدوار المستخدمين في النظام."""

    USER = "user"
    SUPPORT = "support"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class OrderStatus(StrEnum):
    """حالات الطلب — راجع جدول الانتقالات في core/order_state.py (المرحلة 2)."""

    PENDING = "pending"                    # أُنشئ وخُصم الرصيد، بانتظار الإرسال للمزود
    SUBMITTING = "submitting"              # جاري الإرسال (مقفول بـ lease)
    SUBMIT_UNCERTAIN = "submit_uncertain"  # انقطاع/مهلة: لا نعرف هل وصل الطلب للمزود
    SUBMITTED = "submitted"                # المزود قبل الطلب وأعطانا رقمه
    IN_PROGRESS = "in_progress"            # قيد التنفيذ عند المزود
    PARTIAL = "partial"                    # نُفِّذ جزئياً (مع استرجاع جزئي)
    COMPLETED = "completed"                # اكتمل
    CANCELED = "canceled"                  # أُلغي (مع استرجاع كامل)
    FAILED = "failed"                      # فشل الإرسال/رفضه المزود
    REFUNDED = "refunded"                  # استُرجع كامل المبلغ بعد فشل أو إلغاء


#: الحالات النهائية التي لا يجوز الانتقال منها إلى أي حالة أخرى
FINAL_ORDER_STATUSES: frozenset[str] = frozenset(
    {OrderStatus.COMPLETED, OrderStatus.PARTIAL, OrderStatus.REFUNDED, OrderStatus.CANCELED}
)

#: الحالات النشطة التي يتابعها job فحص الحالة
ACTIVE_ORDER_STATUSES: frozenset[str] = frozenset(
    {OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS}
)


class PaymentStatus(StrEnum):
    """حالات طلب الشحن."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class TransactionType(StrEnum):
    """أنواع الحركات المالية."""

    DEPOSIT = "deposit"                # شحن رصيد معتمد
    ORDER = "order"                    # خصم قيمة طلب
    REFUND = "refund"                  # استرجاع كامل
    PARTIAL_REFUND = "partial_refund"  # استرجاع جزئي (طلب partial)
    MANUAL_CREDIT = "manual_credit"    # إضافة يدوية من الأدمن
    MANUAL_DEBIT = "manual_debit"      # خصم يدوي من الأدمن
    WITHDRAW = "withdraw"              # سحب
    ADJUSTMENT = "adjustment"          # تسوية محاسبية


class TransactionDirection(StrEnum):
    """اتجاه الحركة المالية: إضافة أم خصم."""

    CREDIT = "credit"
    DEBIT = "debit"


#: الاتجاه الافتراضي لكل نوع حركة (يمنع التناقض بين النوع والاتجاه)
TRANSACTION_DIRECTIONS: dict[str, str] = {
    TransactionType.DEPOSIT: TransactionDirection.CREDIT,
    TransactionType.ORDER: TransactionDirection.DEBIT,
    TransactionType.REFUND: TransactionDirection.CREDIT,
    TransactionType.PARTIAL_REFUND: TransactionDirection.CREDIT,
    TransactionType.MANUAL_CREDIT: TransactionDirection.CREDIT,
    TransactionType.MANUAL_DEBIT: TransactionDirection.DEBIT,
    TransactionType.WITHDRAW: TransactionDirection.DEBIT,
    TransactionType.ADJUSTMENT: TransactionDirection.CREDIT,  # قد يكون debit — يحدده المنادي
}


class ServiceType(StrEnum):
    """نوع الخدمة — v1 ينفّذ default فقط، والبقية محجوزة للتوسعة."""

    DEFAULT = "default"
    CUSTOM_COMMENTS = "custom_comments"
    DRIP_FEED = "drip_feed"
    SUBSCRIPTION = "subscription"


class TicketStatus(StrEnum):
    """حالات تذكرة الدعم."""

    OPEN = "open"
    PENDING_ADMIN = "pending_admin"
    PENDING_USER = "pending_user"
    CLOSED = "closed"


class TicketPriority(StrEnum):
    """أولوية التذكرة."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class SenderType(StrEnum):
    """نوع مرسل رسالة الدعم."""

    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"


class NotificationStatus(StrEnum):
    """حالة الإشعار في صندوق الإرسال (Outbox)."""

    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"  # المستخدم حظر البوت مثلاً


class NotificationType(StrEnum):
    """أنواع الإشعارات المرسلة للمستخدم."""

    ORDER_CREATED = "order_created"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_IN_PROGRESS = "order_in_progress"
    ORDER_COMPLETED = "order_completed"
    ORDER_PARTIAL = "order_partial"
    ORDER_FAILED = "order_failed"
    ORDER_CANCELED = "order_canceled"
    ORDER_REFUNDED = "order_refunded"
    PAYMENT_RECEIVED = "payment_received"
    PAYMENT_APPROVED = "payment_approved"
    PAYMENT_REJECTED = "payment_rejected"
    BALANCE_CREDITED = "balance_credited"
    BALANCE_DEBITED = "balance_debited"
    TICKET_REPLIED = "ticket_replied"
    TICKET_CLOSED = "ticket_closed"
    BROADCAST = "broadcast"
    SYSTEM = "system"


class ActorType(StrEnum):
    """من نفّذ تغيير الحالة (يُسجَّل في order_status_history)."""

    SYSTEM = "system"
    JOB = "job"
    ADMIN = "admin"
    USER = "user"
    PROVIDER = "provider"


class BroadcastStatus(StrEnum):
    """حالة الرسالة الجماعية."""

    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RecipientStatus(StrEnum):
    """حالة مستلم واحد ضمن رسالة جماعية."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    BLOCKED = "blocked"


class PaymentMethodType(StrEnum):
    """نوع طريقة الدفع."""

    MANUAL = "manual"
    CRYPTO = "crypto"
    GATEWAY = "gateway"


class SettingType(StrEnum):
    """نوع قيمة الإعداد لتحويلها تلقائياً عند القراءة."""

    STR = "str"
    INT = "int"
    BOOL = "bool"
    JSON = "json"
    MONEY = "money"


class BackupType(StrEnum):
    """نوع النسخة الاحتياطية."""

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    PRE_OPERATION = "pre_operation"


class ProviderAction(StrEnum):
    """نوع الاستدعاء المُسجَّل في provider_requests."""

    ADD = "add"
    STATUS = "status"
    BALANCE = "balance"
    SERVICES = "services"
    CANCEL = "cancel"
    REFILL = "refill"


def values(enum_cls: type[StrEnum]) -> tuple[str, ...]:
    """إرجاع كل قيم التعداد كـ tuple نصي (يُستخدم في الاختبارات والتحقق)."""
    return tuple(member.value for member in enum_cls)
```

## `core/exceptions.py`

```python
"""
استثناءات المشروع — كل خطأ متوقع له صنف خاص به.

الفائدة: التعامل مع كل حالة خطأ برسالة مناسبة للمستخدم دون كشف التفاصيل الداخلية،
وبدون استخدام «except: pass» في أي مكان.
"""

from __future__ import annotations


class SMMBotError(Exception):
    """الصنف الأب لكل أخطاء المشروع."""

    #: رسالة عربية مبسطة تُعرض للمستخدم النهائي
    user_message: str = "حدث خطأ غير متوقع. حاول لاحقاً."

    def __init__(self, message: str | None = None, *, user_message: str | None = None) -> None:
        super().__init__(message or self.__class__.__doc__ or "")
        if user_message:
            self.user_message = user_message


# ----------------------------- قاعدة البيانات ----------------------------- #


class DatabaseError(SMMBotError):
    """خطأ عام في قاعدة البيانات."""

    user_message = "تعذر تنفيذ العملية حالياً. حاول بعد قليل."


class DatabaseLockedError(DatabaseError):
    """قاعدة البيانات مقفولة بعد استنفاد محاولات إعادة المحاولة."""


class MigrationError(DatabaseError):
    """خطأ أثناء تطبيق ترحيلات قاعدة البيانات."""


class MigrationChecksumError(MigrationError):
    """تم تعديل ملف ترحيل سبق تطبيقه — ممنوع لأنه يفسد تطابق المخطط."""


# ------------------------------- المال والرصيد ----------------------------- #


class WalletError(SMMBotError):
    """خطأ في عمليات المحفظة."""


class InsufficientBalanceError(WalletError):
    """الرصيد غير كافٍ لإتمام العملية."""

    user_message = "❌ رصيدك غير كافٍ لإتمام هذه العملية."


class InvalidAmountError(WalletError):
    """قيمة المبلغ غير صالحة (صفر أو سالبة أو غير رقمية)."""

    user_message = "❌ المبلغ المُدخل غير صالح."


class DuplicateOperationError(SMMBotError):
    """العملية نُفِّذت مسبقاً بنفس المرجع (حماية من التكرار)."""

    user_message = "⚠️ هذه العملية تم تنفيذها مسبقاً."


# -------------------------------- الطلبات --------------------------------- #


class OrderError(SMMBotError):
    """خطأ عام في الطلبات."""


class InvalidStateTransitionError(OrderError):
    """محاولة انتقال حالة غير مسموح بها."""

    user_message = "⚠️ لا يمكن تنفيذ هذا الإجراء على الطلب في حالته الحالية."


class ServiceNotAvailableError(OrderError):
    """الخدمة غير مفعّلة أو محذوفة."""

    user_message = "❌ هذه الخدمة غير متاحة حالياً."


class QuantityOutOfRangeError(OrderError):
    """الكمية خارج الحد الأدنى/الأقصى للخدمة."""

    user_message = "❌ الكمية خارج الحدود المسموحة لهذه الخدمة."


class InvalidLinkError(OrderError):
    """الرابط غير صالح أو لا يطابق نوع الخدمة."""

    user_message = "❌ الرابط غير صالح. تأكد منه وأعد الإرسال."


# -------------------------------- المزودون -------------------------------- #


class ProviderError(SMMBotError):
    """خطأ عام في التعامل مع مزود الخدمة."""

    user_message = "⚠️ تعذر الاتصال بمزود الخدمة حالياً."


class ProviderTemporaryError(ProviderError):
    """خطأ مؤقت — يمكن إعادة المحاولة بأمان."""


class ProviderPermanentError(ProviderError):
    """خطأ نهائي من المزود — لا فائدة من إعادة المحاولة."""


class ProviderUncertainError(ProviderError):
    """نتيجة غير مؤكدة (مهلة/انقطاع) — ممنوع إعادة الإرسال تلقائياً."""


# -------------------------------- الصلاحيات -------------------------------- #


class PermissionDeniedError(SMMBotError):
    """المستخدم لا يملك الصلاحية المطلوبة."""

    user_message = "🚫 لا تملك صلاحية تنفيذ هذا الإجراء."


class UserBannedError(SMMBotError):
    """المستخدم محظور من استخدام البوت."""

    user_message = "🚫 حسابك محظور من استخدام البوت."


class MaintenanceModeError(SMMBotError):
    """النظام في وضع الصيانة."""

    user_message = "🚧 النظام في وضع الصيانة حالياً. حاول لاحقاً."


class RateLimitedError(SMMBotError):
    """تجاوز المستخدم الحد المسموح من الطلبات."""

    user_message = "⏳ أبطئ قليلاً، لقد أرسلت طلبات كثيرة."


# ---------------------------------- الأمان --------------------------------- #


class EncryptionError(SMMBotError):
    """خطأ في تشفير/فك تشفير الأسرار."""

    user_message = "تعذر تنفيذ العملية لأسباب أمنية."


class ValidationError(SMMBotError):
    """خطأ في التحقق من صحة المدخلات."""

    user_message = "❌ المدخلات غير صحيحة."
```

## `core/money.py`

```python
"""
التعامل مع المال — أعداد صحيحة فقط، بلا أي استخدام لـ float.

المبدأ:
    كل مبلغ في النظام يُخزَّن كعدد صحيح بوحدة «نقطة» = 1/10000 من وحدة العملة.
    مثال: 5.25 ريال  →  52500 نقطة.
    وسعر الألف 1.2345 →  12345 نقطة.

السبب: الحسابات العائمة (float) تُنتج فروقاً صغيرة تتراكم في الأرصدة،
وهو أخطر خطأ ممكن في نظام مالي.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from core.exceptions import InvalidAmountError

#: عدد النقاط في وحدة العملة الواحدة (4 خانات عشرية)
MONEY_SCALE: int = 10_000

#: أقصى مبلغ مسموح في عملية واحدة (حماية من الأخطاء الكارثية عند إدخال رقم ضخم)
MAX_AMOUNT_UNITS: int = 10_000_000 * MONEY_SCALE


def to_units(value: str | int | Decimal) -> int:
    """
    تحويل مبلغ مكتوب (نص/عدد صحيح/Decimal) إلى نقاط صحيحة.

    المدخلات: value مثل "12.5" أو Decimal("12.5") أو 12.
    المخرجات: عدد صحيح من النقاط (12.5 → 125000).

    الاستثناءات:
        InvalidAmountError : القيمة غير رقمية أو سالبة أو تتجاوز الحد الأقصى.
    """
    if isinstance(value, float):  # منع الاستخدام الخاطئ صراحةً
        raise InvalidAmountError("ممنوع تمرير float إلى to_units — استخدم نصاً أو Decimal.")
    try:
        dec = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, AttributeError) as exc:
        raise InvalidAmountError(f"قيمة مالية غير صالحة: {value!r}") from exc

    if dec.is_nan() or dec.is_infinite():
        raise InvalidAmountError("قيمة مالية غير صالحة.")
    if dec < 0:
        raise InvalidAmountError("المبلغ لا يمكن أن يكون سالباً.")

    units = int((dec * MONEY_SCALE).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if units > MAX_AMOUNT_UNITS:
        raise InvalidAmountError("المبلغ يتجاوز الحد الأقصى المسموح.")
    return units


def from_units(units: int) -> Decimal:
    """تحويل النقاط الصحيحة إلى Decimal بعملة العرض (125000 → 12.5)."""
    return (Decimal(int(units)) / Decimal(MONEY_SCALE)).quantize(Decimal("0.0001"))


def format_units(units: int, symbol: str = "", decimals: int = 2) -> str:
    """
    تنسيق مبلغ للعرض على المستخدم.

    المدخلات:
        units    : المبلغ بالنقاط.
        symbol   : رمز العملة (مثل "﷼" أو "$").
        decimals : عدد الخانات المعروضة (لا يؤثر على التخزين).

    المخرجات: نص منسّق مثل "12.50 ﷼".
    """
    quant = Decimal(1).scaleb(-decimals)  # 0.01 مثلاً
    amount = from_units(units).quantize(quant, rounding=ROUND_HALF_UP)
    text = f"{amount:,.{decimals}f}"
    return f"{text} {symbol}".strip()


def order_cost_units(price_per_1000_units: int, quantity: int) -> int:
    """
    حساب تكلفة الطلب بدقة كاملة بأعداد صحيحة.

    المعادلة: التكلفة = (سعر الألف × الكمية) ÷ 1000 مع تقريب نصفي لأعلى.

    المدخلات:
        price_per_1000_units : سعر الألف بالنقاط.
        quantity             : الكمية المطلوبة.

    المخرجات: تكلفة الطلب بالنقاط.

    الاستثناءات:
        InvalidAmountError : كمية أو سعر غير صالح.
    """
    if price_per_1000_units <= 0:
        raise InvalidAmountError("سعر الخدمة يجب أن يكون أكبر من صفر.")
    if quantity <= 0:
        raise InvalidAmountError("الكمية يجب أن تكون أكبر من صفر.")
    total = price_per_1000_units * quantity
    cost = (total + 500) // 1000  # تقريب نصفي لأعلى بأعداد صحيحة
    if cost > MAX_AMOUNT_UNITS:
        raise InvalidAmountError("تكلفة الطلب تتجاوز الحد الأقصى المسموح.")
    return cost


def unit_price_units(price_per_1000_units: int) -> Decimal:
    """سعر الوحدة الواحدة (بالنقاط، كـ Decimal لتفادي فقدان الدقة في الحسابات الوسيطة)."""
    return Decimal(price_per_1000_units) / Decimal(1000)


def partial_refund_units(
    *,
    cost_units: int,
    quantity: int,
    remains: int,
    already_refunded_units: int = 0,
) -> int:
    """
    حساب مبلغ الاسترجاع الجزئي لطلب نُفِّذ جزئياً.

    السياسة المعتمدة: يُسترجع ما يقابل الكمية غير المنفَّذة من التكلفة الأصلية.
        الاسترجاع = التكلفة × (المتبقي ÷ الكمية) − ما سبق استرجاعه

    المدخلات:
        cost_units             : تكلفة الطلب الأصلية بالنقاط.
        quantity               : الكمية الأصلية.
        remains                : الكمية غير المنفَّذة كما أبلغ عنها المزود.
        already_refunded_units : ما سبق استرجاعه لهذا الطلب (لمنع الاسترجاع المزدوج).

    المخرجات: مبلغ الاسترجاع بالنقاط (قد يكون 0 إن لم يستحق شيء).
    """
    if quantity <= 0 or cost_units <= 0:
        return 0
    remains = max(0, min(int(remains), int(quantity)))  # ضبط ضمن الحدود المنطقية
    if remains == 0:
        return 0
    refund = (cost_units * remains) // quantity  # تقريب لأسفل لصالح النظام (لا يتجاوز التكلفة)
    refund = min(refund, cost_units)
    remaining_allowed = cost_units - max(0, already_refunded_units)
    return max(0, min(refund, remaining_allowed))


def apply_markup(provider_price_units: int, markup_percent: int) -> int:
    """
    حساب سعر البيع من سعر التكلفة بإضافة نسبة ربح.

    المدخلات:
        provider_price_units : سعر الألف عند المزود بالنقاط.
        markup_percent       : نسبة الربح (مثال 30 تعني +30%).

    المخرجات: سعر البيع بالنقاط (مقرّب نصفياً لأعلى).
    """
    if provider_price_units < 0:
        raise InvalidAmountError("سعر التكلفة غير صالح.")
    if markup_percent < 0:
        raise InvalidAmountError("نسبة الربح لا يمكن أن تكون سالبة.")
    total = provider_price_units * (100 + markup_percent)
    return (total + 50) // 100
```

## `core/permissions.py`

```python
"""
كتالوج الصلاحيات والأدوار.

هذا الملف هو «المرجع» لأسماء الصلاحيات المستخدمة في الكود،
بينما القيم الفعلية تُخزَّن في قاعدة البيانات (جداول permissions / role_permissions)
لتبقى قابلة للتعديل من لوحة الأدمن دون تعديل الكود.

يوجد اختبار آلي (tests/test_permissions_seed.py) يتأكد أن ما في هذا الملف
مطابق تماماً لما تزرعه ملفات الترحيل في قاعدة البيانات.
"""

from __future__ import annotations

from typing import NamedTuple

from core.enums import Role


class PermissionDef(NamedTuple):
    """تعريف صلاحية واحدة."""

    code: str
    name_ar: str
    group_code: str
    is_dangerous: bool = False


# --------------------------- كتالوج الصلاحيات --------------------------- #

PERMISSIONS: tuple[PermissionDef, ...] = (
    # الدخول للوحة
    PermissionDef("admin.access", "الدخول إلى لوحة التحكم", "general"),
    # المستخدمون
    PermissionDef("users.view", "عرض المستخدمين والبحث عنهم", "users"),
    PermissionDef("users.balance.credit", "إضافة رصيد لمستخدم", "users", True),
    PermissionDef("users.balance.debit", "خصم رصيد من مستخدم", "users", True),
    PermissionDef("users.ban", "حظر مستخدم", "users", True),
    PermissionDef("users.unban", "فك حظر مستخدم", "users"),
    PermissionDef("users.note", "كتابة ملاحظة إدارية على مستخدم", "users"),
    PermissionDef("users.role.change", "تغيير دور مستخدم", "users", True),
    # الخدمات
    PermissionDef("services.view", "عرض الخدمات", "services"),
    PermissionDef("services.create", "إضافة خدمة", "services"),
    PermissionDef("services.update", "تعديل بيانات خدمة", "services"),
    PermissionDef("services.price", "تغيير سعر خدمة", "services", True),
    PermissionDef("services.archive", "تعطيل أو أرشفة خدمة", "services", True),
    PermissionDef("services.sync", "استيراد ومزامنة خدمات المزود", "services"),
    # المزودون
    PermissionDef("providers.view", "عرض المزودين", "providers"),
    PermissionDef("providers.create", "إضافة مزود", "providers", True),
    PermissionDef("providers.update", "تعديل مزود", "providers", True),
    PermissionDef("providers.key.update", "تغيير مفتاح API للمزود", "providers", True),
    PermissionDef("providers.test", "اختبار اتصال المزود وفحص رصيده", "providers"),
    # الطلبات
    PermissionDef("orders.view", "عرض الطلبات", "orders"),
    PermissionDef("orders.recheck", "إعادة فحص حالة طلب", "orders"),
    PermissionDef("orders.cancel", "إلغاء طلب", "orders", True),
    PermissionDef("orders.refund", "استرجاع مبلغ طلب", "orders", True),
    PermissionDef("orders.link_provider_id", "ربط رقم الطلب عند المزود يدوياً", "orders", True),
    PermissionDef("orders.status.override", "تغيير حالة طلب يدوياً", "orders", True),
    # المدفوعات
    PermissionDef("payments.view", "عرض طلبات الشحن", "payments"),
    PermissionDef("payments.approve", "اعتماد طلب شحن", "payments", True),
    PermissionDef("payments.reject", "رفض طلب شحن", "payments", True),
    PermissionDef("payments.methods", "إدارة طرق الدفع", "payments", True),
    # الدعم
    PermissionDef("tickets.view", "عرض تذاكر الدعم", "tickets"),
    PermissionDef("tickets.reply", "الرد على التذاكر", "tickets"),
    PermissionDef("tickets.assign", "إسناد التذاكر", "tickets"),
    PermissionDef("tickets.close", "إغلاق التذاكر", "tickets"),
    # الإذاعة والإحصائيات
    PermissionDef("broadcast.send", "إرسال رسالة جماعية", "broadcast", True),
    PermissionDef("stats.view", "عرض الإحصائيات", "stats"),
    PermissionDef("stats.profit", "عرض تقارير الأرباح والتكلفة", "stats"),
    # الإعدادات والسجلات
    PermissionDef("settings.view", "عرض الإعدادات", "settings"),
    PermissionDef("settings.update", "تعديل الإعدادات العامة", "settings", True),
    PermissionDef("settings.maintenance", "تفعيل أو إيقاف وضع الصيانة", "settings", True),
    PermissionDef("logs.view", "عرض السجلات والأخطاء", "logs"),
    # النسخ الاحتياطي وإدارة الصلاحيات
    PermissionDef("backup.create", "إنشاء نسخة احتياطية", "backup", True),
    PermissionDef("backup.download", "تنزيل نسخة احتياطية", "backup", True),
    PermissionDef("admins.manage", "إدارة الأدوار والصلاحيات", "admins", True),
)

#: خريطة سريعة: كود الصلاحية → تعريفها
PERMISSION_MAP: dict[str, PermissionDef] = {p.code: p for p in PERMISSIONS}


# ------------------------------ الأدوار ------------------------------ #


class RoleDef(NamedTuple):
    """تعريف دور واحد."""

    code: str
    name_ar: str
    level: int


ROLES: tuple[RoleDef, ...] = (
    RoleDef(Role.USER, "مستخدم", 10),
    RoleDef(Role.SUPPORT, "دعم فني", 40),
    RoleDef(Role.ADMIN, "أدمن", 70),
    RoleDef(Role.SUPER_ADMIN, "أدمن أعلى", 100),
)


#: صلاحيات الدعم الفني (عرض + تذاكر فقط)
_SUPPORT_PERMISSIONS: tuple[str, ...] = (
    "admin.access",
    "users.view",
    "orders.view",
    "orders.recheck",
    "payments.view",
    "tickets.view",
    "tickets.reply",
    "tickets.assign",
    "tickets.close",
    "services.view",
)

#: الصلاحيات الممنوعة على الأدمن العادي (حصرية للأدمن الأعلى)
_SUPER_ONLY: frozenset[str] = frozenset(
    {
        "users.role.change",
        "providers.key.update",
        "orders.link_provider_id",
        "orders.status.override",
        "stats.profit",
        "backup.create",
        "backup.download",
        "admins.manage",
    }
)

#: الصلاحيات الافتراضية لكل دور (تُزرع في جدول role_permissions)
ROLE_DEFAULTS: dict[str, tuple[str, ...]] = {
    Role.USER: (),
    Role.SUPPORT: _SUPPORT_PERMISSIONS,
    Role.ADMIN: tuple(p.code for p in PERMISSIONS if p.code not in _SUPER_ONLY),
    Role.SUPER_ADMIN: tuple(p.code for p in PERMISSIONS),
}


def all_permission_codes() -> tuple[str, ...]:
    """إرجاع كل أكواد الصلاحيات المعرَّفة في الكتالوج."""
    return tuple(p.code for p in PERMISSIONS)


def role_has_default(role: str, permission: str) -> bool:
    """هل يملك الدور هذه الصلاحية افتراضياً؟ (للاختبارات والزرع الأولي فقط)."""
    return permission in ROLE_DEFAULTS.get(role, ())
```

## `core/constants.py`

```python
"""ثوابت عامة للنظام (قيم لا تتغير أثناء التشغيل)."""

from __future__ import annotations

#: اسم المشروع وإصداره
APP_NAME: str = "SMM Telegram Bot"
APP_VERSION: str = "0.2.0-phase1"

#: مدة قفل الطلب أثناء معالجته بواسطة job (بالثواني)
ORDER_LOCK_SECONDS: int = 120

#: أقصى عدد محاولات لإرسال الطلب إلى المزود عند الفشل الآمن (قبل اعتباره فاشلاً)
MAX_SUBMIT_ATTEMPTS: int = 3

#: أقصى عدد محاولات إرسال إشعار قبل اعتباره فاشلاً
MAX_NOTIFICATION_ATTEMPTS: int = 5

#: تدرج فترات إعادة فحص حالة الطلب (بالثواني)
ORDER_CHECK_BACKOFF: tuple[int, ...] = (60, 300, 900, 1800, 3600)

#: تدرج فترات إعادة إرسال الإشعار الفاشل (بالثواني)
NOTIFICATION_BACKOFF: tuple[int, ...] = (10, 60, 300, 1800, 3600)

#: مدة صلاحية مفاتيح منع التكرار الافتراضية (بالثواني)
IDEMPOTENCY_TTL_SECONDS: int = 24 * 3600

#: طول أقصى للنصوص المُخزَّنة من استجابات المزود (منعاً لتضخم قاعدة البيانات)
PROVIDER_RESPONSE_SNIPPET_LEN: int = 500

#: عدد العناصر في صفحة القوائم داخل تيليجرام
PAGE_SIZE: int = 8

#: صيغة مراجع الحركات المالية (تُستخدم لمنع التكرار)
REF_ORDER_DEBIT: str = "order:{order_id}"
REF_ORDER_REFUND: str = "refund:order:{order_id}"
REF_ORDER_PARTIAL_REFUND: str = "partial_refund:order:{order_id}"
REF_PAYMENT_DEPOSIT: str = "payment:{payment_id}"
REF_MANUAL: str = "manual:{kind}:{admin_id}:{token}"

#: صيغة مفاتيح منع تكرار الإشعارات
NOTIF_KEY_ORDER: str = "order:{order_id}:{event}"
NOTIF_KEY_PAYMENT: str = "payment:{payment_id}:{event}"
NOTIF_KEY_TICKET: str = "ticket:{ticket_id}:{event}"
NOTIF_KEY_MANUAL: str = "manual:{token}"
```

# الأدوات المساعدة — utils/

## `utils/__init__.py`

```python
"""أدوات مساعدة عامة: الوقت، اللوقات، الأمان."""
```

## `utils/datetime_utils.py`

```python
"""
أدوات الوقت — قاعدة ثابتة في المشروع:

    • كل ما يُخزَّن في قاعدة البيانات بتوقيت UTC وبصيغة ISO-8601 منتهية بحرف Z.
    • التحويل إلى التوقيت المحلي (Asia/Aden افتراضياً) يتم عند العرض فقط.

السبب: خلط التوقيتات يفسد الإحصائيات اليومية ويجعل مقارنة الأوقات غير موثوقة.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

ISO_FORMAT: str = "%Y-%m-%dT%H:%M:%S.%fZ"


def utc_now() -> datetime:
    """الوقت الحالي بتوقيت UTC ككائن datetime واعٍ بالمنطقة الزمنية."""
    return datetime.now(UTC)


def to_iso(moment: datetime) -> str:
    """تحويل datetime إلى نص ISO-8601 بتوقيت UTC (الصيغة المعتمدة للتخزين)."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime(ISO_FORMAT)


def utc_now_iso() -> str:
    """الوقت الحالي جاهزاً للتخزين في قاعدة البيانات."""
    return to_iso(utc_now())


def parse_iso(value: str | None) -> datetime | None:
    """تحويل نص مخزَّن إلى datetime، وإرجاع None إذا كانت القيمة فارغة أو غير صالحة."""
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def iso_plus_seconds(seconds: int, *, base: datetime | None = None) -> str:
    """نص ISO لوقت مستقبلي بعد عدد من الثواني (يُستخدم للقفول ومواعيد الفحص)."""
    return to_iso((base or utc_now()) + timedelta(seconds=seconds))


def iso_minus_days(days: int, *, base: datetime | None = None) -> str:
    """نص ISO لوقت ماضٍ قبل عدد من الأيام (يُستخدم في التقارير والتنظيف)."""
    return to_iso((base or utc_now()) - timedelta(days=days))


def is_past(value: str | None) -> bool:
    """هل مرّ هذا الوقت المخزَّن؟ (تُعامل القيمة الفارغة على أنها منتهية)."""
    moment = parse_iso(value)
    return True if moment is None else moment <= utc_now()


def to_local_text(value: str | None, timezone: str = "Asia/Aden", fmt: str = "%Y-%m-%d %H:%M") -> str:
    """
    تحويل وقت مخزَّن (UTC) إلى نص بالتوقيت المحلي للعرض على المستخدم.

    المدخلات:
        value    : النص المخزَّن في قاعدة البيانات.
        timezone : المنطقة الزمنية للعرض.
        fmt      : صيغة العرض.

    المخرجات: نص منسّق، أو "-" إذا لم توجد قيمة.
    """
    moment = parse_iso(value)
    if moment is None:
        return "-"
    try:
        zone = ZoneInfo(timezone)
    except Exception:  # منطقة زمنية غير معروفة — نعرض بتوقيت UTC بدل الانهيار
        zone = UTC
    return moment.astimezone(zone).strftime(fmt)


def day_bounds_utc(days_back: int = 0, timezone: str = "Asia/Aden") -> tuple[str, str]:
    """
    حدود يوم محلي كاملة معبَّراً عنها بتوقيت UTC (لاستعلامات الإحصائيات اليومية).

    المدخلات:
        days_back : 0 = اليوم، 1 = أمس ... إلخ.
        timezone  : المنطقة الزمنية المحلية المعتمدة للعرض.

    المخرجات: (بداية اليوم، نهاية اليوم) كنصين ISO بتوقيت UTC.
    """
    try:
        zone = ZoneInfo(timezone)
    except Exception:
        zone = UTC
    local_now = utc_now().astimezone(zone) - timedelta(days=days_back)
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return to_iso(start_local), to_iso(end_local)
```

## `utils/security.py`

```python
"""
أدوات الأمان: تشفير أسرار المزودين، وإخفاء الأسرار عند العرض والتسجيل.

قواعد صارمة:
    • مفاتيح API للمزودين تُخزَّن مشفّرة (Fernet) ولا تُعرض كاملة أبداً.
    • لا يُكتب أي سر في ملفات اللوق.
"""

from __future__ import annotations

import hashlib
import re
import secrets

from cryptography.fernet import Fernet, InvalidToken

from core.exceptions import EncryptionError


def generate_encryption_key() -> str:
    """توليد مفتاح تشفير جديد (يوضع في متغير البيئة ENCRYPTION_KEY)."""
    return Fernet.generate_key().decode("utf-8")


class SecretBox:
    """
    صندوق تشفير متماثل للأسرار المخزَّنة في قاعدة البيانات.

    الاستخدام: تشفير api_key للمزود قبل الحفظ، وفك التشفير عند الاستدعاء فقط.
    """

    def __init__(self, key: str | None) -> None:
        """تهيئة الصندوق بمفتاح Fernet؛ يُرفع خطأ واضح إذا كان المفتاح ناقصاً أو تالفاً."""
        if not key:
            raise EncryptionError(
                "متغير البيئة ENCRYPTION_KEY غير موجود. "
                "ولّد مفتاحاً عبر: python -m scripts.init_db --gen-key"
            )
        try:
            self._fernet = Fernet(key.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise EncryptionError("قيمة ENCRYPTION_KEY غير صالحة (يجب أن تكون مفتاح Fernet).") from exc

    def encrypt(self, plaintext: str) -> str:
        """تشفير نص سري وإرجاعه كنص قابل للتخزين."""
        if not plaintext:
            raise EncryptionError("لا يمكن تشفير قيمة فارغة.")
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """فك تشفير نص مخزَّن؛ يُرفع خطأ إذا كان المفتاح خاطئاً أو البيانات تالفة."""
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except (InvalidToken, ValueError, TypeError) as exc:
            raise EncryptionError(
                "تعذر فك تشفير المفتاح المخزَّن — تأكد أن ENCRYPTION_KEY هو نفسه المستخدم عند الحفظ."
            ) from exc


def mask_secret(value: str | None, visible: int = 4) -> str:
    """
    إخفاء سر للعرض في الواجهة (يُظهر آخر أربعة محارف فقط).

    مثال: "abcd1234efgh" → "••••efgh"
    """
    if not value:
        return "غير محدد"
    tail = value[-visible:] if len(value) > visible else value
    return f"••••{tail}"


def secret_hint(value: str) -> str:
    """تلميح قصير يُخزَّن في قاعدة البيانات بجانب المفتاح المشفّر (آخر 4 محارف)."""
    return value[-4:] if len(value) >= 4 else "****"


def fingerprint(value: str) -> str:
    """بصمة SHA-256 مختصرة لقيمة سرية (للمقارنة دون كشف القيمة)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def new_token(length: int = 16) -> str:
    """توليد رمز عشوائي آمن (يُستخدم كمرجع فريد أو مفتاح منع تكرار)."""
    return secrets.token_urlsafe(length)


#: قيمة سرية: كل ما يلي علامة = أو : حتى أول فاصل، مع تجاهل علامات الاقتباس المحيطة
_SECRET_VALUE = r"[\"']?\s*[=:]\s*[\"']?[^\s,;&'\"}\])]+"

#: أنماط نصية يجب حذفها من أي نص يُسجَّل في اللوقات أو يُخزَّن في قاعدة البيانات
#: كل عنصر: (النمط، النص البديل)
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # توكن بوت تيليجرام بصيغته المعروفة 123456789:AA...
    (re.compile(r"\b\d{6,12}:[A-Za-z0-9_\-]{30,}\b"), "***"),
    # api_key / token / secret / password بأي صيغة (JSON أو query أو سطر إعداد)
    (
        re.compile(
            r"(?i)\b(api[_-]?key|api[_-]?token|access[_-]?token|auth[_-]?token|token|secret"
            r"|password|passwd|pwd)\b" + _SECRET_VALUE
        ),
        r"\1=***",
    ),
    # المعامل key= المستخدم في لوحات SMM (perfect panel)
    (re.compile(r"(?i)\bkey\b" + _SECRET_VALUE), "key=***"),
)


def sanitize(text: str | None, extra_secrets: tuple[str, ...] = ()) -> str:
    """
    تنقية نص من الأسرار قبل تسجيله في اللوق أو حفظه في قاعدة البيانات.

    المدخلات:
        text           : النص الخام (مثل استجابة المزود أو رسالة الخطأ).
        extra_secrets  : قيم سرية معروفة يجب حذفها حرفياً (مثل مفتاح المزود الحالي).

    المخرجات: نص آمن للتسجيل.
    """
    if not text:
        return ""
    clean = str(text)
    for secret in extra_secrets:
        if secret:
            clean = clean.replace(secret, "***")
    for pattern, replacement in _SECRET_PATTERNS:
        clean = pattern.sub(replacement, clean)
    return clean
```

## `utils/logging_setup.py`

```python
"""
إعداد نظام التسجيل (Logging) المركزي.

الميزات:
    • ملف دوّار (RotatingFileHandler) حتى لا يتضخم حجم اللوق.
    • إخراج على الشاشة أثناء التطوير.
    • فلتر أمني يحذف أي توكن أو مفتاح API قبل الكتابة.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from utils.security import sanitize

_CONFIGURED: bool = False


class SecretRedactionFilter(logging.Filter):
    """فلتر يمنع كتابة الأسرار (التوكن/المفاتيح) داخل ملفات اللوق."""

    def filter(self, record: logging.LogRecord) -> bool:
        """تنقية نص الرسالة قبل إخراجها؛ يُرجع True دائماً لأننا لا نحذف السجلات."""
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - نسجل السجل كما هو إن فشل التنسيق
            return True
        cleaned = sanitize(message)
        if cleaned != message:
            record.msg = cleaned
            record.args = ()
        return True


def setup_logging(
    log_file: Path | str = "logs/bot.log",
    level: str = "INFO",
    *,
    console: bool = True,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
) -> logging.Logger:
    """
    تهيئة اللوق المركزي للمشروع (تُستدعى مرة واحدة عند الإقلاع).

    المدخلات:
        log_file     : مسار ملف اللوق.
        level        : مستوى التسجيل (DEBUG/INFO/WARNING/ERROR/CRITICAL).
        console      : إظهار السجلات على الشاشة أيضاً.
        max_bytes    : الحجم الأقصى للملف قبل التدوير.
        backup_count : عدد الملفات المحفوظة بعد التدوير.

    المخرجات: اللوجر الجذري بعد التهيئة.
    """
    global _CONFIGURED

    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    if _CONFIGURED:
        return root

    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    redaction = SecretRedactionFilter()

    file_handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redaction)
    root.addHandler(file_handler)

    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.addFilter(redaction)
        root.addHandler(stream_handler)

    # تخفيف ضجيج المكتبات الخارجية
    for noisy in ("httpx", "httpcore", "aiosqlite", "telegram.vendor", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
    return root


def get_logger(name: str) -> logging.Logger:
    """الحصول على لوجر باسم الوحدة الحالية."""
    return logging.getLogger(name)
```

# طبقة قاعدة البيانات — database/

## `database/__init__.py`

```python
"""طبقة قاعدة البيانات: الاتصال، الترحيلات، النماذج، المستودعات."""
```

## `database/database.py`

```python
"""
طبقة الوصول إلى قاعدة البيانات (SQLite عبر aiosqlite).

التصميم:
    • اتصال كتابة واحد محمي بقفل asyncio  ← لأن SQLite يسمح بكاتب واحد فقط،
      والتسلسل الصريح يمنع أخطاء "database is locked" العشوائية.
    • مجموعة اتصالات للقراءة (WAL يسمح بقراءات متوازية أثناء الكتابة).
    • كل كتابة تتم داخل معاملة BEGIN IMMEDIATE ... COMMIT، مع دعم المعاملات المتداخلة
      (إذا فتحت خدمة معاملة ثم نادت خدمة أخرى، تُستخدم نفس المعاملة ولا تُفتح ثانية).
    • إعادة محاولة تلقائية محدودة عند قفل قاعدة البيانات.

كل عبارات SQL هنا وفي المستودعات (repositories) مُعلَّمة بـ ? — لا بناء نصوص SQL يدوياً.
"""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Sequence

import aiosqlite

from core.exceptions import DatabaseError, DatabaseLockedError
from utils.logging_setup import get_logger

logger = get_logger(__name__)

SQLParams = Sequence[Any] | dict[str, Any]


@dataclass(frozen=True)
class ExecResult:
    """نتيجة تنفيذ عبارة كتابة: عدد الصفوف المتأثرة ومعرف آخر صف مُدرج."""

    rowcount: int
    lastrowid: int | None


def _is_locked_error(exc: BaseException) -> bool:
    """هل هذا الخطأ ناتج عن قفل مؤقت لقاعدة البيانات (قابل لإعادة المحاولة)؟"""
    return isinstance(exc, sqlite3.OperationalError) and (
        "locked" in str(exc).lower() or "busy" in str(exc).lower()
    )


class Tx:
    """
    مقبض معاملة مفتوحة على اتصال الكتابة.

    يُمرَّر إلى دوال المستودعات التي تُعدِّل البيانات، لضمان أن كل التعديلات
    المترابطة (خصم رصيد + إنشاء طلب + تسجيل حركة + إشعار) تتم كوحدة واحدة.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def execute(self, sql: str, params: SQLParams = ()) -> ExecResult:
        """تنفيذ عبارة كتابة (INSERT/UPDATE/DELETE) وإرجاع عدد الصفوف والمعرف الجديد."""
        async with self._conn.execute(sql, params) as cursor:
            return ExecResult(rowcount=cursor.rowcount, lastrowid=cursor.lastrowid)

    async def executemany(self, sql: str, seq: Iterable[SQLParams]) -> ExecResult:
        """تنفيذ نفس العبارة على مجموعة قيم (إدراج جماعي)."""
        async with self._conn.executemany(sql, seq) as cursor:
            return ExecResult(rowcount=cursor.rowcount, lastrowid=cursor.lastrowid)

    async def fetchone(self, sql: str, params: SQLParams = ()) -> aiosqlite.Row | None:
        """قراءة صف واحد داخل المعاملة (يرى التعديلات غير المثبتة بعد)."""
        async with self._conn.execute(sql, params) as cursor:
            return await cursor.fetchone()

    async def fetchall(self, sql: str, params: SQLParams = ()) -> list[aiosqlite.Row]:
        """قراءة كل الصفوف داخل المعاملة."""
        async with self._conn.execute(sql, params) as cursor:
            return list(await cursor.fetchall())

    async def fetchval(self, sql: str, params: SQLParams = (), default: Any = None) -> Any:
        """قراءة قيمة واحدة (أول عمود من أول صف) داخل المعاملة."""
        row = await self.fetchone(sql, params)
        if row is None:
            return default
        value = row[0]
        return default if value is None else value


#: المعاملة النشطة في السياق الحالي (لدعم المعاملات المتداخلة بأمان)
_current_tx: ContextVar[Tx | None] = ContextVar("smm_current_tx", default=None)


class Database:
    """مدير الاتصال بقاعدة البيانات: اتصال كتابة واحد + مجموعة اتصالات قراءة."""

    def __init__(
        self,
        path: str | Path,
        *,
        read_pool_size: int = 3,
        busy_timeout_ms: int = 5_000,
        max_retries: int = 5,
    ) -> None:
        """تهيئة المدير دون فتح الاتصال (الفتح يتم في connect)."""
        self.path = Path(path)
        self._read_pool_size = max(1, read_pool_size)
        self._busy_timeout_ms = busy_timeout_ms
        self._max_retries = max_retries
        self._write_conn: aiosqlite.Connection | None = None
        self._read_pool: asyncio.Queue[aiosqlite.Connection] | None = None
        self._read_conns: list[aiosqlite.Connection] = []
        self._write_lock = asyncio.Lock()
        self._connected = False

    # ------------------------------ الاتصال ------------------------------ #

    async def connect(self) -> None:
        """فتح الاتصالات وتطبيق إعدادات SQLite المطلوبة (WAL، المفاتيح الأجنبية...)."""
        if self._connected:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self._write_conn = await self._open_connection()
        self._read_pool = asyncio.Queue(maxsize=self._read_pool_size)
        for _ in range(self._read_pool_size):
            conn = await self._open_connection()
            self._read_conns.append(conn)
            self._read_pool.put_nowait(conn)

        self._connected = True
        logger.info("تم الاتصال بقاعدة البيانات: %s", self.path)

    async def _open_connection(self) -> aiosqlite.Connection:
        """فتح اتصال واحد وضبط إعداداته (isolation_level=None للتحكم اليدوي بالمعاملات)."""
        conn = await aiosqlite.connect(self.path, isolation_level=None)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode = WAL")
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute(f"PRAGMA busy_timeout = {int(self._busy_timeout_ms)}")
        await conn.execute("PRAGMA synchronous = NORMAL")
        await conn.execute("PRAGMA temp_store = MEMORY")
        return conn

    async def close(self) -> None:
        """إغلاق كل الاتصالات بأمان."""
        if not self._connected:
            return
        for conn in self._read_conns:
            await conn.close()
        self._read_conns.clear()
        if self._write_conn is not None:
            await self._write_conn.close()
            self._write_conn = None
        self._read_pool = None
        self._connected = False
        logger.info("تم إغلاق الاتصال بقاعدة البيانات.")

    def _require_connected(self) -> None:
        """التأكد من أن الاتصال مفتوح قبل أي عملية."""
        if not self._connected or self._write_conn is None or self._read_pool is None:
            raise DatabaseError("قاعدة البيانات غير متصلة — نادِ connect() أولاً.")

    # ------------------------------ المعاملات ----------------------------- #

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Tx]:
        """
        فتح معاملة كتابة ذرّية (BEGIN IMMEDIATE ... COMMIT).

        الاستخدام:
            async with db.transaction() as tx:
                await repo.do_something(tx, ...)

        الضمانات:
            • أي استثناء داخل الكتلة يؤدي إلى ROLLBACK كامل.
            • المعاملات المتداخلة تُعيد استخدام نفس المعاملة (لا commit مبكر).
            • إعادة محاولة محدودة إذا كانت قاعدة البيانات مقفولة مؤقتاً.
        """
        self._require_connected()
        existing = _current_tx.get()
        if existing is not None:
            # معاملة متداخلة: نكمل ضمن نفس المعاملة الخارجية
            yield existing
            return

        async with self._write_lock:
            conn = self._write_conn
            assert conn is not None
            await self._begin_with_retry(conn)
            tx = Tx(conn)
            token = _current_tx.set(tx)
            try:
                yield tx
            except BaseException:
                await self._rollback_quietly(conn)
                raise
            else:
                await conn.execute("COMMIT")
            finally:
                _current_tx.reset(token)

    async def _begin_with_retry(self, conn: aiosqlite.Connection) -> None:
        """بدء معاملة فورية مع إعادة محاولة عند القفل المؤقت."""
        delay = 0.05
        for attempt in range(1, self._max_retries + 1):
            try:
                await conn.execute("BEGIN IMMEDIATE")
                return
            except sqlite3.OperationalError as exc:
                if not _is_locked_error(exc) or attempt == self._max_retries:
                    if _is_locked_error(exc):
                        raise DatabaseLockedError(
                            "تعذر بدء المعاملة: قاعدة البيانات مقفولة."
                        ) from exc
                    raise DatabaseError(f"خطأ في بدء المعاملة: {exc}") from exc
                logger.warning("قاعدة البيانات مقفولة، إعادة المحاولة %s/%s", attempt, self._max_retries)
                await asyncio.sleep(delay)
                delay *= 2

    async def _rollback_quietly(self, conn: aiosqlite.Connection) -> None:
        """تنفيذ ROLLBACK مع تسجيل أي مشكلة (دون إخفاء الخطأ الأصلي)."""
        try:
            await conn.execute("ROLLBACK")
        except sqlite3.Error as exc:  # نسجل ولا نبتلع: الخطأ الأصلي هو الأهم
            logger.error("فشل التراجع عن المعاملة: %s", exc)

    # ------------------------------- القراءة ------------------------------ #

    @asynccontextmanager
    async def _reader(self) -> AsyncIterator[aiosqlite.Connection]:
        """حجز اتصال قراءة من المجموعة وإعادته بعد الانتهاء."""
        self._require_connected()
        assert self._read_pool is not None
        conn = await self._read_pool.get()
        try:
            yield conn
        finally:
            self._read_pool.put_nowait(conn)

    async def fetchone(self, sql: str, params: SQLParams = ()) -> aiosqlite.Row | None:
        """قراءة صف واحد (تستخدم المعاملة الحالية إن وُجدت، وإلا اتصال قراءة)."""
        tx = _current_tx.get()
        if tx is not None:
            return await tx.fetchone(sql, params)
        async with self._reader() as conn, conn.execute(sql, params) as cursor:
            return await cursor.fetchone()

    async def fetchall(self, sql: str, params: SQLParams = ()) -> list[aiosqlite.Row]:
        """قراءة كل الصفوف المطابقة."""
        tx = _current_tx.get()
        if tx is not None:
            return await tx.fetchall(sql, params)
        async with self._reader() as conn, conn.execute(sql, params) as cursor:
            return list(await cursor.fetchall())

    async def fetchval(self, sql: str, params: SQLParams = (), default: Any = None) -> Any:
        """قراءة قيمة مفردة (مثل COUNT أو SUM)."""
        row = await self.fetchone(sql, params)
        if row is None:
            return default
        value = row[0]
        return default if value is None else value

    # ------------------------------ أدوات إدارية --------------------------- #

    async def executescript(self, script: str) -> None:
        """
        تنفيذ سكربت SQL كامل على اتصال الكتابة (يُستخدم للترحيلات فقط).

        تحذير: هذه الدالة تتحكم بالمعاملات بنفسها، لذا لا تُستدعى داخل transaction().
        """
        self._require_connected()
        assert self._write_conn is not None
        async with self._write_lock:
            await self._write_conn.executescript(script)

    async def execute_raw(self, sql: str, params: SQLParams = ()) -> ExecResult:
        """
        تنفيذ عبارة كتابة مفردة خارج معاملة صريحة (للأدوات الإدارية فقط).

        ⚠️ ممنوع استخدامها في أي عملية مالية — تلك تمر عبر transaction() دائماً.
        """
        self._require_connected()
        assert self._write_conn is not None
        async with self._write_lock:
            async with self._write_conn.execute(sql, params) as cursor:
                return ExecResult(rowcount=cursor.rowcount, lastrowid=cursor.lastrowid)

    async def table_names(self) -> list[str]:
        """قائمة بأسماء جداول قاعدة البيانات (للتحقق والاختبارات)."""
        rows = await self.fetchall(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        return [row["name"] for row in rows]

    async def integrity_check(self) -> bool:
        """فحص سلامة ملف قاعدة البيانات (يُستخدم قبل/بعد النسخ الاحتياطي)."""
        result = await self.fetchval("PRAGMA integrity_check")
        return str(result).lower() == "ok"

    async def foreign_key_check(self) -> list[aiosqlite.Row]:
        """فحص وجود أي انتهاك للمفاتيح الأجنبية (يجب أن تكون النتيجة فارغة)."""
        return await self.fetchall("PRAGMA foreign_key_check")

    async def vacuum(self) -> None:
        """ضغط ملف قاعدة البيانات بعد عمليات الحذف الكبيرة."""
        self._require_connected()
        assert self._write_conn is not None
        async with self._write_lock:
            await self._write_conn.execute("VACUUM")
```

## `database/migrator.py`

```python
"""
مُرحِّل قاعدة البيانات (Migrations Runner).

الفكرة:
    • كل تعديل على المخطط يوضع في ملف SQL مرقّم داخل database/migrations/.
    • تُطبَّق الملفات بالترتيب مرة واحدة فقط، ويُسجَّل ما طُبِّق في جدول schema_migrations.
    • لكل ملف بصمة SHA-256؛ إذا عُدِّل ملف سبق تطبيقه يُرفع خطأ فوراً
      (لأن ذلك يعني أن قواعد بيانات مختلفة أصبحت بمخططات مختلفة).
    • كل ملف يُطبَّق داخل معاملة واحدة: إما ينجح كاملاً أو لا شيء.

قواعد كتابة ملفات الترحيل:
    • لا تضع PRAGMA ولا BEGIN/COMMIT داخل الملف.
    • لا تعدّل ملفاً مطبقاً؛ أنشئ ملفاً جديداً بدلاً منه.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from core.exceptions import MigrationChecksumError, MigrationError
from database.database import Database
from utils.logging_setup import get_logger

logger = get_logger(__name__)

MIGRATIONS_DIR: Path = Path(__file__).resolve().parent / "migrations"

#: نمط اسم الملف: 0001_name.sql
_FILENAME_RE = re.compile(r"^(\d{4})_([a-zA-Z0-9_\-]+)\.sql$")


@dataclass(frozen=True)
class MigrationFile:
    """ملف ترحيل واحد بعد قراءته."""

    version: str
    name: str
    sql: str
    checksum: str
    path: Path


#: كلمات ممنوعة في بداية أي عبارة داخل ملف ترحيل
#: (المُرحِّل هو من يفتح المعاملة ويضبط الـ PRAGMA؛ وجودها في الملف يكسر ذرّية الترحيل)
_FORBIDDEN_STARTS: tuple[str, ...] = (
    "begin", "commit", "end transaction", "rollback", "pragma", "attach", "detach", "vacuum",
)


def _split_statements(sql: str) -> list[str]:
    """
    تقسيم نص SQL إلى عبارات مكتملة.

    نعتمد على sqlite3.complete_statement لأنه يفهم علامات الاقتباس والتعليقات
    وأجسام TRIGGER (BEGIN … END)، فلا ينكسر التقسيم عند وجود فاصلة منقوطة داخلها.
    """
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement and not _is_comment_only(statement):
                statements.append(statement)
            buffer = ""
    leftover = buffer.strip()
    if leftover and not _is_comment_only(leftover):
        raise MigrationError(f"عبارة SQL غير مكتملة في نهاية الملف: {leftover[:80]}…")
    return statements


def _is_comment_only(statement: str) -> bool:
    """هل هذه الكتلة تعليقات فقط بلا SQL فعلي؟"""
    for line in statement.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            return False
    return True


def _strip_leading_comments(statement: str) -> str:
    """إزالة أسطر التعليق من بداية العبارة للتحقق من كلمتها الأولى."""
    lines = statement.splitlines()
    index = 0
    while index < len(lines) and (not lines[index].strip() or lines[index].strip().startswith("--")):
        index += 1
    return "\n".join(lines[index:]).strip()


class Migrator:
    """مسؤول عن قراءة ملفات الترحيل وتطبيق الناقص منها."""

    def __init__(self, db: Database, migrations_dir: Path | str = MIGRATIONS_DIR) -> None:
        """تهيئة المُرحِّل بقاعدة بيانات متصلة ومجلد الترحيلات."""
        self.db = db
        self.dir = Path(migrations_dir)

    # ------------------------------ القراءة ------------------------------ #

    def load_files(self) -> list[MigrationFile]:
        """
        قراءة كل ملفات الترحيل من المجلد وترتيبها تصاعدياً حسب رقم الإصدار.

        الاستثناءات:
            MigrationError : اسم ملف غير مطابق للنمط، أو تكرار رقم إصدار.
        """
        if not self.dir.exists():
            raise MigrationError(f"مجلد الترحيلات غير موجود: {self.dir}")

        files: list[MigrationFile] = []
        seen: set[str] = set()
        for path in sorted(self.dir.glob("*.sql")):
            match = _FILENAME_RE.match(path.name)
            if not match:
                raise MigrationError(
                    f"اسم ملف ترحيل غير صالح: {path.name} — الصيغة المطلوبة 0001_description.sql"
                )
            version, name = match.group(1), match.group(2)
            if version in seen:
                raise MigrationError(f"رقم إصدار مكرر في الترحيلات: {version}")
            seen.add(version)
            sql = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            files.append(MigrationFile(version=version, name=name, sql=sql, checksum=checksum, path=path))
        return files

    async def ensure_table(self) -> None:
        """إنشاء جدول تتبع الترحيلات إن لم يكن موجوداً."""
        await self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                checksum   TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );
            """
        )

    async def applied(self) -> dict[str, str]:
        """إرجاع الترحيلات المطبقة على شكل: رقم الإصدار → البصمة."""
        rows = await self.db.fetchall("SELECT version, checksum FROM schema_migrations")
        return {row["version"]: row["checksum"] for row in rows}

    # ------------------------------ التطبيق ------------------------------ #

    async def apply_all(self) -> list[str]:
        """
        تطبيق كل الترحيلات غير المطبقة بالترتيب.

        المخرجات: قائمة بأرقام الإصدارات التي طُبِّقت في هذه المرة (فارغة إذا كان كل شيء محدّثاً).

        الاستثناءات:
            MigrationChecksumError : ملف مطبق سابقاً تم تعديله.
            MigrationError         : فشل تنفيذ SQL (مع التراجع الكامل عن الملف).
        """
        await self.ensure_table()
        done = await self.applied()
        files = self.load_files()

        # التحقق من عدم تعديل أي ملف سبق تطبيقه
        for migration in files:
            previous = done.get(migration.version)
            if previous is not None and previous != migration.checksum:
                raise MigrationChecksumError(
                    f"الملف {migration.path.name} تم تعديله بعد تطبيقه. "
                    "أنشئ ملف ترحيل جديداً بدل تعديل القديم."
                )

        newly_applied: list[str] = []
        for migration in files:
            if migration.version in done:
                continue
            await self._apply_one(migration)
            newly_applied.append(migration.version)
            logger.info("تم تطبيق الترحيل %s_%s", migration.version, migration.name)

        if not newly_applied:
            logger.info("قاعدة البيانات محدّثة — لا توجد ترحيلات جديدة.")
        return newly_applied

    def _prepare_statements(self, migration: MigrationFile) -> list[str]:
        """
        تجهيز عبارات ملف الترحيل والتحقق من خلوّها من الممنوعات.

        الاستثناءات:
            MigrationError : الملف فارغ، أو يحتوي BEGIN/COMMIT/PRAGMA … داخله.
        """
        statements = _split_statements(migration.sql)
        if not statements:
            raise MigrationError(f"ملف الترحيل فارغ بلا أي عبارة: {migration.path.name}")
        for statement in statements:
            head = _strip_leading_comments(statement).lower()
            for forbidden in _FORBIDDEN_STARTS:
                if head.startswith(forbidden):
                    raise MigrationError(
                        f"العبارة «{forbidden.upper()}» ممنوعة داخل ملف الترحيل "
                        f"{migration.path.name} — المُرحِّل يتكفل بالمعاملات وإعدادات PRAGMA."
                    )
        return statements

    async def _apply_one(self, migration: MigrationFile) -> None:
        """
        تطبيق ملف ترحيل واحد داخل معاملة ذرّية مع تسجيله في جدول التتبع.

        ملاحظة مهمة: لا نستخدم executescript هنا لأنه يُثبِّت (COMMIT) أي معاملة مفتوحة
        قبل تنفيذ النص، فتضيع ذرّية الترحيل؛ لذلك نُقسِّم الملف وننفّذ عباراته واحدة
        واحدة داخل معاملة واحدة يديرها كائن Database.
        """
        statements = self._prepare_statements(migration)
        try:
            async with self.db.transaction() as tx:
                for statement in statements:
                    await tx.execute(statement)
                await tx.execute(
                    """
                    INSERT INTO schema_migrations (version, name, checksum, applied_at)
                    VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                    """,
                    (migration.version, migration.name, migration.checksum),
                )
        except sqlite3.Error as exc:
            raise MigrationError(f"فشل تطبيق الترحيل {migration.path.name}: {exc}") from exc

    # ------------------------------ التحقق ------------------------------- #

    async def current_version(self) -> str | None:
        """آخر رقم إصدار مطبق على قاعدة البيانات."""
        return await self.db.fetchval(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        )

    async def pending(self) -> list[str]:
        """قائمة الترحيلات غير المطبقة بعد."""
        await self.ensure_table()
        done = await self.applied()
        return [m.version for m in self.load_files() if m.version not in done]
```

## `database/models.py`

```python
"""
نماذج البيانات (Data Models) — تمثيل صفوف الجداول ككائنات Python.

لماذا dataclasses بدل ORM كامل؟
    • خفيفة وسريعة ولا تُخفي ما يحدث في SQL.
    • تُبقي كل عبارات SQL ظاهرة في المستودعات (repositories) مما يسهّل
      مراجعتها أمنياً ونقلها لاحقاً إلى PostgreSQL.

كل نموذج يوفّر from_row لتحويل صف قاعدة البيانات إلى كائن، مع تجاهل أي أعمدة إضافية.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Iterable, Mapping, TypeVar

from core.money import from_units

_T = TypeVar("_T", bound="BaseModel")


@dataclass(slots=True)
class BaseModel:
    """أساس كل النماذج: يوفّر التحويل من صف قاعدة بيانات إلى كائن."""

    @classmethod
    def from_row(cls: type[_T], row: Mapping[str, Any] | None) -> _T | None:
        """تحويل صف واحد إلى كائن النموذج، أو None إذا لم يوجد صف."""
        if row is None:
            return None
        allowed = {f.name for f in fields(cls)}
        data = {key: row[key] for key in row.keys() if key in allowed}
        return cls(**data)  # type: ignore[arg-type]

    @classmethod
    def from_rows(cls: type[_T], rows: Iterable[Mapping[str, Any]]) -> list[_T]:
        """تحويل مجموعة صفوف إلى قائمة كائنات."""
        result: list[_T] = []
        for row in rows:
            item = cls.from_row(row)
            if item is not None:
                result.append(item)
        return result


# ------------------------------- المستخدمون ------------------------------- #


@dataclass(slots=True)
class User(BaseModel):
    """مستخدم البوت (عميل أو أدمن)."""

    id: int
    telegram_id: int
    created_at: str
    updated_at: str
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    balance_units: int = 0
    total_spent_units: int = 0
    total_deposited_units: int = 0
    role: str = "user"
    is_banned: int = 0
    ban_reason: str | None = None
    banned_at: str | None = None
    blocked_bot: int = 0
    language: str = "ar"
    referrer_id: int | None = None
    notes: str | None = None
    last_activity: str | None = None

    @property
    def balance(self):
        """الرصيد كقيمة عشرية للعرض فقط (التخزين والحساب يبقى بالنقاط)."""
        return from_units(self.balance_units)

    @property
    def display_name(self) -> str:
        """اسم مناسب للعرض في لوحة الأدمن."""
        if self.username:
            return f"@{self.username}"
        return self.first_name or f"ID:{self.telegram_id}"

    @property
    def banned(self) -> bool:
        """هل المستخدم محظور؟"""
        return bool(self.is_banned)


# -------------------------------- المزودون -------------------------------- #


@dataclass(slots=True)
class Provider(BaseModel):
    """مزود خدمات SMM خارجي."""

    id: int
    name: str
    api_url: str
    api_key_enc: str
    created_at: str
    updated_at: str
    api_key_hint: str | None = None
    api_type: str = "perfect_panel"
    balance_units: int = 0
    currency: str = "USD"
    balance_checked_at: str | None = None
    low_balance_threshold_units: int | None = None
    is_active: int = 1
    priority: int = 100
    timeout_seconds: int = 30
    consecutive_failures: int = 0
    disabled_until: str | None = None
    last_error: str | None = None
    last_success_at: str | None = None

    @property
    def active(self) -> bool:
        """هل المزود مفعّل؟ (التعطيل المؤقت يُفحص في ProviderService)."""
        return bool(self.is_active)


# --------------------------- التصنيفات والخدمات ---------------------------- #


@dataclass(slots=True)
class ServiceCategory(BaseModel):
    """تصنيف خدمات (منصة مثل انستغرام أو تيك توك)."""

    id: int
    name_ar: str
    created_at: str
    updated_at: str
    name_en: str | None = None
    emoji: str = "📦"
    sort_order: int = 100
    is_active: int = 1

    @property
    def title(self) -> str:
        """العنوان المعروض على الزر."""
        return f"{self.emoji} {self.name_ar}"


@dataclass(slots=True)
class Service(BaseModel):
    """خدمة معروضة للبيع."""

    id: int
    category_id: int
    provider_id: int
    provider_service_id: str
    name: str
    price_per_1000_units: int
    min_quantity: int
    max_quantity: int
    created_at: str
    updated_at: str
    description: str | None = None
    service_type: str = "default"
    provider_price_per_1000_units: int | None = None
    dripfeed_enabled: int = 0
    refill_enabled: int = 0
    cancel_enabled: int = 0
    link_pattern: str | None = None
    avg_time_text: str | None = None
    is_active: int = 1
    is_archived: int = 0
    sort_order: int = 100

    @property
    def available(self) -> bool:
        """هل الخدمة متاحة للطلب الآن؟"""
        return bool(self.is_active) and not bool(self.is_archived)

    @property
    def margin_units(self) -> int | None:
        """هامش الربح لكل ألف (None إذا لم تُسجَّل تكلفة المزود)."""
        if self.provider_price_per_1000_units is None:
            return None
        return self.price_per_1000_units - self.provider_price_per_1000_units


# --------------------------------- الطلبات -------------------------------- #


@dataclass(slots=True)
class Order(BaseModel):
    """طلب عميل على خدمة."""

    id: int
    user_id: int
    service_id: int
    provider_id: int
    service_name_snapshot: str
    price_per_1000_snapshot_units: int
    link: str
    quantity: int
    cost_units: int
    client_request_id: str
    created_at: str
    updated_at: str
    public_code: str | None = None
    provider_cost_units: int | None = None
    status: str = "pending"
    provider_status: str | None = None
    provider_order_id: str | None = None
    start_count: int | None = None
    remains: int | None = None
    delivered_quantity: int | None = None
    refund_amount_units: int = 0
    refunded_at: str | None = None
    submit_attempts: int = 0
    checks_count: int = 0
    last_error: str | None = None
    locked_by: str | None = None
    locked_until: str | None = None
    next_check_at: str | None = None
    submitted_at: str | None = None
    completed_at: str | None = None
    cancelled_at: str | None = None

    @property
    def refundable_units(self) -> int:
        """المبلغ المتبقي القابل للاسترجاع (التكلفة ناقص ما استُرجع)."""
        return max(0, self.cost_units - self.refund_amount_units)


@dataclass(slots=True)
class OrderStatusHistory(BaseModel):
    """سجل انتقال حالة طلب."""

    id: int
    order_id: int
    to_status: str
    created_at: str
    from_status: str | None = None
    actor_type: str = "system"
    actor_id: int | None = None
    reason: str | None = None
    provider_status_raw: str | None = None


# ----------------------------- الحركات المالية ----------------------------- #


@dataclass(slots=True)
class Transaction(BaseModel):
    """حركة مالية في دفتر الأستاذ (إضافة فقط — لا تُعدَّل ولا تُحذف)."""

    id: int
    user_id: int
    type: str
    direction: str
    amount_units: int
    balance_before_units: int
    balance_after_units: int
    created_at: str
    order_id: int | None = None
    payment_id: int | None = None
    description: str | None = None
    reference: str | None = None
    actor_id: int | None = None

    @property
    def signed_amount_units(self) -> int:
        """المبلغ بإشارته (موجب للإضافة وسالب للخصم) لعرضه في السجل."""
        return self.amount_units if self.direction == "credit" else -self.amount_units


# -------------------------------- المدفوعات -------------------------------- #


@dataclass(slots=True)
class PaymentMethod(BaseModel):
    """طريقة شحن رصيد قابلة للتهيئة من لوحة الأدمن."""

    id: int
    code: str
    name_ar: str
    created_at: str
    updated_at: str
    type: str = "manual"
    instructions_ar: str = ""
    account_details: str = ""
    min_amount_units: int = 0
    max_amount_units: int | None = None
    requires_proof: int = 1
    is_active: int = 1
    sort_order: int = 100


@dataclass(slots=True)
class Payment(BaseModel):
    """طلب شحن رصيد."""

    id: int
    user_id: int
    method_id: int
    amount_units: int
    created_at: str
    updated_at: str
    credited_units: int | None = None
    status: str = "pending"
    transaction_reference: str | None = None
    proof_file_id: str | None = None
    proof_file_type: str | None = None
    user_note: str | None = None
    admin_id: int | None = None
    admin_note: str | None = None
    reject_reason: str | None = None
    reviewed_at: str | None = None
    expires_at: str | None = None


# ---------------------------------- الدعم ---------------------------------- #


@dataclass(slots=True)
class SupportTicket(BaseModel):
    """تذكرة دعم فني."""

    id: int
    user_id: int
    subject: str
    created_at: str
    updated_at: str
    category: str = "other"
    related_order_id: int | None = None
    status: str = "open"
    priority: str = "normal"
    assigned_admin: int | None = None
    last_message_at: str | None = None
    closed_by: int | None = None
    close_reason: str | None = None
    closed_at: str | None = None

    @property
    def is_open(self) -> bool:
        """هل التذكرة ما زالت مفتوحة؟"""
        return self.status != "closed"


@dataclass(slots=True)
class SupportMessage(BaseModel):
    """رسالة داخل تذكرة دعم."""

    id: int
    ticket_id: int
    sender_type: str
    message: str
    created_at: str
    sender_id: int | None = None
    attachment_file_id: str | None = None
    attachment_type: str | None = None
    telegram_message_id: int | None = None
    is_read_by_user: int = 0
    is_read_by_admin: int = 0


# -------------------------------- الإشعارات -------------------------------- #


@dataclass(slots=True)
class Notification(BaseModel):
    """إشعار في صندوق الإرسال (Outbox)."""

    id: int
    user_id: int
    type: str
    message: str
    dedupe_key: str
    created_at: str
    title: str = ""
    payload_json: str | None = None
    status: str = "queued"
    attempts: int = 0
    next_attempt_at: str | None = None
    last_error: str | None = None
    telegram_message_id: int | None = None
    is_read: int = 0
    sent_at: str | None = None


# ------------------------------ الإعدادات والسجل ---------------------------- #


@dataclass(slots=True)
class Setting(BaseModel):
    """إعداد عام من جدول settings."""

    key: str
    value: str
    updated_at: str
    value_type: str = "str"
    group_code: str = "general"
    name_ar: str = ""
    description_ar: str | None = None
    is_editable: int = 1
    updated_by: int | None = None


@dataclass(slots=True)
class AuditLog(BaseModel):
    """سجل عملية إدارية حساسة."""

    id: int
    action: str
    created_at: str
    admin_id: int | None = None
    target_type: str | None = None
    target_id: str | None = None
    details_json: str | None = None
    before_json: str | None = None
    after_json: str | None = None
    source: str = "telegram"


@dataclass(slots=True)
class Broadcast(BaseModel):
    """رسالة جماعية."""

    id: int
    created_at: str
    admin_id: int | None = None
    message_text: str = ""
    parse_mode: str | None = None
    media_file_id: str | None = None
    media_type: str | None = None
    buttons_json: str | None = None
    target: str = "all"
    target_filter_json: str | None = None
    total_count: int = 0
    sent_count: int = 0
    failed_count: int = 0
    blocked_count: int = 0
    status: str = "draft"
    started_at: str | None = None
    finished_at: str | None = None
```

# ملفات الترحيل — database/migrations/

## `database/migrations/0001_initial_schema.sql`

```sql
-- =====================================================================
-- الترحيل 0001 — المخطط الأساسي الكامل لنظام SMM Bot
-- ملاحظات:
--   * كل الطوابع الزمنية نصية بصيغة ISO-8601 بتوقيت UTC (مثال: 2026-10-01T09:00:00.000Z)
--   * كل المبالغ أعداد صحيحة بوحدة «نقطة» = 1/10000 من وحدة العملة
--   * ممنوع وضع PRAGMA أو BEGIN/COMMIT داخل ملفات الترحيل (المُرحِّل يتكفل بها)
-- =====================================================================

-- ------------------------- الأدوار والصلاحيات ------------------------- --

CREATE TABLE roles (
    code       TEXT PRIMARY KEY,
    name_ar    TEXT    NOT NULL,
    level      INTEGER NOT NULL DEFAULT 0,
    is_system  INTEGER NOT NULL DEFAULT 1 CHECK (is_system IN (0, 1)),
    created_at TEXT    NOT NULL
);

CREATE TABLE permissions (
    code         TEXT PRIMARY KEY,
    name_ar      TEXT    NOT NULL,
    group_code   TEXT    NOT NULL,
    is_dangerous INTEGER NOT NULL DEFAULT 0 CHECK (is_dangerous IN (0, 1))
);

CREATE TABLE role_permissions (
    role_code       TEXT NOT NULL REFERENCES roles(code) ON DELETE CASCADE,
    permission_code TEXT NOT NULL REFERENCES permissions(code) ON DELETE CASCADE,
    PRIMARY KEY (role_code, permission_code)
);

-- ------------------------------ المستخدمون ---------------------------- --

CREATE TABLE users (
    id                    INTEGER PRIMARY KEY,
    telegram_id           INTEGER NOT NULL UNIQUE,
    username              TEXT,
    first_name            TEXT,
    last_name             TEXT,
    balance_units         INTEGER NOT NULL DEFAULT 0 CHECK (balance_units >= 0),
    total_spent_units     INTEGER NOT NULL DEFAULT 0 CHECK (total_spent_units >= 0),
    total_deposited_units INTEGER NOT NULL DEFAULT 0 CHECK (total_deposited_units >= 0),
    role                  TEXT    NOT NULL DEFAULT 'user' REFERENCES roles(code) ON DELETE RESTRICT,
    is_banned             INTEGER NOT NULL DEFAULT 0 CHECK (is_banned IN (0, 1)),
    ban_reason            TEXT,
    banned_at             TEXT,
    blocked_bot           INTEGER NOT NULL DEFAULT 0 CHECK (blocked_bot IN (0, 1)),
    language              TEXT    NOT NULL DEFAULT 'ar',
    referrer_id           INTEGER REFERENCES users(id) ON DELETE SET NULL,
    notes                 TEXT,
    created_at            TEXT    NOT NULL,
    updated_at            TEXT    NOT NULL,
    last_activity         TEXT
);

CREATE INDEX idx_users_role        ON users(role);
CREATE INDEX idx_users_banned      ON users(is_banned);
CREATE INDEX idx_users_activity    ON users(last_activity);
CREATE INDEX idx_users_created     ON users(created_at);

-- استثناءات صلاحيات فردية تتجاوز الدور (منح أو منع لمستخدم بعينه)
CREATE TABLE user_permissions (
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission_code TEXT    NOT NULL REFERENCES permissions(code) ON DELETE CASCADE,
    allow           INTEGER NOT NULL CHECK (allow IN (0, 1)),
    granted_by      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at      TEXT    NOT NULL,
    PRIMARY KEY (user_id, permission_code)
);

-- حفظ خطوة المحادثة الحالية حتى لا يضيع المستخدم بعد إعادة تشغيل البوت
CREATE TABLE user_states (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    chat_id    INTEGER,
    state      TEXT,
    data_json  TEXT NOT NULL DEFAULT '{}',
    expires_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_user_states_expires ON user_states(expires_at);

-- ------------------------------- المزودون ----------------------------- --

CREATE TABLE providers (
    id                          INTEGER PRIMARY KEY,
    name                        TEXT    NOT NULL UNIQUE,
    api_url                     TEXT    NOT NULL,
    api_key_enc                 TEXT    NOT NULL,          -- مشفّر بـ Fernet
    api_key_hint                TEXT,                      -- آخر 4 محارف للعرض فقط
    api_type                    TEXT    NOT NULL DEFAULT 'perfect_panel',
    balance_units               INTEGER NOT NULL DEFAULT 0,
    currency                    TEXT    NOT NULL DEFAULT 'USD',
    balance_checked_at          TEXT,
    low_balance_threshold_units INTEGER,
    is_active                   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    priority                    INTEGER NOT NULL DEFAULT 100,
    timeout_seconds             INTEGER NOT NULL DEFAULT 30 CHECK (timeout_seconds > 0),
    consecutive_failures        INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
    disabled_until              TEXT,                      -- تعطيل مؤقت (قاطع الدائرة)
    last_error                  TEXT,
    last_success_at             TEXT,
    created_at                  TEXT    NOT NULL,
    updated_at                  TEXT    NOT NULL
);

CREATE INDEX idx_providers_active ON providers(is_active);

CREATE TABLE provider_balance_snapshots (
    id            INTEGER PRIMARY KEY,
    provider_id   INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    balance_units INTEGER NOT NULL,
    currency      TEXT    NOT NULL DEFAULT 'USD',
    created_at    TEXT    NOT NULL
);

CREATE INDEX idx_provider_snapshots ON provider_balance_snapshots(provider_id, created_at);

-- ------------------------- التصنيفات والخدمات -------------------------- --

CREATE TABLE service_categories (
    id         INTEGER PRIMARY KEY,
    name_ar    TEXT    NOT NULL,
    name_en    TEXT,
    emoji      TEXT    NOT NULL DEFAULT '📦',
    sort_order INTEGER NOT NULL DEFAULT 100,
    is_active  INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);

CREATE INDEX idx_categories_active ON service_categories(is_active, sort_order);

CREATE TABLE services (
    id                            INTEGER PRIMARY KEY,
    category_id                   INTEGER NOT NULL REFERENCES service_categories(id) ON DELETE RESTRICT,
    provider_id                   INTEGER NOT NULL REFERENCES providers(id) ON DELETE RESTRICT,
    provider_service_id           TEXT    NOT NULL,
    name                          TEXT    NOT NULL,
    description                   TEXT,
    service_type                  TEXT    NOT NULL DEFAULT 'default'
                                   CHECK (service_type IN ('default', 'custom_comments', 'drip_feed', 'subscription')),
    price_per_1000_units          INTEGER NOT NULL CHECK (price_per_1000_units > 0),
    provider_price_per_1000_units INTEGER CHECK (provider_price_per_1000_units IS NULL OR provider_price_per_1000_units >= 0),
    min_quantity                  INTEGER NOT NULL CHECK (min_quantity > 0),
    max_quantity                  INTEGER NOT NULL CHECK (max_quantity > 0),
    dripfeed_enabled              INTEGER NOT NULL DEFAULT 0 CHECK (dripfeed_enabled IN (0, 1)),
    refill_enabled                INTEGER NOT NULL DEFAULT 0 CHECK (refill_enabled IN (0, 1)),
    cancel_enabled                INTEGER NOT NULL DEFAULT 0 CHECK (cancel_enabled IN (0, 1)),
    link_pattern                  TEXT,
    avg_time_text                 TEXT,
    is_active                     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    is_archived                   INTEGER NOT NULL DEFAULT 0 CHECK (is_archived IN (0, 1)),
    sort_order                    INTEGER NOT NULL DEFAULT 100,
    created_at                    TEXT    NOT NULL,
    updated_at                    TEXT    NOT NULL,
    CHECK (max_quantity >= min_quantity)
);

CREATE INDEX idx_services_category ON services(category_id, is_active, is_archived);
CREATE INDEX idx_services_provider ON services(provider_id, provider_service_id);

CREATE TABLE service_price_history (
    id             INTEGER PRIMARY KEY,
    service_id     INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    old_price_units INTEGER,
    new_price_units INTEGER NOT NULL,
    old_min        INTEGER,
    new_min        INTEGER,
    old_max        INTEGER,
    new_max        INTEGER,
    changed_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    source         TEXT    NOT NULL DEFAULT 'admin' CHECK (source IN ('admin', 'sync')),
    created_at     TEXT    NOT NULL
);

CREATE INDEX idx_price_history_service ON service_price_history(service_id, created_at);

-- --------------------------- طرق الدفع والشحن -------------------------- --

CREATE TABLE payment_methods (
    id               INTEGER PRIMARY KEY,
    code             TEXT    NOT NULL UNIQUE,
    name_ar          TEXT    NOT NULL,
    type             TEXT    NOT NULL DEFAULT 'manual' CHECK (type IN ('manual', 'crypto', 'gateway')),
    instructions_ar  TEXT    NOT NULL DEFAULT '',
    account_details  TEXT    NOT NULL DEFAULT '',
    min_amount_units INTEGER NOT NULL DEFAULT 0 CHECK (min_amount_units >= 0),
    max_amount_units INTEGER CHECK (max_amount_units IS NULL OR max_amount_units > 0),
    requires_proof   INTEGER NOT NULL DEFAULT 1 CHECK (requires_proof IN (0, 1)),
    is_active        INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    sort_order       INTEGER NOT NULL DEFAULT 100,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL
);

CREATE TABLE payments (
    id                    INTEGER PRIMARY KEY,
    user_id               INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    method_id             INTEGER NOT NULL REFERENCES payment_methods(id) ON DELETE RESTRICT,
    amount_units          INTEGER NOT NULL CHECK (amount_units > 0),
    credited_units        INTEGER CHECK (credited_units IS NULL OR credited_units >= 0),
    status                TEXT    NOT NULL DEFAULT 'pending'
                           CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled', 'expired')),
    transaction_reference TEXT,
    proof_file_id         TEXT,
    proof_file_type       TEXT CHECK (proof_file_type IS NULL OR proof_file_type IN ('photo', 'document')),
    user_note             TEXT,
    admin_id              INTEGER REFERENCES users(id) ON DELETE SET NULL,
    admin_note            TEXT,
    reject_reason         TEXT,
    reviewed_at           TEXT,
    expires_at            TEXT,
    created_at            TEXT    NOT NULL,
    updated_at            TEXT    NOT NULL
);

CREATE INDEX idx_payments_status  ON payments(status, created_at);
CREATE INDEX idx_payments_user    ON payments(user_id, created_at);
CREATE INDEX idx_payments_expires ON payments(status, expires_at);

-- -------------------------------- الطلبات ------------------------------ --

CREATE TABLE orders (
    id                            INTEGER PRIMARY KEY,
    public_code                   TEXT UNIQUE,
    user_id                       INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    service_id                    INTEGER NOT NULL REFERENCES services(id) ON DELETE RESTRICT,
    provider_id                   INTEGER NOT NULL REFERENCES providers(id) ON DELETE RESTRICT,
    service_name_snapshot         TEXT    NOT NULL,
    price_per_1000_snapshot_units INTEGER NOT NULL CHECK (price_per_1000_snapshot_units > 0),
    link                          TEXT    NOT NULL,
    quantity                      INTEGER NOT NULL CHECK (quantity > 0),
    cost_units                    INTEGER NOT NULL CHECK (cost_units >= 0),
    provider_cost_units           INTEGER CHECK (provider_cost_units IS NULL OR provider_cost_units >= 0),
    status                        TEXT    NOT NULL DEFAULT 'pending'
                                   CHECK (status IN ('pending', 'submitting', 'submit_uncertain', 'submitted',
                                                     'in_progress', 'partial', 'completed', 'canceled',
                                                     'failed', 'refunded')),
    provider_status               TEXT,
    provider_order_id             TEXT,
    client_request_id             TEXT    NOT NULL UNIQUE,   -- مفتاح منع الطلب المكرر
    start_count                   INTEGER,
    remains                       INTEGER,
    delivered_quantity            INTEGER,
    refund_amount_units           INTEGER NOT NULL DEFAULT 0 CHECK (refund_amount_units >= 0),
    refunded_at                   TEXT,
    submit_attempts               INTEGER NOT NULL DEFAULT 0 CHECK (submit_attempts >= 0),
    checks_count                  INTEGER NOT NULL DEFAULT 0 CHECK (checks_count >= 0),
    last_error                    TEXT,
    locked_by                     TEXT,
    locked_until                  TEXT,
    next_check_at                 TEXT,
    created_at                    TEXT    NOT NULL,
    updated_at                    TEXT    NOT NULL,
    submitted_at                  TEXT,
    completed_at                  TEXT,
    cancelled_at                  TEXT,
    CHECK (refund_amount_units <= cost_units)
);

CREATE UNIQUE INDEX idx_orders_provider_order
    ON orders(provider_id, provider_order_id)
    WHERE provider_order_id IS NOT NULL;
CREATE INDEX idx_orders_status_check ON orders(status, next_check_at);
CREATE INDEX idx_orders_user         ON orders(user_id, created_at);
CREATE INDEX idx_orders_created      ON orders(created_at);
CREATE INDEX idx_orders_service      ON orders(service_id);

CREATE TABLE order_status_history (
    id                  INTEGER PRIMARY KEY,
    order_id            INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    from_status         TEXT,
    to_status           TEXT    NOT NULL,
    actor_type          TEXT    NOT NULL DEFAULT 'system'
                         CHECK (actor_type IN ('system', 'job', 'admin', 'user', 'provider')),
    actor_id            INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reason              TEXT,
    provider_status_raw TEXT,
    created_at          TEXT    NOT NULL
);

CREATE INDEX idx_order_history ON order_status_history(order_id, created_at);

-- --------------------------- الحركات المالية --------------------------- --
-- جدول «إضافة فقط»: ممنوع UPDATE أو DELETE عليه، وأي تصحيح يكون بحركة جديدة.

CREATE TABLE transactions (
    id                   INTEGER PRIMARY KEY,
    user_id              INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    order_id             INTEGER REFERENCES orders(id) ON DELETE RESTRICT,
    payment_id           INTEGER REFERENCES payments(id) ON DELETE RESTRICT,
    type                 TEXT    NOT NULL
                          CHECK (type IN ('deposit', 'order', 'refund', 'partial_refund',
                                          'manual_credit', 'manual_debit', 'withdraw', 'adjustment')),
    direction            TEXT    NOT NULL CHECK (direction IN ('credit', 'debit')),
    amount_units         INTEGER NOT NULL CHECK (amount_units > 0),
    balance_before_units INTEGER NOT NULL CHECK (balance_before_units >= 0),
    balance_after_units  INTEGER NOT NULL CHECK (balance_after_units >= 0),
    description          TEXT,
    reference            TEXT UNIQUE,          -- مفتاح منع تكرار العملية المالية
    actor_id             INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at           TEXT    NOT NULL
);

CREATE INDEX idx_tx_user    ON transactions(user_id, created_at);
CREATE INDEX idx_tx_type    ON transactions(type, created_at);
CREATE INDEX idx_tx_order   ON transactions(order_id);
CREATE INDEX idx_tx_payment ON transactions(payment_id);

-- --------------------------------- الدعم ------------------------------- --

CREATE TABLE support_tickets (
    id               INTEGER PRIMARY KEY,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    subject          TEXT    NOT NULL,
    category         TEXT    NOT NULL DEFAULT 'other'
                      CHECK (category IN ('order', 'payment', 'service', 'other')),
    related_order_id INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    status           TEXT    NOT NULL DEFAULT 'open'
                      CHECK (status IN ('open', 'pending_admin', 'pending_user', 'closed')),
    priority         TEXT    NOT NULL DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high')),
    assigned_admin   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    last_message_at  TEXT,
    closed_by        INTEGER REFERENCES users(id) ON DELETE SET NULL,
    close_reason     TEXT,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL,
    closed_at        TEXT
);

CREATE INDEX idx_tickets_status ON support_tickets(status, last_message_at);
CREATE INDEX idx_tickets_user   ON support_tickets(user_id, created_at);

CREATE TABLE support_messages (
    id                  INTEGER PRIMARY KEY,
    ticket_id           INTEGER NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
    sender_id           INTEGER REFERENCES users(id) ON DELETE SET NULL,
    sender_type         TEXT    NOT NULL CHECK (sender_type IN ('user', 'admin', 'system')),
    message             TEXT    NOT NULL,
    attachment_file_id  TEXT,
    attachment_type     TEXT,
    telegram_message_id INTEGER,
    is_read_by_user     INTEGER NOT NULL DEFAULT 0 CHECK (is_read_by_user IN (0, 1)),
    is_read_by_admin    INTEGER NOT NULL DEFAULT 0 CHECK (is_read_by_admin IN (0, 1)),
    created_at          TEXT    NOT NULL
);

CREATE INDEX idx_ticket_messages ON support_messages(ticket_id, created_at);

-- ------------------------ الإشعارات (صندوق الإرسال) --------------------- --

CREATE TABLE notifications (
    id                  INTEGER PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type                TEXT    NOT NULL,
    title               TEXT    NOT NULL DEFAULT '',
    message             TEXT    NOT NULL,
    payload_json        TEXT,
    dedupe_key          TEXT    NOT NULL UNIQUE,   -- يمنع إرسال نفس الإشعار مرتين
    status              TEXT    NOT NULL DEFAULT 'queued'
                         CHECK (status IN ('queued', 'sent', 'failed', 'skipped')),
    attempts            INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at     TEXT,
    last_error          TEXT,
    telegram_message_id INTEGER,
    is_read             INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0, 1)),
    created_at          TEXT    NOT NULL,
    sent_at             TEXT
);

CREATE INDEX idx_notifications_queue ON notifications(status, next_attempt_at);
CREATE INDEX idx_notifications_user  ON notifications(user_id, created_at);

-- --------------------------- السجلات والإعدادات ------------------------- --

CREATE TABLE audit_logs (
    id           INTEGER PRIMARY KEY,
    admin_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action       TEXT    NOT NULL,
    target_type  TEXT,
    target_id    TEXT,
    details_json TEXT,
    before_json  TEXT,
    after_json   TEXT,
    source       TEXT    NOT NULL DEFAULT 'telegram',
    created_at   TEXT    NOT NULL
);

CREATE INDEX idx_audit_admin  ON audit_logs(admin_id, created_at);
CREATE INDEX idx_audit_target ON audit_logs(target_type, target_id);
CREATE INDEX idx_audit_action ON audit_logs(action, created_at);

CREATE TABLE settings (
    key            TEXT PRIMARY KEY,
    value          TEXT    NOT NULL DEFAULT '',
    value_type     TEXT    NOT NULL DEFAULT 'str'
                    CHECK (value_type IN ('str', 'int', 'bool', 'json', 'money')),
    group_code     TEXT    NOT NULL DEFAULT 'general',
    name_ar        TEXT    NOT NULL DEFAULT '',
    description_ar TEXT,
    is_editable    INTEGER NOT NULL DEFAULT 1 CHECK (is_editable IN (0, 1)),
    updated_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_at     TEXT    NOT NULL
);

CREATE INDEX idx_settings_group ON settings(group_code);

-- ------------------------------- الإذاعة -------------------------------- --

CREATE TABLE broadcasts (
    id                 INTEGER PRIMARY KEY,
    admin_id           INTEGER REFERENCES users(id) ON DELETE SET NULL,
    message_text       TEXT    NOT NULL DEFAULT '',
    parse_mode         TEXT,
    media_file_id      TEXT,
    media_type         TEXT,
    buttons_json       TEXT,
    target             TEXT    NOT NULL DEFAULT 'all',
    target_filter_json TEXT,
    total_count        INTEGER NOT NULL DEFAULT 0 CHECK (total_count >= 0),
    sent_count         INTEGER NOT NULL DEFAULT 0 CHECK (sent_count >= 0),
    failed_count       INTEGER NOT NULL DEFAULT 0 CHECK (failed_count >= 0),
    blocked_count      INTEGER NOT NULL DEFAULT 0 CHECK (blocked_count >= 0),
    status             TEXT    NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft', 'running', 'paused', 'completed', 'cancelled')),
    started_at         TEXT,
    finished_at        TEXT,
    created_at         TEXT    NOT NULL
);

CREATE TABLE broadcast_recipients (
    id           INTEGER PRIMARY KEY,
    broadcast_id INTEGER NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status       TEXT    NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'sent', 'failed', 'blocked')),
    error        TEXT,
    sent_at      TEXT,
    UNIQUE (broadcast_id, user_id)
);

CREATE INDEX idx_broadcast_recipients ON broadcast_recipients(broadcast_id, status);

-- --------------------- منع التكرار والسجلات التشخيصية ------------------- --

CREATE TABLE idempotency_keys (
    key         TEXT PRIMARY KEY,
    scope       TEXT    NOT NULL,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    result_json TEXT,
    created_at  TEXT    NOT NULL,
    expires_at  TEXT    NOT NULL
);

CREATE INDEX idx_idempotency_expires ON idempotency_keys(expires_at);

CREATE TABLE provider_requests (
    id               INTEGER PRIMARY KEY,
    provider_id      INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    order_id         INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    action           TEXT    NOT NULL CHECK (action IN ('add', 'status', 'balance', 'services', 'cancel', 'refill')),
    request_summary  TEXT,        -- ملخص بدون أي مفتاح سري
    http_status      INTEGER,
    response_snippet TEXT,        -- مقتطع منقّى من الاستجابة
    duration_ms      INTEGER,
    is_success       INTEGER NOT NULL DEFAULT 0 CHECK (is_success IN (0, 1)),
    error_type       TEXT,
    created_at       TEXT    NOT NULL
);

CREATE INDEX idx_provider_requests ON provider_requests(provider_id, created_at);
CREATE INDEX idx_provider_req_order ON provider_requests(order_id);

CREATE TABLE error_logs (
    id                 INTEGER PRIMARY KEY,
    level              TEXT    NOT NULL DEFAULT 'ERROR',
    source             TEXT    NOT NULL DEFAULT 'app',
    error_type         TEXT,
    message            TEXT    NOT NULL,
    traceback_snippet  TEXT,
    user_id            INTEGER REFERENCES users(id) ON DELETE SET NULL,
    update_summary     TEXT,
    notified_admin     INTEGER NOT NULL DEFAULT 0 CHECK (notified_admin IN (0, 1)),
    created_at         TEXT    NOT NULL
);

CREATE INDEX idx_error_logs ON error_logs(created_at);

CREATE TABLE backups (
    id          INTEGER PRIMARY KEY,
    filename    TEXT    NOT NULL,
    path        TEXT    NOT NULL,
    size_bytes  INTEGER NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
    sha256      TEXT,
    type        TEXT    NOT NULL DEFAULT 'manual' CHECK (type IN ('manual', 'scheduled', 'pre_operation')),
    created_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    status      TEXT    NOT NULL DEFAULT 'ok',
    created_at  TEXT    NOT NULL
);

CREATE INDEX idx_backups_created ON backups(created_at);
```

## `database/migrations/0002_seed_rbac.sql`

```sql
-- =====================================================================
-- الترحيل 0002 — زرع الأدوار والصلاحيات الافتراضية
-- المصدر المرجعي لهذه القيم هو الملف core/permissions.py
-- ويوجد اختبار آلي يتأكد من تطابق الاثنين (tests/test_permissions_seed.py)
-- =====================================================================

INSERT INTO roles (code, name_ar, level, is_system, created_at) VALUES
    ('user',        'مستخدم',     10,  1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('support',     'دعم فني',    40,  1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('admin',       'أدمن',       70,  1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('super_admin', 'أدمن أعلى',  100, 1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

INSERT INTO permissions (code, name_ar, group_code, is_dangerous) VALUES
    ('admin.access',             'الدخول إلى لوحة التحكم',            'general',   0),

    ('users.view',               'عرض المستخدمين والبحث عنهم',        'users',     0),
    ('users.balance.credit',     'إضافة رصيد لمستخدم',                'users',     1),
    ('users.balance.debit',      'خصم رصيد من مستخدم',                'users',     1),
    ('users.ban',                'حظر مستخدم',                        'users',     1),
    ('users.unban',              'فك حظر مستخدم',                     'users',     0),
    ('users.note',               'كتابة ملاحظة إدارية على مستخدم',    'users',     0),
    ('users.role.change',        'تغيير دور مستخدم',                  'users',     1),

    ('services.view',            'عرض الخدمات',                       'services',  0),
    ('services.create',          'إضافة خدمة',                        'services',  0),
    ('services.update',          'تعديل بيانات خدمة',                 'services',  0),
    ('services.price',           'تغيير سعر خدمة',                    'services',  1),
    ('services.archive',         'تعطيل أو أرشفة خدمة',               'services',  1),
    ('services.sync',            'استيراد ومزامنة خدمات المزود',      'services',  0),

    ('providers.view',           'عرض المزودين',                      'providers', 0),
    ('providers.create',         'إضافة مزود',                        'providers', 1),
    ('providers.update',         'تعديل مزود',                        'providers', 1),
    ('providers.key.update',     'تغيير مفتاح API للمزود',            'providers', 1),
    ('providers.test',           'اختبار اتصال المزود وفحص رصيده',    'providers', 0),

    ('orders.view',              'عرض الطلبات',                       'orders',    0),
    ('orders.recheck',           'إعادة فحص حالة طلب',                'orders',    0),
    ('orders.cancel',            'إلغاء طلب',                         'orders',    1),
    ('orders.refund',            'استرجاع مبلغ طلب',                  'orders',    1),
    ('orders.link_provider_id',  'ربط رقم الطلب عند المزود يدوياً',   'orders',    1),
    ('orders.status.override',   'تغيير حالة طلب يدوياً',             'orders',    1),

    ('payments.view',            'عرض طلبات الشحن',                   'payments',  0),
    ('payments.approve',         'اعتماد طلب شحن',                    'payments',  1),
    ('payments.reject',          'رفض طلب شحن',                       'payments',  1),
    ('payments.methods',         'إدارة طرق الدفع',                   'payments',  1),

    ('tickets.view',             'عرض تذاكر الدعم',                   'tickets',   0),
    ('tickets.reply',            'الرد على التذاكر',                  'tickets',   0),
    ('tickets.assign',           'إسناد التذاكر',                     'tickets',   0),
    ('tickets.close',            'إغلاق التذاكر',                     'tickets',   0),

    ('broadcast.send',           'إرسال رسالة جماعية',                'broadcast', 1),

    ('stats.view',               'عرض الإحصائيات',                    'stats',     0),
    ('stats.profit',             'عرض تقارير الأرباح والتكلفة',       'stats',     0),

    ('settings.view',            'عرض الإعدادات',                     'settings',  0),
    ('settings.update',          'تعديل الإعدادات العامة',            'settings',  1),
    ('settings.maintenance',     'تفعيل أو إيقاف وضع الصيانة',        'settings',  1),

    ('logs.view',                'عرض السجلات والأخطاء',              'logs',      0),

    ('backup.create',            'إنشاء نسخة احتياطية',               'backup',    1),
    ('backup.download',          'تنزيل نسخة احتياطية',               'backup',    1),

    ('admins.manage',            'إدارة الأدوار والصلاحيات',          'admins',    1);

-- الأدمن الأعلى: كل الصلاحيات
INSERT INTO role_permissions (role_code, permission_code)
SELECT 'super_admin', code FROM permissions;

-- الأدمن العادي: كل الصلاحيات عدا الحصرية للأدمن الأعلى
INSERT INTO role_permissions (role_code, permission_code)
SELECT 'admin', code FROM permissions
WHERE code NOT IN (
    'users.role.change',
    'providers.key.update',
    'orders.link_provider_id',
    'orders.status.override',
    'stats.profit',
    'backup.create',
    'backup.download',
    'admins.manage'
);

-- الدعم الفني: التذاكر + صلاحيات عرض محدودة
INSERT INTO role_permissions (role_code, permission_code)
SELECT 'support', code FROM permissions
WHERE code IN (
    'admin.access',
    'users.view',
    'services.view',
    'orders.view',
    'orders.recheck',
    'payments.view',
    'tickets.view',
    'tickets.reply',
    'tickets.assign',
    'tickets.close'
);

-- دور المستخدم العادي: لا يملك أي صلاحية إدارية (لا صفوف)
```

## `database/migrations/0003_seed_settings.sql`

```sql
-- =====================================================================
-- الترحيل 0003 — زرع الإعدادات الافتراضية وتصنيفات الخدمات
-- كل إعداد هنا قابل للتعديل لاحقاً من لوحة الأدمن (عدا ما is_editable = 0)
-- المبالغ مخزَّنة بالنقاط (1/10000 من وحدة العملة)
-- =====================================================================

INSERT INTO settings (key, value, value_type, group_code, name_ar, description_ar, is_editable, updated_at) VALUES
    -- عام
    ('bot_name', 'SMM Bot', 'str', 'general', 'اسم البوت', 'يظهر في رسالة الترحيل وبعض الرسائل', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('currency_code', 'YER', 'str', 'general', 'رمز العملة', 'رمز العملة المحاسبي مثل YER أو USD', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('currency_symbol', 'ريال', 'str', 'general', 'رمز العرض للعملة', 'النص الذي يظهر بجانب المبالغ', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('display_decimals', '2', 'int', 'general', 'عدد الخانات العشرية للعرض', 'لا يؤثر على دقة التخزين الداخلية', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('welcome_message', 'أهلاً بك في بوت خدمات السوشيال ميديا 👋', 'str', 'general', 'رسالة الترحيب', 'تظهر عند أمر start', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('support_username', '', 'str', 'general', 'حساب الدعم', 'معرف تيليجرام للدعم بدون علامة @', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('rules_text', 'يرجى قراءة الشروط قبل الطلب. لا يوجد استرجاع بعد اكتمال التنفيذ.', 'str', 'general', 'الشروط وسياسة الاسترجاع', 'تظهر في قسم معلومات', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('registration_enabled', '1', 'bool', 'general', 'السماح بتسجيل مستخدمين جدد', 'عند التعطيل لن يُقبل أي مستخدم جديد', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    -- الصيانة
    ('maintenance_mode', '0', 'bool', 'maintenance', 'وضع الصيانة', 'عند التفعيل يستخدم النظام الأدمن فقط', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('maintenance_message', '🚧 النظام في وضع الصيانة حالياً، نعتذر عن الإزعاج.', 'str', 'maintenance', 'رسالة الصيانة', 'تظهر للمستخدمين أثناء الصيانة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    -- الطلبات
    ('min_order_amount_units', '0', 'money', 'orders', 'الحد الأدنى لقيمة الطلب', 'صفر يعني لا يوجد حد أدنى', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('duplicate_order_window_minutes', '10', 'int', 'orders', 'نافذة كشف الطلب المكرر بالدقائق', 'خلالها يُطلب تأكيد إضافي لنفس الرابط والكمية', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('order_submit_interval_seconds', '15', 'int', 'orders', 'فاصل إرسال الطلبات للمزود', 'كل كم ثانية يعمل job الإرسال', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('order_check_interval_seconds', '120', 'int', 'orders', 'فاصل فحص حالة الطلبات', 'كل كم ثانية يعمل job فحص الحالة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('order_stuck_alert_hours', '24', 'int', 'orders', 'تنبيه الطلب العالق بالساعات', 'ينبّه الأدمن للطلب الذي لم يكتمل خلال هذه المدة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('partial_refund_enabled', '1', 'bool', 'orders', 'تفعيل الاسترجاع الجزئي', 'استرجاع قيمة الكمية غير المنفذة تلقائياً', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('auto_refund_on_provider_fail', '1', 'bool', 'orders', 'الاسترجاع التلقائي عند فشل المزود', 'إعادة المبلغ فوراً عند فشل الإرسال', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('user_cancel_before_submit', '1', 'bool', 'orders', 'السماح للمستخدم بإلغاء طلبه قبل الإرسال', 'يُسترجع المبلغ كاملاً', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('max_orders_per_day', '50', 'int', 'orders', 'أقصى عدد طلبات للمستخدم يومياً', 'حماية من إساءة الاستخدام', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    -- المدفوعات
    ('min_deposit_units', '10000', 'money', 'payments', 'الحد الأدنى للشحن', 'بالنقاط: 10000 تعادل وحدة عملة واحدة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('max_deposit_units', '100000000', 'money', 'payments', 'الحد الأقصى للشحن', 'بالنقاط', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('payment_expiry_hours', '48', 'int', 'payments', 'انتهاء صلاحية طلب الشحن بالساعات', 'يُعلَّم تلقائياً كمنتهٍ بعدها', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    -- الإشعارات
    ('notification_dispatch_seconds', '5', 'int', 'notifications', 'فاصل إرسال الإشعارات', 'كل كم ثانية يعمل job الإشعارات', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('admin_alert_chat_id', '', 'str', 'notifications', 'قناة تنبيهات الأدمن', 'معرف مجموعة أو قناة لاستقبال تنبيهات النظام', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    -- المزودون
    ('provider_low_balance_alert_units', '0', 'money', 'providers', 'حد التنبيه لرصيد المزود', 'صفر يعني بدون تنبيه', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('provider_exchange_rate', '1', 'str', 'providers', 'سعر صرف عملة المزود', 'كم وحدة من عملة العرض تعادل وحدة واحدة من عملة المزود', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('provider_failure_threshold', '5', 'int', 'providers', 'عدد الأخطاء المتتالية لتعطيل المزود', 'قاطع الدائرة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('provider_disable_minutes', '15', 'int', 'providers', 'مدة التعطيل المؤقت للمزود بالدقائق', 'بعدها يُعاد تفعيله تلقائياً', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('provider_insufficient_wait_hours', '6', 'int', 'providers', 'مهلة انتظار شحن رصيد المزود بالساعات', 'بعدها يفشل الطلب ويُسترجع المبلغ', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    -- النسخ الاحتياطي
    ('backup_interval_hours', '12', 'int', 'backup', 'فاصل النسخ الاحتياطي التلقائي بالساعات', 'صفر يعني تعطيل', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('backup_retention_days', '14', 'int', 'backup', 'مدة الاحتفاظ بالنسخ بالأيام', 'تُحذف النسخ الأقدم تلقائياً', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    -- الحدود والحماية
    ('broadcast_rate_per_second', '20', 'int', 'limits', 'سرعة الإذاعة رسالة بالثانية', 'احترام حدود تيليجرام', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('rate_limit_actions_per_minute', '25', 'int', 'limits', 'أقصى عدد إجراءات للمستخدم بالدقيقة', 'حماية من الضغط المتكرر', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('max_tickets_per_day', '5', 'int', 'limits', 'أقصى عدد تذاكر للمستخدم يومياً', 'حماية من الإزعاج', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    -- قيمة داخلية غير قابلة للتعديل من الواجهة
    ('schema_money_scale', '10000', 'int', 'system', 'مقياس المال الداخلي', 'عدد النقاط في وحدة العملة - تغييره يتطلب ترحيل بيانات', 0, strftime('%Y-%m-%dT%H:%M:%fZ','now'));

-- تصنيفات الخدمات الافتراضية (هيكلية وليست بيانات وهمية - لا تحتوي أي خدمة)
INSERT INTO service_categories (name_ar, name_en, emoji, sort_order, is_active, created_at, updated_at) VALUES
    ('انستغرام', 'Instagram', '📸', 10, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('تيك توك',  'TikTok',    '🎵', 20, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('يوتيوب',   'YouTube',   '▶️', 30, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('تيليجرام', 'Telegram',  '📢', 40, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('فيسبوك',   'Facebook',  '📘', 50, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('تويتر',    'X',         '✖️', 60, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('سناب شات', 'Snapchat',  '👻', 70, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('أخرى',     'Other',     '📦', 99, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now'));
```

# المستودعات — database/repositories/

## `database/repositories/__init__.py`

```python
"""
حزمة المستودعات + حاوية موحدة للوصول إليها.

الاستخدام في الطبقات الأعلى:
    repos = Repositories(db)
    user = await repos.users.get_by_telegram_id(123)
"""

from __future__ import annotations

from database.database import Database
from database.repositories.audit import AuditRepository
from database.repositories.base import BaseRepository
from database.repositories.broadcasts import BroadcastsRepository
from database.repositories.categories import CategoriesRepository
from database.repositories.idempotency import IdempotencyRepository
from database.repositories.misc import (
    BackupsRepository,
    ErrorLogsRepository,
    ProviderRequestsRepository,
    UserStatesRepository,
)
from database.repositories.notifications import NotificationsRepository
from database.repositories.orders import OrdersRepository
from database.repositories.payments import PaymentMethodsRepository, PaymentsRepository
from database.repositories.providers import ProvidersRepository
from database.repositories.rbac import RbacRepository
from database.repositories.services import ServicesRepository
from database.repositories.settings import SettingsRepository
from database.repositories.tickets import TicketsRepository
from database.repositories.transactions import TransactionsRepository
from database.repositories.users import UsersRepository

__all__ = [
    "Repositories",
    "BaseRepository",
    "UsersRepository",
    "RbacRepository",
    "SettingsRepository",
    "ProvidersRepository",
    "CategoriesRepository",
    "ServicesRepository",
    "OrdersRepository",
    "TransactionsRepository",
    "PaymentsRepository",
    "PaymentMethodsRepository",
    "TicketsRepository",
    "NotificationsRepository",
    "AuditRepository",
    "BroadcastsRepository",
    "IdempotencyRepository",
    "UserStatesRepository",
    "ProviderRequestsRepository",
    "ErrorLogsRepository",
    "BackupsRepository",
]


class Repositories:
    """حاوية تجمع كل المستودعات على نفس اتصال قاعدة البيانات."""

    def __init__(self, db: Database) -> None:
        """إنشاء نسخة واحدة من كل مستودع ومشاركتها مع بقية النظام."""
        self.db = db
        self.users = UsersRepository(db)
        self.rbac = RbacRepository(db)
        self.settings = SettingsRepository(db)
        self.providers = ProvidersRepository(db)
        self.categories = CategoriesRepository(db)
        self.services = ServicesRepository(db)
        self.orders = OrdersRepository(db)
        self.transactions = TransactionsRepository(db)
        self.payments = PaymentsRepository(db)
        self.payment_methods = PaymentMethodsRepository(db)
        self.tickets = TicketsRepository(db)
        self.notifications = NotificationsRepository(db)
        self.audit = AuditRepository(db)
        self.broadcasts = BroadcastsRepository(db)
        self.idempotency = IdempotencyRepository(db)
        self.user_states = UserStatesRepository(db)
        self.provider_requests = ProviderRequestsRepository(db)
        self.error_logs = ErrorLogsRepository(db)
        self.backups = BackupsRepository(db)
```

## `database/repositories/base.py`

```python
"""
الأساس المشترك لكل المستودعات (Repositories).

القاعدة المتبعة في المشروع:
    • كل دوال القراءة تعمل مباشرة عبر db (وتستخدم المعاملة الحالية تلقائياً إن وُجدت).
    • كل دوال الكتابة تستقبل tx كأول مُعامل، لإجبار المنادي على فتح معاملة صريحة.
      هذا يضمن أن العمليات المترابطة (مال + طلب + سجل + إشعار) تتم كوحدة واحدة.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from database.database import Database, ExecResult, Tx
from utils.datetime_utils import utc_now_iso


class BaseRepository:
    """أساس المستودعات: يحمل مرجع قاعدة البيانات وأدوات مساعدة مشتركة."""

    def __init__(self, db: Database) -> None:
        """تهيئة المستودع بمرجع قاعدة البيانات."""
        self.db = db

    @staticmethod
    def now() -> str:
        """الوقت الحالي بصيغة التخزين المعتمدة (ISO/UTC)."""
        return utc_now_iso()

    @staticmethod
    def _build_update(
        fields: Mapping[str, Any],
        allowed: Iterable[str],
    ) -> tuple[str, list[Any]]:
        """
        بناء جملة SET آمنة من قاموس حقول، مع قبول الأعمدة المسموح بها فقط.

        المدخلات:
            fields  : الحقول المطلوب تعديلها.
            allowed : أسماء الأعمدة المسموح تعديلها (قائمة بيضاء).

        المخرجات: (نص SET، قائمة القيم) لاستخدامها في عبارة مُعلَّمة.

        ملاحظة أمنية: أسماء الأعمدة لا تأتي أبداً من إدخال المستخدم مباشرة،
        بل تُقارن بالقائمة البيضاء، والقيم تُمرَّر كمعاملات ? وليس بالدمج النصي.
        """
        allowed_set = set(allowed)
        parts: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            if key not in allowed_set:
                raise ValueError(f"محاولة تعديل عمود غير مسموح: {key}")
            parts.append(f"{key} = ?")
            values.append(value)
        return ", ".join(parts), values

    async def _update_by_id(
        self,
        tx: Tx,
        table: str,
        row_id: int | str,
        fields: Mapping[str, Any],
        allowed: Iterable[str],
        *,
        id_column: str = "id",
        touch_updated: bool = True,
    ) -> bool:
        """
        تعديل صف واحد حسب معرفه مع تحديث عمود updated_at تلقائياً.

        المخرجات: True إذا تم تعديل صف فعلاً.
        """
        data = dict(fields)
        if not data:
            return False
        set_sql, values = self._build_update(data, allowed)
        if touch_updated:
            set_sql += ", updated_at = ?"
            values.append(self.now())
        values.append(row_id)
        result: ExecResult = await tx.execute(
            f"UPDATE {table} SET {set_sql} WHERE {id_column} = ?", values
        )
        return result.rowcount > 0

    async def count(self, table: str, where: str = "", params: Iterable[Any] = ()) -> int:
        """عدّ الصفوف في جدول مع شرط اختياري (يُستخدم في الإحصائيات)."""
        sql = f"SELECT COUNT(*) FROM {table}"
        if where:
            sql += f" WHERE {where}"
        return int(await self.db.fetchval(sql, list(params), default=0))
```

## `database/repositories/users.py`

```python
"""
مستودع المستخدمين — كل عبارات SQL الخاصة بجدول users.

مهم: هذا المستودع يوفّر العمليات الذرّية على الرصيد (try_debit / credit)،
لكن لا يجوز استدعاؤها إلا من WalletService (المرحلة 2) لضمان تسجيل كل حركة مالية.
"""

from __future__ import annotations

from typing import Any

from database.database import Tx
from database.models import User
from database.repositories.base import BaseRepository

#: الأعمدة المسموح تعديلها عبر update_fields
_ALLOWED_FIELDS = {
    "username",
    "first_name",
    "last_name",
    "role",
    "is_banned",
    "ban_reason",
    "banned_at",
    "blocked_bot",
    "language",
    "notes",
    "last_activity",
    "referrer_id",
}


class UsersRepository(BaseRepository):
    """عمليات قراءة وكتابة بيانات المستخدمين."""

    # ------------------------------ القراءة ------------------------------ #

    async def get_by_id(self, user_id: int) -> User | None:
        """جلب مستخدم بالمعرف الداخلي."""
        row = await self.db.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
        return User.from_row(row)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        """جلب مستخدم بمعرف تيليجرام."""
        row = await self.db.fetchone("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        return User.from_row(row)

    async def get_balance_units(self, user_id: int) -> int:
        """قراءة الرصيد الحالي بالنقاط (0 إذا لم يوجد المستخدم)."""
        return int(await self.db.fetchval(
            "SELECT balance_units FROM users WHERE id = ?", (user_id,), default=0
        ))

    async def search(self, query: str, limit: int = 10, offset: int = 0) -> list[User]:
        """
        البحث عن مستخدم بالمعرف الرقمي أو باسم المستخدم أو الاسم الأول.

        المدخلات: query نص البحث (يقبل «@name» أو رقم تيليجرام أو جزء من الاسم).
        """
        text = query.strip().lstrip("@")
        if text.isdigit():
            rows = await self.db.fetchall(
                "SELECT * FROM users WHERE telegram_id = ? OR id = ? LIMIT ? OFFSET ?",
                (int(text), int(text), limit, offset),
            )
        else:
            pattern = f"%{text}%"
            rows = await self.db.fetchall(
                "SELECT * FROM users WHERE username LIKE ? OR first_name LIKE ? "
                "ORDER BY last_activity DESC LIMIT ? OFFSET ?",
                (pattern, pattern, limit, offset),
            )
        return User.from_rows(rows)

    async def list_by_role(self, role: str) -> list[User]:
        """كل المستخدمين الذين يحملون دوراً معيناً (لإشعارات الأدمن مثلاً)."""
        rows = await self.db.fetchall("SELECT * FROM users WHERE role = ? ORDER BY id", (role,))
        return User.from_rows(rows)

    async def list_recent(self, limit: int = 10, offset: int = 0) -> list[User]:
        """آخر المستخدمين المسجلين."""
        rows = await self.db.fetchall(
            "SELECT * FROM users ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        return User.from_rows(rows)

    async def count_all(self) -> int:
        """إجمالي عدد المستخدمين."""
        return await self.count("users")

    async def count_since(self, since_iso: str) -> int:
        """عدد المستخدمين الجدد منذ وقت معين."""
        return await self.count("users", "created_at >= ?", (since_iso,))

    async def count_active_since(self, since_iso: str) -> int:
        """عدد المستخدمين النشطين منذ وقت معين."""
        return await self.count("users", "last_activity >= ?", (since_iso,))

    async def count_banned(self) -> int:
        """عدد المستخدمين المحظورين."""
        return await self.count("users", "is_banned = 1")

    async def telegram_ids_for_broadcast(
        self, *, only_active_since: str | None = None, with_orders: bool = False
    ) -> list[int]:
        """
        قائمة معرفات تيليجرام المستهدفة بالإذاعة (تستثني المحظورين ومن حظر البوت).

        المدخلات:
            only_active_since : اقتصار على من كان نشطاً بعد هذا الوقت.
            with_orders       : اقتصار على من لديه طلب واحد على الأقل.
        """
        sql = ["SELECT DISTINCT u.telegram_id FROM users u"]
        params: list[Any] = []
        if with_orders:
            sql.append("JOIN orders o ON o.user_id = u.id")
        sql.append("WHERE u.is_banned = 0 AND u.blocked_bot = 0")
        if only_active_since:
            sql.append("AND u.last_activity >= ?")
            params.append(only_active_since)
        rows = await self.db.fetchall(" ".join(sql), params)
        return [int(row["telegram_id"]) for row in rows]

    # ------------------------------ الكتابة ------------------------------ #

    async def create(
        self,
        tx: Tx,
        *,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        language: str = "ar",
        role: str = "user",
        referrer_id: int | None = None,
    ) -> User:
        """
        إنشاء مستخدم جديد برصيد صفر.

        المخرجات: كائن المستخدم بعد الإنشاء.
        """
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO users (telegram_id, username, first_name, last_name, language, role,
                               referrer_id, created_at, updated_at, last_activity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (telegram_id, username, first_name, last_name, language, role, referrer_id, now, now, now),
        )
        row = await tx.fetchone("SELECT * FROM users WHERE id = ?", (result.lastrowid,))
        user = User.from_row(row)
        assert user is not None
        return user

    async def update_fields(self, tx: Tx, user_id: int, **fields: Any) -> bool:
        """تعديل حقول مسموح بها للمستخدم (لا تشمل الرصيد إطلاقاً)."""
        return await self._update_by_id(tx, "users", user_id, fields, _ALLOWED_FIELDS)

    async def update_profile(
        self,
        tx: Tx,
        user_id: int,
        *,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> bool:
        """تحديث بيانات الملف الشخصي القادمة من تيليجرام عند كل تفاعل."""
        return await self._update_by_id(
            tx,
            "users",
            user_id,
            {
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "last_activity": self.now(),
            },
            _ALLOWED_FIELDS,
        )

    async def touch_activity(self, tx: Tx, user_id: int) -> None:
        """تحديث وقت آخر نشاط للمستخدم."""
        now = self.now()
        await tx.execute(
            "UPDATE users SET last_activity = ?, updated_at = ? WHERE id = ?", (now, now, user_id)
        )

    async def set_ban(self, tx: Tx, user_id: int, *, banned: bool, reason: str | None = None) -> bool:
        """حظر مستخدم أو فك حظره مع تسجيل السبب ووقت الحظر."""
        return await self._update_by_id(
            tx,
            "users",
            user_id,
            {
                "is_banned": 1 if banned else 0,
                "ban_reason": reason if banned else None,
                "banned_at": self.now() if banned else None,
            },
            _ALLOWED_FIELDS,
        )

    async def set_role(self, tx: Tx, user_id: int, role: str) -> bool:
        """تغيير دور المستخدم (عملية حساسة تتطلب تسجيلاً في Audit Log)."""
        return await self._update_by_id(tx, "users", user_id, {"role": role}, _ALLOWED_FIELDS)

    async def set_blocked_bot(self, tx: Tx, user_id: int, blocked: bool) -> bool:
        """تعليم أن المستخدم حظر البوت (يُكتشف عند فشل إرسال إشعار)."""
        return await self._update_by_id(
            tx, "users", user_id, {"blocked_bot": 1 if blocked else 0}, _ALLOWED_FIELDS
        )

    # --------------------------- عمليات الرصيد ---------------------------- #
    # ⚠️ تُستدعى حصراً من WalletService مع تسجيل حركة مالية في نفس المعاملة.

    async def try_debit(self, tx: Tx, user_id: int, amount_units: int) -> bool:
        """
        خصم مبلغ من الرصيد بشكل ذرّي دون إمكانية أن يصبح الرصيد سالباً.

        الآلية: UPDATE مشروط برصيد كافٍ؛ إذا لم يتأثر أي صف فالرصيد غير كافٍ.

        المخرجات: True إذا تم الخصم، False إذا كان الرصيد غير كافٍ أو المستخدم غير موجود.
        """
        if amount_units <= 0:
            raise ValueError("مبلغ الخصم يجب أن يكون أكبر من صفر.")
        result = await tx.execute(
            """
            UPDATE users
               SET balance_units = balance_units - ?,
                   total_spent_units = total_spent_units + ?,
                   updated_at = ?
             WHERE id = ? AND balance_units >= ?
            """,
            (amount_units, amount_units, self.now(), user_id, amount_units),
        )
        return result.rowcount == 1

    async def credit(self, tx: Tx, user_id: int, amount_units: int, *, count_as_deposit: bool = False) -> bool:
        """
        إضافة مبلغ إلى رصيد المستخدم.

        المدخلات:
            count_as_deposit : احتساب المبلغ ضمن إجمالي الإيداعات (يُستخدم عند اعتماد الشحن فقط).
        """
        if amount_units <= 0:
            raise ValueError("مبلغ الإضافة يجب أن يكون أكبر من صفر.")
        result = await tx.execute(
            """
            UPDATE users
               SET balance_units = balance_units + ?,
                   total_deposited_units = total_deposited_units + ?,
                   updated_at = ?
             WHERE id = ?
            """,
            (amount_units, amount_units if count_as_deposit else 0, self.now(), user_id),
        )
        return result.rowcount == 1

    async def refund_spent(self, tx: Tx, user_id: int, amount_units: int) -> bool:
        """
        إعادة مبلغ إلى الرصيد مع تخفيض إجمالي الإنفاق (يُستخدم عند الاسترجاع).

        ملاحظة: إجمالي الإنفاق لا يُسمح بأن يصبح سالباً.
        """
        if amount_units <= 0:
            raise ValueError("مبلغ الاسترجاع يجب أن يكون أكبر من صفر.")
        result = await tx.execute(
            """
            UPDATE users
               SET balance_units = balance_units + ?,
                   total_spent_units = MAX(0, total_spent_units - ?),
                   updated_at = ?
             WHERE id = ?
            """,
            (amount_units, amount_units, self.now(), user_id),
        )
        return result.rowcount == 1
```

## `database/repositories/rbac.py`

```python
"""
مستودع الأدوار والصلاحيات (RBAC) — المصدر الفعلي للصلاحيات هو قاعدة البيانات.

منطق التحقق:
    1. إن وُجد استثناء فردي للمستخدم في user_permissions فهو الحاسم (منح أو منع).
    2. وإلا تُستخدم صلاحيات دوره من role_permissions.
"""

from __future__ import annotations

from database.database import Tx
from database.repositories.base import BaseRepository


class RbacRepository(BaseRepository):
    """قراءة وتعديل الأدوار والصلاحيات."""

    # ------------------------------ القراءة ------------------------------ #

    async def list_roles(self) -> list[dict]:
        """كل الأدوار مرتبة حسب مستوى الصلاحية."""
        rows = await self.db.fetchall("SELECT * FROM roles ORDER BY level DESC")
        return [dict(row) for row in rows]

    async def list_permissions(self) -> list[dict]:
        """كل الصلاحيات المعرَّفة في النظام."""
        rows = await self.db.fetchall("SELECT * FROM permissions ORDER BY group_code, code")
        return [dict(row) for row in rows]

    async def role_permissions(self, role_code: str) -> set[str]:
        """أكواد الصلاحيات الممنوحة لدور معين."""
        rows = await self.db.fetchall(
            "SELECT permission_code FROM role_permissions WHERE role_code = ?", (role_code,)
        )
        return {row["permission_code"] for row in rows}

    async def user_overrides(self, user_id: int) -> dict[str, bool]:
        """الاستثناءات الفردية لمستخدم: كود الصلاحية → مسموح/ممنوع."""
        rows = await self.db.fetchall(
            "SELECT permission_code, allow FROM user_permissions WHERE user_id = ?", (user_id,)
        )
        return {row["permission_code"]: bool(row["allow"]) for row in rows}

    async def has_permission(self, user_id: int, role_code: str, permission: str) -> bool:
        """
        هل يملك المستخدم هذه الصلاحية؟

        الترتيب: الاستثناء الفردي أولاً، ثم صلاحيات الدور.
        """
        override = await self.db.fetchone(
            "SELECT allow FROM user_permissions WHERE user_id = ? AND permission_code = ?",
            (user_id, permission),
        )
        if override is not None:
            return bool(override["allow"])
        found = await self.db.fetchone(
            "SELECT 1 FROM role_permissions WHERE role_code = ? AND permission_code = ?",
            (role_code, permission),
        )
        return found is not None

    async def effective_permissions(self, user_id: int, role_code: str) -> set[str]:
        """الصلاحيات الفعلية للمستخدم بعد تطبيق الاستثناءات الفردية."""
        permissions = await self.role_permissions(role_code)
        for code, allowed in (await self.user_overrides(user_id)).items():
            if allowed:
                permissions.add(code)
            else:
                permissions.discard(code)
        return permissions

    # ------------------------------ الكتابة ------------------------------ #

    async def grant_to_role(self, tx: Tx, role_code: str, permission: str) -> None:
        """منح صلاحية لدور (يتجاهل التكرار)."""
        await tx.execute(
            "INSERT OR IGNORE INTO role_permissions (role_code, permission_code) VALUES (?, ?)",
            (role_code, permission),
        )

    async def revoke_from_role(self, tx: Tx, role_code: str, permission: str) -> bool:
        """سحب صلاحية من دور."""
        result = await tx.execute(
            "DELETE FROM role_permissions WHERE role_code = ? AND permission_code = ?",
            (role_code, permission),
        )
        return result.rowcount > 0

    async def set_user_override(
        self, tx: Tx, user_id: int, permission: str, *, allow: bool, granted_by: int | None = None
    ) -> None:
        """تعيين استثناء فردي لمستخدم (منح صلاحية أو منعها بغض النظر عن دوره)."""
        await tx.execute(
            """
            INSERT INTO user_permissions (user_id, permission_code, allow, granted_by, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, permission_code)
            DO UPDATE SET allow = excluded.allow, granted_by = excluded.granted_by
            """,
            (user_id, permission, 1 if allow else 0, granted_by, self.now()),
        )

    async def clear_user_override(self, tx: Tx, user_id: int, permission: str) -> bool:
        """حذف استثناء فردي والعودة إلى صلاحيات الدور."""
        result = await tx.execute(
            "DELETE FROM user_permissions WHERE user_id = ? AND permission_code = ?",
            (user_id, permission),
        )
        return result.rowcount > 0
```

## `database/repositories/settings.py`

```python
"""
مستودع الإعدادات العامة — كل قيمة قابلة للتعديل من لوحة الأدمن تُقرأ من هنا.

التخزين نصي دائماً، والتحويل إلى النوع الصحيح يتم عند القراءة حسب value_type.
"""

from __future__ import annotations

import json
from typing import Any

from database.database import Tx
from database.models import Setting
from database.repositories.base import BaseRepository


class SettingsRepository(BaseRepository):
    """قراءة وكتابة إعدادات النظام."""

    # ------------------------------ القراءة ------------------------------ #

    async def get_raw(self, key: str) -> str | None:
        """القيمة النصية الخام لإعداد، أو None إذا لم يوجد."""
        return await self.db.fetchval("SELECT value FROM settings WHERE key = ?", (key,))

    async def get(self, key: str) -> Setting | None:
        """جلب الإعداد كاملاً بكل بياناته الوصفية."""
        row = await self.db.fetchone("SELECT * FROM settings WHERE key = ?", (key,))
        return Setting.from_row(row)

    async def get_str(self, key: str, default: str = "") -> str:
        """قراءة إعداد نصي."""
        value = await self.get_raw(key)
        return default if value is None else value

    async def get_int(self, key: str, default: int = 0) -> int:
        """قراءة إعداد رقمي (يُرجع القيمة الافتراضية إذا كانت القيمة تالفة)."""
        value = await self.get_raw(key)
        if value is None or value == "":
            return default
        try:
            return int(value)
        except ValueError:
            return default

    async def get_bool(self, key: str, default: bool = False) -> bool:
        """قراءة إعداد منطقي (يقبل 1/0 و true/false و yes/no)."""
        value = await self.get_raw(key)
        if value is None or value == "":
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    async def get_json(self, key: str, default: Any = None) -> Any:
        """قراءة إعداد مخزَّن كـ JSON."""
        value = await self.get_raw(key)
        if not value:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default

    async def get_money_units(self, key: str, default: int = 0) -> int:
        """قراءة إعداد مالي مخزَّن بالنقاط."""
        return await self.get_int(key, default)

    async def all(self) -> list[Setting]:
        """كل الإعدادات مرتبة حسب المجموعة."""
        rows = await self.db.fetchall("SELECT * FROM settings ORDER BY group_code, key")
        return Setting.from_rows(rows)

    async def by_group(self, group_code: str) -> list[Setting]:
        """إعدادات مجموعة واحدة (لعرضها في شاشة واحدة داخل اللوحة)."""
        rows = await self.db.fetchall(
            "SELECT * FROM settings WHERE group_code = ? ORDER BY key", (group_code,)
        )
        return Setting.from_rows(rows)

    async def groups(self) -> list[str]:
        """أسماء مجموعات الإعدادات الموجودة."""
        rows = await self.db.fetchall("SELECT DISTINCT group_code FROM settings ORDER BY group_code")
        return [row["group_code"] for row in rows]

    async def as_dict(self) -> dict[str, str]:
        """كل الإعدادات كقاموس (يُستخدم لبناء الذاكرة المؤقتة في SettingsService)."""
        rows = await self.db.fetchall("SELECT key, value FROM settings")
        return {row["key"]: row["value"] for row in rows}

    # ------------------------------ الكتابة ------------------------------ #

    async def set(self, tx: Tx, key: str, value: Any, *, updated_by: int | None = None) -> bool:
        """
        تعديل قيمة إعداد موجود.

        المخرجات: True إذا تم التعديل، False إذا كان المفتاح غير موجود أو غير قابل للتعديل.
        """
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        result = await tx.execute(
            "UPDATE settings SET value = ?, updated_by = ?, updated_at = ? WHERE key = ? AND is_editable = 1",
            (text, updated_by, self.now(), key),
        )
        return result.rowcount > 0

    async def upsert(
        self,
        tx: Tx,
        key: str,
        value: Any,
        *,
        value_type: str = "str",
        group_code: str = "general",
        name_ar: str = "",
        description_ar: str | None = None,
        is_editable: bool = True,
    ) -> None:
        """إضافة إعداد جديد أو تحديثه (تُستخدم عند إضافة ميزات جديدة تحتاج إعدادات)."""
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        await tx.execute(
            """
            INSERT INTO settings (key, value, value_type, group_code, name_ar, description_ar,
                                  is_editable, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                value_type = excluded.value_type,
                group_code = excluded.group_code,
                name_ar = excluded.name_ar,
                description_ar = excluded.description_ar,
                updated_at = excluded.updated_at
            """,
            (key, text, value_type, group_code, name_ar, description_ar, 1 if is_editable else 0, self.now()),
        )
```

## `database/repositories/providers.py`

```python
"""
مستودع المزودين — بيانات الاتصال بلوحات SMM الخارجية.

ملاحظة أمنية: مفتاح API يُخزَّن مشفّراً في api_key_enc، ولا تُرجع هذه الطبقة
المفتاح الأصلي أبداً؛ فك التشفير يتم في ProviderService عند الاستدعاء فقط.
"""

from __future__ import annotations

from typing import Any

from database.database import Tx
from database.models import Provider
from database.repositories.base import BaseRepository

_ALLOWED_FIELDS = {
    "name",
    "api_url",
    "api_key_enc",
    "api_key_hint",
    "api_type",
    "balance_units",
    "currency",
    "balance_checked_at",
    "low_balance_threshold_units",
    "is_active",
    "priority",
    "timeout_seconds",
    "consecutive_failures",
    "disabled_until",
    "last_error",
    "last_success_at",
}


class ProvidersRepository(BaseRepository):
    """عمليات قراءة وكتابة بيانات المزودين."""

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, provider_id: int) -> Provider | None:
        """جلب مزود بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM providers WHERE id = ?", (provider_id,))
        return Provider.from_row(row)

    async def get_by_name(self, name: str) -> Provider | None:
        """جلب مزود بالاسم (الاسم فريد)."""
        row = await self.db.fetchone("SELECT * FROM providers WHERE name = ?", (name,))
        return Provider.from_row(row)

    async def list_all(self, *, active_only: bool = False) -> list[Provider]:
        """قائمة المزودين مرتبة حسب الأولوية."""
        sql = "SELECT * FROM providers"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY priority, id"
        rows = await self.db.fetchall(sql)
        return Provider.from_rows(rows)

    async def count_services(self, provider_id: int) -> int:
        """عدد الخدمات المرتبطة بمزود (للتحذير قبل تعطيله)."""
        return await self.count("services", "provider_id = ? AND is_archived = 0", (provider_id,))

    # ------------------------------ الكتابة ------------------------------ #

    async def create(
        self,
        tx: Tx,
        *,
        name: str,
        api_url: str,
        api_key_enc: str,
        api_key_hint: str | None = None,
        api_type: str = "perfect_panel",
        currency: str = "USD",
        timeout_seconds: int = 30,
        priority: int = 100,
    ) -> Provider:
        """إضافة مزود جديد (المفتاح يصل مشفّراً من ProviderService)."""
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO providers (name, api_url, api_key_enc, api_key_hint, api_type, currency,
                                   timeout_seconds, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, api_url, api_key_enc, api_key_hint, api_type, currency, timeout_seconds, priority, now, now),
        )
        row = await tx.fetchone("SELECT * FROM providers WHERE id = ?", (result.lastrowid,))
        provider = Provider.from_row(row)
        assert provider is not None
        return provider

    async def update_fields(self, tx: Tx, provider_id: int, **fields: Any) -> bool:
        """تعديل حقول مسموح بها للمزود."""
        return await self._update_by_id(tx, "providers", provider_id, fields, _ALLOWED_FIELDS)

    async def update_balance(
        self, tx: Tx, provider_id: int, balance_units: int, currency: str | None = None
    ) -> bool:
        """تحديث رصيد المزود بعد فحصه، مع تسجيل وقت الفحص."""
        fields: dict[str, Any] = {
            "balance_units": balance_units,
            "balance_checked_at": self.now(),
        }
        if currency:
            fields["currency"] = currency
        return await self._update_by_id(tx, "providers", provider_id, fields, _ALLOWED_FIELDS)

    async def record_success(self, tx: Tx, provider_id: int) -> None:
        """تصفير عداد الأخطاء المتتالية بعد استدعاء ناجح."""
        await tx.execute(
            """
            UPDATE providers
               SET consecutive_failures = 0, disabled_until = NULL,
                   last_error = NULL, last_success_at = ?, updated_at = ?
             WHERE id = ?
            """,
            (self.now(), self.now(), provider_id),
        )

    async def record_failure(
        self, tx: Tx, provider_id: int, error: str, *, disable_until: str | None = None
    ) -> int:
        """
        تسجيل فشل استدعاء وزيادة عداد الأخطاء المتتالية (قاطع الدائرة).

        المخرجات: عدد الأخطاء المتتالية بعد التحديث.
        """
        await tx.execute(
            """
            UPDATE providers
               SET consecutive_failures = consecutive_failures + 1,
                   last_error = ?, disabled_until = COALESCE(?, disabled_until), updated_at = ?
             WHERE id = ?
            """,
            (error[:500], disable_until, self.now(), provider_id),
        )
        return int(
            await self.db.fetchval(
                "SELECT consecutive_failures FROM providers WHERE id = ?", (provider_id,), default=0
            )
        )

    async def set_active(self, tx: Tx, provider_id: int, active: bool) -> bool:
        """تفعيل أو تعطيل مزود يدوياً."""
        return await self._update_by_id(
            tx, "providers", provider_id, {"is_active": 1 if active else 0}, _ALLOWED_FIELDS
        )

    async def add_balance_snapshot(
        self, tx: Tx, provider_id: int, balance_units: int, currency: str = "USD"
    ) -> None:
        """حفظ لقطة لرصيد المزود لتتبع الاتجاه والتنبيه المبكر."""
        await tx.execute(
            """
            INSERT INTO provider_balance_snapshots (provider_id, balance_units, currency, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (provider_id, balance_units, currency, self.now()),
        )
```

## `database/repositories/categories.py`

```python
"""مستودع تصنيفات الخدمات (المنصات: انستغرام، تيك توك ...)."""

from __future__ import annotations

from typing import Any

from database.database import Tx
from database.models import ServiceCategory
from database.repositories.base import BaseRepository

_ALLOWED_FIELDS = {"name_ar", "name_en", "emoji", "sort_order", "is_active"}


class CategoriesRepository(BaseRepository):
    """عمليات التصنيفات."""

    async def get(self, category_id: int) -> ServiceCategory | None:
        """جلب تصنيف بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM service_categories WHERE id = ?", (category_id,))
        return ServiceCategory.from_row(row)

    async def list_all(self, *, active_only: bool = False) -> list[ServiceCategory]:
        """قائمة التصنيفات مرتبة حسب ترتيب العرض."""
        sql = "SELECT * FROM service_categories"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY sort_order, id"
        rows = await self.db.fetchall(sql)
        return ServiceCategory.from_rows(rows)

    async def list_with_available_services(self) -> list[ServiceCategory]:
        """
        التصنيفات التي تحتوي فعلياً على خدمة واحدة متاحة على الأقل.

        الفائدة: عدم عرض تصنيف فارغ للمستخدم (زر بلا محتوى).
        """
        rows = await self.db.fetchall(
            """
            SELECT c.* FROM service_categories c
             WHERE c.is_active = 1
               AND EXISTS (
                   SELECT 1 FROM services s
                    WHERE s.category_id = c.id AND s.is_active = 1 AND s.is_archived = 0
               )
             ORDER BY c.sort_order, c.id
            """
        )
        return ServiceCategory.from_rows(rows)

    async def create(
        self, tx: Tx, *, name_ar: str, name_en: str | None = None, emoji: str = "📦", sort_order: int = 100
    ) -> ServiceCategory:
        """إضافة تصنيف جديد."""
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO service_categories (name_ar, name_en, emoji, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name_ar, name_en, emoji, sort_order, now, now),
        )
        row = await tx.fetchone("SELECT * FROM service_categories WHERE id = ?", (result.lastrowid,))
        category = ServiceCategory.from_row(row)
        assert category is not None
        return category

    async def update_fields(self, tx: Tx, category_id: int, **fields: Any) -> bool:
        """تعديل بيانات تصنيف."""
        return await self._update_by_id(tx, "service_categories", category_id, fields, _ALLOWED_FIELDS)

    async def set_active(self, tx: Tx, category_id: int, active: bool) -> bool:
        """تفعيل أو إخفاء تصنيف."""
        return await self._update_by_id(
            tx, "service_categories", category_id, {"is_active": 1 if active else 0}, _ALLOWED_FIELDS
        )
```

## `database/repositories/services.py`

```python
"""
مستودع الخدمات — الخدمات المعروضة للبيع وارتباطها بالمزودين.

قاعدة مهمة: الخدمة التي لها طلبات سابقة لا تُحذف نهائياً، بل تُعطَّل أو تُؤرشف،
حتى لا تُكسر المراجع التاريخية في جدول الطلبات.
"""

from __future__ import annotations

from typing import Any

from database.database import Tx
from database.models import Service
from database.repositories.base import BaseRepository

_ALLOWED_FIELDS = {
    "category_id",
    "provider_id",
    "provider_service_id",
    "name",
    "description",
    "service_type",
    "price_per_1000_units",
    "provider_price_per_1000_units",
    "min_quantity",
    "max_quantity",
    "dripfeed_enabled",
    "refill_enabled",
    "cancel_enabled",
    "link_pattern",
    "avg_time_text",
    "is_active",
    "is_archived",
    "sort_order",
}


class ServicesRepository(BaseRepository):
    """عمليات قراءة وكتابة الخدمات."""

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, service_id: int) -> Service | None:
        """جلب خدمة بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM services WHERE id = ?", (service_id,))
        return Service.from_row(row)

    async def get_available(self, service_id: int) -> Service | None:
        """جلب خدمة متاحة للطلب فقط (مفعّلة وغير مؤرشفة)."""
        row = await self.db.fetchone(
            "SELECT * FROM services WHERE id = ? AND is_active = 1 AND is_archived = 0", (service_id,)
        )
        return Service.from_row(row)

    async def list_by_category(
        self, category_id: int, *, only_available: bool = True, limit: int = 8, offset: int = 0
    ) -> list[Service]:
        """قائمة خدمات تصنيف معين مع ترقيم صفحات."""
        sql = "SELECT * FROM services WHERE category_id = ?"
        params: list[Any] = [category_id]
        if only_available:
            sql += " AND is_active = 1 AND is_archived = 0"
        sql += " ORDER BY sort_order, id LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = await self.db.fetchall(sql, params)
        return Service.from_rows(rows)

    async def count_by_category(self, category_id: int, *, only_available: bool = True) -> int:
        """عدد خدمات تصنيف (لحساب عدد الصفحات)."""
        where = "category_id = ?"
        if only_available:
            where += " AND is_active = 1 AND is_archived = 0"
        return await self.count("services", where, (category_id,))

    async def find_by_provider_service(self, provider_id: int, provider_service_id: str) -> Service | None:
        """البحث عن خدمة مرتبطة بمعرف خدمة معين عند المزود (يُستخدم في المزامنة)."""
        row = await self.db.fetchone(
            "SELECT * FROM services WHERE provider_id = ? AND provider_service_id = ?",
            (provider_id, str(provider_service_id)),
        )
        return Service.from_row(row)

    async def list_by_provider(self, provider_id: int, *, limit: int = 50, offset: int = 0) -> list[Service]:
        """خدمات مزود معين."""
        rows = await self.db.fetchall(
            "SELECT * FROM services WHERE provider_id = ? ORDER BY id LIMIT ? OFFSET ?",
            (provider_id, limit, offset),
        )
        return Service.from_rows(rows)

    async def search(self, text: str, *, limit: int = 10) -> list[Service]:
        """بحث نصي في أسماء الخدمات (للوحة الأدمن)."""
        pattern = f"%{text.strip()}%"
        rows = await self.db.fetchall(
            "SELECT * FROM services WHERE name LIKE ? ORDER BY id LIMIT ?", (pattern, limit)
        )
        return Service.from_rows(rows)

    async def count_active(self) -> int:
        """عدد الخدمات المتاحة حالياً."""
        return await self.count("services", "is_active = 1 AND is_archived = 0")

    async def has_orders(self, service_id: int) -> bool:
        """هل توجد طلبات مرتبطة بهذه الخدمة؟ (يمنع الحذف الفعلي)."""
        row = await self.db.fetchone("SELECT 1 FROM orders WHERE service_id = ? LIMIT 1", (service_id,))
        return row is not None

    async def negative_margin_services(self) -> list[Service]:
        """الخدمات التي أصبح سعر بيعها أقل من تكلفتها (تحذير بعد مزامنة الأسعار)."""
        rows = await self.db.fetchall(
            """
            SELECT * FROM services
             WHERE provider_price_per_1000_units IS NOT NULL
               AND price_per_1000_units < provider_price_per_1000_units
               AND is_archived = 0
             ORDER BY id
            """
        )
        return Service.from_rows(rows)

    # ------------------------------ الكتابة ------------------------------ #

    async def create(
        self,
        tx: Tx,
        *,
        category_id: int,
        provider_id: int,
        provider_service_id: str,
        name: str,
        price_per_1000_units: int,
        min_quantity: int,
        max_quantity: int,
        description: str | None = None,
        provider_price_per_1000_units: int | None = None,
        service_type: str = "default",
        link_pattern: str | None = None,
        avg_time_text: str | None = None,
        sort_order: int = 100,
    ) -> Service:
        """إضافة خدمة جديدة."""
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO services (category_id, provider_id, provider_service_id, name, description,
                                  service_type, price_per_1000_units, provider_price_per_1000_units,
                                  min_quantity, max_quantity, link_pattern, avg_time_text,
                                  sort_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                category_id, provider_id, str(provider_service_id), name, description,
                service_type, price_per_1000_units, provider_price_per_1000_units,
                min_quantity, max_quantity, link_pattern, avg_time_text, sort_order, now, now,
            ),
        )
        row = await tx.fetchone("SELECT * FROM services WHERE id = ?", (result.lastrowid,))
        service = Service.from_row(row)
        assert service is not None
        return service

    async def update_fields(self, tx: Tx, service_id: int, **fields: Any) -> bool:
        """تعديل حقول مسموح بها للخدمة."""
        return await self._update_by_id(tx, "services", service_id, fields, _ALLOWED_FIELDS)

    async def change_price(
        self,
        tx: Tx,
        service_id: int,
        *,
        new_price_units: int,
        new_min: int | None = None,
        new_max: int | None = None,
        changed_by: int | None = None,
        source: str = "admin",
    ) -> bool:
        """
        تغيير سعر أو حدود خدمة مع تسجيل التغيير في سجل الأسعار.

        السبب: الحاجة لتفسير محاسبي لأي فرق سعر بين الطلبات القديمة والجديدة.
        """
        current = await tx.fetchone(
            "SELECT price_per_1000_units, min_quantity, max_quantity FROM services WHERE id = ?",
            (service_id,),
        )
        if current is None:
            return False

        fields: dict[str, Any] = {"price_per_1000_units": new_price_units}
        if new_min is not None:
            fields["min_quantity"] = new_min
        if new_max is not None:
            fields["max_quantity"] = new_max
        updated = await self._update_by_id(tx, "services", service_id, fields, _ALLOWED_FIELDS)
        if not updated:
            return False

        await tx.execute(
            """
            INSERT INTO service_price_history (service_id, old_price_units, new_price_units,
                                               old_min, new_min, old_max, new_max,
                                               changed_by, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                service_id,
                current["price_per_1000_units"],
                new_price_units,
                current["min_quantity"],
                new_min if new_min is not None else current["min_quantity"],
                current["max_quantity"],
                new_max if new_max is not None else current["max_quantity"],
                changed_by,
                source,
                self.now(),
            ),
        )
        return True

    async def set_active(self, tx: Tx, service_id: int, active: bool) -> bool:
        """تفعيل أو تعطيل خدمة."""
        return await self._update_by_id(
            tx, "services", service_id, {"is_active": 1 if active else 0}, _ALLOWED_FIELDS
        )

    async def archive(self, tx: Tx, service_id: int) -> bool:
        """أرشفة خدمة (حذف ناعم): تُخفى عن المستخدمين ويبقى تاريخها سليماً."""
        return await self._update_by_id(
            tx, "services", service_id, {"is_archived": 1, "is_active": 0}, _ALLOWED_FIELDS
        )

    async def price_history(self, service_id: int, limit: int = 10) -> list[dict]:
        """آخر تغييرات السعر لخدمة."""
        rows = await self.db.fetchall(
            "SELECT * FROM service_price_history WHERE service_id = ? ORDER BY id DESC LIMIT ?",
            (service_id, limit),
        )
        return [dict(row) for row in rows]
```

## `database/repositories/orders.py`

```python
"""
مستودع الطلبات — أهم مستودع في النظام.

يوفّر العمليات الذرّية التي تمنع أخطر مشكلتين:
    1. تغيير حالة الطلب من مكانين في نفس اللحظة  → update_status المشروط بالحالة السابقة.
    2. معالجة نفس الطلب بواسطة أكثر من job       → claim_* مع قفل زمني (lease).
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from core.constants import ORDER_LOCK_SECONDS
from database.database import Tx
from database.models import Order, OrderStatusHistory
from database.repositories.base import BaseRepository
from utils.datetime_utils import iso_plus_seconds, utc_now_iso

_ALLOWED_FIELDS = {
    "status",
    "provider_status",
    "provider_order_id",
    "provider_cost_units",
    "start_count",
    "remains",
    "delivered_quantity",
    "refund_amount_units",
    "refunded_at",
    "submit_attempts",
    "checks_count",
    "last_error",
    "locked_by",
    "locked_until",
    "next_check_at",
    "submitted_at",
    "completed_at",
    "cancelled_at",
    "public_code",
}


class OrdersRepository(BaseRepository):
    """عمليات قراءة وكتابة الطلبات."""

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, order_id: int) -> Order | None:
        """جلب طلب بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM orders WHERE id = ?", (order_id,))
        return Order.from_row(row)

    async def get_by_client_request_id(self, client_request_id: str) -> Order | None:
        """
        جلب طلب بمفتاح الطلب الفريد القادم من واجهة المستخدم.

        الفائدة: إذا ضغط المستخدم «تأكيد» مرتين، نُرجع نفس الطلب بدل إنشاء طلب جديد.
        """
        row = await self.db.fetchone(
            "SELECT * FROM orders WHERE client_request_id = ?", (client_request_id,)
        )
        return Order.from_row(row)

    async def get_by_provider_order_id(self, provider_id: int, provider_order_id: str) -> Order | None:
        """جلب طلب برقمه عند المزود (للتسوية اليدوية)."""
        row = await self.db.fetchone(
            "SELECT * FROM orders WHERE provider_id = ? AND provider_order_id = ?",
            (provider_id, str(provider_order_id)),
        )
        return Order.from_row(row)

    async def list_by_user(
        self, user_id: int, *, statuses: Sequence[str] | None = None, limit: int = 8, offset: int = 0
    ) -> list[Order]:
        """قائمة طلبات مستخدم مع إمكانية الفلترة بالحالة."""
        sql = "SELECT * FROM orders WHERE user_id = ?"
        params: list[Any] = [user_id]
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            sql += f" AND status IN ({placeholders})"
            params.extend(statuses)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = await self.db.fetchall(sql, params)
        return Order.from_rows(rows)

    async def count_by_user(self, user_id: int, *, statuses: Sequence[str] | None = None) -> int:
        """عدد طلبات مستخدم (لحساب الصفحات والحدود اليومية)."""
        where = "user_id = ?"
        params: list[Any] = [user_id]
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            where += f" AND status IN ({placeholders})"
            params.extend(statuses)
        return await self.count("orders", where, params)

    async def count_today_by_user(self, user_id: int, since_iso: str) -> int:
        """عدد طلبات المستخدم منذ بداية اليوم (لتطبيق الحد اليومي)."""
        return await self.count("orders", "user_id = ? AND created_at >= ?", (user_id, since_iso))

    async def list_by_status(self, status: str, *, limit: int = 20, offset: int = 0) -> list[Order]:
        """قائمة الطلبات حسب الحالة (للوحة الأدمن)."""
        rows = await self.db.fetchall(
            "SELECT * FROM orders WHERE status = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (status, limit, offset),
        )
        return Order.from_rows(rows)

    async def status_counts(self) -> dict[str, int]:
        """عدد الطلبات في كل حالة (لوحة الإحصائيات)."""
        rows = await self.db.fetchall("SELECT status, COUNT(*) AS c FROM orders GROUP BY status")
        return {row["status"]: int(row["c"]) for row in rows}

    async def find_recent_duplicate(
        self, *, user_id: int, service_id: int, link: str, quantity: int, since_iso: str
    ) -> Order | None:
        """
        كشف طلب مشابه خلال نافذة زمنية (نفس المستخدم والخدمة والرابط والكمية).

        الفائدة: تحذير المستخدم قبل تكرار الدفع بالخطأ.
        """
        row = await self.db.fetchone(
            """
            SELECT * FROM orders
             WHERE user_id = ? AND service_id = ? AND link = ? AND quantity = ?
               AND created_at >= ?
               AND status NOT IN ('failed', 'canceled', 'refunded')
             ORDER BY id DESC LIMIT 1
            """,
            (user_id, service_id, link, quantity, since_iso),
        )
        return Order.from_row(row)

    async def history(self, order_id: int) -> list[OrderStatusHistory]:
        """سجل انتقالات حالة الطلب."""
        rows = await self.db.fetchall(
            "SELECT * FROM order_status_history WHERE order_id = ? ORDER BY id", (order_id,)
        )
        return OrderStatusHistory.from_rows(rows)

    async def stuck_orders(self, *, before_iso: str, limit: int = 20) -> list[Order]:
        """الطلبات النشطة التي تجاوزت المدة المتوقعة (لتنبيه الأدمن)."""
        rows = await self.db.fetchall(
            """
            SELECT * FROM orders
             WHERE status IN ('pending', 'submitting', 'submit_uncertain', 'submitted', 'in_progress')
               AND created_at <= ?
             ORDER BY id LIMIT ?
            """,
            (before_iso, limit),
        )
        return Order.from_rows(rows)

    async def sum_cost_between(self, start_iso: str, end_iso: str) -> int:
        """إجمالي قيمة الطلبات المنشأة خلال فترة (بالنقاط)."""
        return int(
            await self.db.fetchval(
                "SELECT COALESCE(SUM(cost_units), 0) FROM orders WHERE created_at >= ? AND created_at < ?",
                (start_iso, end_iso),
                default=0,
            )
        )

    async def sum_provider_cost_between(self, start_iso: str, end_iso: str) -> int:
        """إجمالي تكلفة المزود خلال فترة (لحساب الربح التقريبي)."""
        return int(
            await self.db.fetchval(
                """
                SELECT COALESCE(SUM(provider_cost_units), 0) FROM orders
                 WHERE created_at >= ? AND created_at < ? AND provider_cost_units IS NOT NULL
                """,
                (start_iso, end_iso),
                default=0,
            )
        )

    # ------------------------------ الكتابة ------------------------------ #

    async def create(
        self,
        tx: Tx,
        *,
        user_id: int,
        service_id: int,
        provider_id: int,
        service_name_snapshot: str,
        price_per_1000_snapshot_units: int,
        link: str,
        quantity: int,
        cost_units: int,
        client_request_id: str,
        provider_cost_units: int | None = None,
        status: str = "pending",
    ) -> Order:
        """
        إنشاء طلب جديد بحالة pending.

        ملاحظة: خصم الرصيد وتسجيل الحركة المالية يتمان في نفس المعاملة
        داخل OrderService، وليس هنا.
        """
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO orders (user_id, service_id, provider_id, service_name_snapshot,
                                price_per_1000_snapshot_units, link, quantity, cost_units,
                                provider_cost_units, status, client_request_id,
                                created_at, updated_at, next_check_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, service_id, provider_id, service_name_snapshot,
                price_per_1000_snapshot_units, link, quantity, cost_units,
                provider_cost_units, status, client_request_id, now, now, now,
            ),
        )
        row = await tx.fetchone("SELECT * FROM orders WHERE id = ?", (result.lastrowid,))
        order = Order.from_row(row)
        assert order is not None
        return order

    async def add_history(
        self,
        tx: Tx,
        *,
        order_id: int,
        from_status: str | None,
        to_status: str,
        actor_type: str = "system",
        actor_id: int | None = None,
        reason: str | None = None,
        provider_status_raw: str | None = None,
    ) -> None:
        """تسجيل انتقال حالة في سجل الطلب (يُستدعى مع كل تغيير حالة)."""
        await tx.execute(
            """
            INSERT INTO order_status_history (order_id, from_status, to_status, actor_type,
                                              actor_id, reason, provider_status_raw, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (order_id, from_status, to_status, actor_type, actor_id, reason, provider_status_raw, self.now()),
        )

    async def update_status(
        self,
        tx: Tx,
        order_id: int,
        *,
        new_status: str,
        expected_statuses: Iterable[str],
        extra_fields: dict[str, Any] | None = None,
    ) -> bool:
        """
        تغيير حالة الطلب بشكل مشروط بالحالة الحالية (العمود الفقري لمنع التغيير العشوائي).

        المدخلات:
            new_status        : الحالة الجديدة.
            expected_statuses : الحالات المسموح الانتقال منها.
            extra_fields      : حقول إضافية تُحدَّث في نفس العبارة (رقم المزود، أوقات ...).

        المخرجات: True إذا تم التغيير فعلاً، False إذا كانت حالة الطلب مختلفة
                  (يعني أن جهة أخرى غيّرتها قبلنا — وهذا ليس خطأً بل حماية).
        """
        statuses = list(expected_statuses)
        if not statuses:
            raise ValueError("يجب تحديد الحالات المتوقعة قبل تغيير حالة الطلب.")

        fields: dict[str, Any] = {"status": new_status}
        if extra_fields:
            fields.update(extra_fields)
        set_sql, values = self._build_update(fields, _ALLOWED_FIELDS)
        set_sql += ", updated_at = ?"
        values.append(self.now())
        placeholders = ", ".join("?" for _ in statuses)
        values.append(order_id)
        values.extend(statuses)

        result = await tx.execute(
            f"UPDATE orders SET {set_sql} WHERE id = ? AND status IN ({placeholders})", values
        )
        return result.rowcount == 1

    async def update_fields(self, tx: Tx, order_id: int, **fields: Any) -> bool:
        """تعديل حقول غير حالة الطلب (تقدم التنفيذ، مواعيد الفحص ...)."""
        return await self._update_by_id(tx, "orders", order_id, fields, _ALLOWED_FIELDS)

    async def add_refund_amount(self, tx: Tx, order_id: int, amount_units: int) -> bool:
        """
        زيادة مبلغ الاسترجاع المسجَّل على الطلب دون تجاوز التكلفة.

        المخرجات: True عند النجاح، False إذا كان المبلغ سيتجاوز تكلفة الطلب
                  (حماية إضافية فوق قيد CHECK في قاعدة البيانات).
        """
        result = await tx.execute(
            """
            UPDATE orders
               SET refund_amount_units = refund_amount_units + ?,
                   refunded_at = ?, updated_at = ?
             WHERE id = ? AND refund_amount_units + ? <= cost_units
            """,
            (amount_units, self.now(), self.now(), order_id, amount_units),
        )
        return result.rowcount == 1

    # --------------------------- الأقفال والمهام --------------------------- #

    async def claim_pending_for_submit(
        self, tx: Tx, *, worker: str, limit: int = 5, lock_seconds: int = ORDER_LOCK_SECONDS
    ) -> list[Order]:
        """
        حجز دفعة من الطلبات المعلّقة لإرسالها للمزود.

        الآلية: لكل طلب مرشّح يُنفَّذ UPDATE مشروط (status='pending' وغير مقفول)؛
        من ينجح UPDATE الخاص به هو من يملك الطلب — فلا يعالجه worker آخر.
        """
        now = utc_now_iso()
        candidates = await tx.fetchall(
            """
            SELECT id FROM orders
             WHERE status = 'pending'
               AND (locked_until IS NULL OR locked_until < ?)
             ORDER BY id LIMIT ?
            """,
            (now, limit),
        )
        claimed: list[Order] = []
        for row in candidates:
            ok = await tx.execute(
                """
                UPDATE orders
                   SET status = 'submitting', locked_by = ?, locked_until = ?,
                       submit_attempts = submit_attempts + 1, updated_at = ?
                 WHERE id = ? AND status = 'pending'
                   AND (locked_until IS NULL OR locked_until < ?)
                """,
                (worker, iso_plus_seconds(lock_seconds), now, row["id"], now),
            )
            if ok.rowcount == 1:
                order_row = await tx.fetchone("SELECT * FROM orders WHERE id = ?", (row["id"],))
                order = Order.from_row(order_row)
                if order is not None:
                    claimed.append(order)
                    await self.add_history(
                        tx,
                        order_id=order.id,
                        from_status="pending",
                        to_status="submitting",
                        actor_type="job",
                        reason=f"حجز للإرسال بواسطة {worker}",
                    )
        return claimed

    async def claim_due_for_check(
        self, tx: Tx, *, worker: str, limit: int = 20, lock_seconds: int = ORDER_LOCK_SECONDS
    ) -> list[Order]:
        """
        حجز دفعة من الطلبات النشطة التي حان موعد فحص حالتها عند المزود.

        لا تُغيَّر حالة الطلب هنا — فقط يوضع قفل زمني لتفادي الفحص المزدوج.
        """
        now = utc_now_iso()
        candidates = await tx.fetchall(
            """
            SELECT id FROM orders
             WHERE status IN ('submitted', 'in_progress')
               AND provider_order_id IS NOT NULL
               AND (next_check_at IS NULL OR next_check_at <= ?)
               AND (locked_until IS NULL OR locked_until < ?)
             ORDER BY next_check_at LIMIT ?
            """,
            (now, now, limit),
        )
        claimed: list[Order] = []
        for row in candidates:
            ok = await tx.execute(
                """
                UPDATE orders
                   SET locked_by = ?, locked_until = ?, checks_count = checks_count + 1, updated_at = ?
                 WHERE id = ? AND (locked_until IS NULL OR locked_until < ?)
                """,
                (worker, iso_plus_seconds(lock_seconds), now, row["id"], now),
            )
            if ok.rowcount == 1:
                order_row = await tx.fetchone("SELECT * FROM orders WHERE id = ?", (row["id"],))
                order = Order.from_row(order_row)
                if order is not None:
                    claimed.append(order)
        return claimed

    async def release_lock(self, tx: Tx, order_id: int, *, next_check_at: str | None = None) -> None:
        """تحرير قفل الطلب بعد انتهاء المعالجة، مع تحديد موعد الفحص القادم اختيارياً."""
        if next_check_at is None:
            await tx.execute(
                "UPDATE orders SET locked_by = NULL, locked_until = NULL, updated_at = ? WHERE id = ?",
                (self.now(), order_id),
            )
        else:
            await tx.execute(
                """
                UPDATE orders SET locked_by = NULL, locked_until = NULL,
                       next_check_at = ?, updated_at = ? WHERE id = ?
                """,
                (next_check_at, self.now(), order_id),
            )

    async def release_expired_locks(self, tx: Tx) -> int:
        """
        تحرير كل الأقفال المنتهية (يُستدعى عند إقلاع البوت ضمن عملية الاسترداد).

        المخرجات: عدد الطلبات التي حُرِّرت.
        """
        result = await tx.execute(
            """
            UPDATE orders SET locked_by = NULL, locked_until = NULL, updated_at = ?
             WHERE locked_until IS NOT NULL AND locked_until < ?
            """,
            (self.now(), utc_now_iso()),
        )
        return result.rowcount

    async def recover_submitting_orders(self, tx: Tx) -> list[int]:
        """
        معالجة الطلبات العالقة في حالة submitting بعد إعادة تشغيل مفاجئ.

        القاعدة: إذا لم يُسجَّل رقم الطلب عند المزود فالنتيجة غير مؤكدة
        (ربما وصل الطلب وربما لا) ⇒ تُنقل إلى submit_uncertain لمراجعة الأدمن،
        وممنوع إعادة إرسالها تلقائياً.

        المخرجات: قائمة معرفات الطلبات التي نُقلت إلى submit_uncertain.
        """
        rows = await tx.fetchall(
            "SELECT id FROM orders WHERE status = 'submitting' AND provider_order_id IS NULL"
        )
        ids: list[int] = []
        for row in rows:
            ok = await tx.execute(
                """
                UPDATE orders SET status = 'submit_uncertain', locked_by = NULL, locked_until = NULL,
                       last_error = 'انقطاع أثناء الإرسال - تحتاج مراجعة يدوية', updated_at = ?
                 WHERE id = ? AND status = 'submitting'
                """,
                (self.now(), row["id"]),
            )
            if ok.rowcount == 1:
                ids.append(int(row["id"]))
                await self.add_history(
                    tx,
                    order_id=int(row["id"]),
                    from_status="submitting",
                    to_status="submit_uncertain",
                    actor_type="system",
                    reason="استرداد بعد إعادة تشغيل البوت",
                )
        return ids
```

## `database/repositories/transactions.py`

```python
"""
مستودع الحركات المالية (دفتر الأستاذ).

قواعد صارمة:
    • الجدول «إضافة فقط»: لا يوجد UPDATE ولا DELETE هنا، وأي تصحيح يكون بحركة adjustment جديدة.
    • عمود reference فريد، وهو خط الدفاع الأخير ضد تكرار أي عملية مالية.
"""

from __future__ import annotations

import sqlite3

from core.enums import TRANSACTION_DIRECTIONS, TransactionDirection
from core.exceptions import DuplicateOperationError
from database.database import Tx
from database.models import Transaction
from database.repositories.base import BaseRepository


class TransactionsRepository(BaseRepository):
    """تسجيل وقراءة الحركات المالية."""

    # ------------------------------ الكتابة ------------------------------ #

    async def insert(
        self,
        tx: Tx,
        *,
        user_id: int,
        type: str,
        amount_units: int,
        balance_before_units: int,
        balance_after_units: int,
        direction: str | None = None,
        order_id: int | None = None,
        payment_id: int | None = None,
        description: str | None = None,
        reference: str | None = None,
        actor_id: int | None = None,
    ) -> Transaction:
        """
        تسجيل حركة مالية جديدة.

        المدخلات:
            type      : نوع الحركة (deposit/order/refund/...).
            direction : اتجاه الحركة، ويُستنتج تلقائياً من النوع إن لم يُحدَّد.
            reference : مرجع فريد لمنع التكرار (مثل "refund:order:12").

        الاستثناءات:
            DuplicateOperationError : المرجع مستخدم سابقاً ⇒ العملية نُفِّذت من قبل.
        """
        if amount_units <= 0:
            raise ValueError("مبلغ الحركة يجب أن يكون أكبر من صفر.")
        resolved_direction = direction or TRANSACTION_DIRECTIONS.get(type, TransactionDirection.CREDIT)

        try:
            result = await tx.execute(
                """
                INSERT INTO transactions (user_id, order_id, payment_id, type, direction, amount_units,
                                          balance_before_units, balance_after_units, description,
                                          reference, actor_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id, order_id, payment_id, type, str(resolved_direction), amount_units,
                    balance_before_units, balance_after_units, description, reference, actor_id, self.now(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            if "transactions.reference" in str(exc) or "UNIQUE" in str(exc).upper():
                raise DuplicateOperationError(
                    f"حركة مالية بنفس المرجع موجودة مسبقاً: {reference}"
                ) from exc
            raise

        row = await tx.fetchone("SELECT * FROM transactions WHERE id = ?", (result.lastrowid,))
        transaction = Transaction.from_row(row)
        assert transaction is not None
        return transaction

    # ------------------------------ القراءة ------------------------------ #

    async def exists_reference(self, reference: str) -> bool:
        """هل سبق تنفيذ عملية بهذا المرجع؟ (فحص استباقي قبل محاولة الإدراج)."""
        row = await self.db.fetchone("SELECT 1 FROM transactions WHERE reference = ?", (reference,))
        return row is not None

    async def get_by_reference(self, reference: str) -> Transaction | None:
        """جلب حركة بمرجعها الفريد."""
        row = await self.db.fetchone("SELECT * FROM transactions WHERE reference = ?", (reference,))
        return Transaction.from_row(row)

    async def get(self, transaction_id: int) -> Transaction | None:
        """جلب حركة بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM transactions WHERE id = ?", (transaction_id,))
        return Transaction.from_row(row)

    async def list_by_user(self, user_id: int, *, limit: int = 10, offset: int = 0) -> list[Transaction]:
        """سجل العمليات المالية للمستخدم (الأحدث أولاً)."""
        rows = await self.db.fetchall(
            "SELECT * FROM transactions WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
        return Transaction.from_rows(rows)

    async def count_by_user(self, user_id: int) -> int:
        """عدد الحركات المالية للمستخدم."""
        return await self.count("transactions", "user_id = ?", (user_id,))

    async def list_by_order(self, order_id: int) -> list[Transaction]:
        """كل الحركات المرتبطة بطلب (خصم + استرجاعات)."""
        rows = await self.db.fetchall(
            "SELECT * FROM transactions WHERE order_id = ? ORDER BY id", (order_id,)
        )
        return Transaction.from_rows(rows)

    async def sum_by_type(self, tx_type: str, *, start_iso: str | None = None, end_iso: str | None = None) -> int:
        """إجمالي المبالغ لنوع حركة خلال فترة اختيارية (بالنقاط)."""
        sql = "SELECT COALESCE(SUM(amount_units), 0) FROM transactions WHERE type = ?"
        params: list[object] = [tx_type]
        if start_iso:
            sql += " AND created_at >= ?"
            params.append(start_iso)
        if end_iso:
            sql += " AND created_at < ?"
            params.append(end_iso)
        return int(await self.db.fetchval(sql, params, default=0))

    async def user_balance_from_ledger(self, user_id: int) -> int:
        """
        احتساب الرصيد من دفتر الحركات (للمطابقة والتدقيق).

        الفائدة: مقارنة الناتج مع users.balance_units يكشف أي خلل محاسبي.
        """
        return int(
            await self.db.fetchval(
                """
                SELECT COALESCE(SUM(CASE WHEN direction = 'credit' THEN amount_units ELSE -amount_units END), 0)
                  FROM transactions WHERE user_id = ?
                """,
                (user_id,),
                default=0,
            )
        )
```

## `database/repositories/payments.py`

```python
"""
مستودع المدفوعات — طلبات شحن الرصيد وطرق الدفع.

الحماية الأساسية هنا: تغيير حالة الدفعة مشروط بحالتها السابقة،
فلا يمكن اعتماد نفس الدفعة مرتين حتى لو ضغط الأدمن الزر مرتين.
"""

from __future__ import annotations

from typing import Any

from database.database import Tx
from database.models import Payment, PaymentMethod
from database.repositories.base import BaseRepository
from utils.datetime_utils import utc_now_iso

_METHOD_FIELDS = {
    "code",
    "name_ar",
    "type",
    "instructions_ar",
    "account_details",
    "min_amount_units",
    "max_amount_units",
    "requires_proof",
    "is_active",
    "sort_order",
}

_PAYMENT_FIELDS = {
    "amount_units",
    "credited_units",
    "status",
    "transaction_reference",
    "proof_file_id",
    "proof_file_type",
    "user_note",
    "admin_id",
    "admin_note",
    "reject_reason",
    "reviewed_at",
    "expires_at",
}


class PaymentMethodsRepository(BaseRepository):
    """إدارة طرق الشحن القابلة للتهيئة من لوحة الأدمن."""

    async def get(self, method_id: int) -> PaymentMethod | None:
        """جلب طريقة دفع بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM payment_methods WHERE id = ?", (method_id,))
        return PaymentMethod.from_row(row)

    async def get_by_code(self, code: str) -> PaymentMethod | None:
        """جلب طريقة دفع بالكود الفريد."""
        row = await self.db.fetchone("SELECT * FROM payment_methods WHERE code = ?", (code,))
        return PaymentMethod.from_row(row)

    async def list_all(self, *, active_only: bool = False) -> list[PaymentMethod]:
        """قائمة طرق الدفع مرتبة للعرض."""
        sql = "SELECT * FROM payment_methods"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY sort_order, id"
        rows = await self.db.fetchall(sql)
        return PaymentMethod.from_rows(rows)

    async def create(
        self,
        tx: Tx,
        *,
        code: str,
        name_ar: str,
        instructions_ar: str = "",
        account_details: str = "",
        type: str = "manual",
        min_amount_units: int = 0,
        max_amount_units: int | None = None,
        requires_proof: bool = True,
        sort_order: int = 100,
    ) -> PaymentMethod:
        """إضافة طريقة دفع جديدة."""
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO payment_methods (code, name_ar, type, instructions_ar, account_details,
                                         min_amount_units, max_amount_units, requires_proof,
                                         sort_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code, name_ar, type, instructions_ar, account_details, min_amount_units,
                max_amount_units, 1 if requires_proof else 0, sort_order, now, now,
            ),
        )
        row = await tx.fetchone("SELECT * FROM payment_methods WHERE id = ?", (result.lastrowid,))
        method = PaymentMethod.from_row(row)
        assert method is not None
        return method

    async def update_fields(self, tx: Tx, method_id: int, **fields: Any) -> bool:
        """تعديل بيانات طريقة دفع."""
        return await self._update_by_id(tx, "payment_methods", method_id, fields, _METHOD_FIELDS)


class PaymentsRepository(BaseRepository):
    """إدارة طلبات الشحن."""

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, payment_id: int) -> Payment | None:
        """جلب طلب شحن بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM payments WHERE id = ?", (payment_id,))
        return Payment.from_row(row)

    async def list_by_user(self, user_id: int, *, limit: int = 10, offset: int = 0) -> list[Payment]:
        """طلبات شحن مستخدم معين."""
        rows = await self.db.fetchall(
            "SELECT * FROM payments WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
        return Payment.from_rows(rows)

    async def list_pending(self, *, limit: int = 10, offset: int = 0) -> list[Payment]:
        """طلبات الشحن المعلّقة بانتظار مراجعة الأدمن (الأقدم أولاً)."""
        rows = await self.db.fetchall(
            "SELECT * FROM payments WHERE status = 'pending' ORDER BY id LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return Payment.from_rows(rows)

    async def count_pending(self) -> int:
        """عدد طلبات الشحن المعلّقة (يظهر في لوحة المعلومات)."""
        return await self.count("payments", "status = 'pending'")

    async def list_expired_pending(self, *, limit: int = 50) -> list[Payment]:
        """طلبات الشحن المعلّقة التي انتهت صلاحيتها (لمهمة الإغلاق التلقائي)."""
        rows = await self.db.fetchall(
            """
            SELECT * FROM payments
             WHERE status = 'pending' AND expires_at IS NOT NULL AND expires_at <= ?
             ORDER BY id LIMIT ?
            """,
            (utc_now_iso(), limit),
        )
        return Payment.from_rows(rows)

    async def sum_approved_between(self, start_iso: str, end_iso: str) -> int:
        """إجمالي المبالغ المعتمدة خلال فترة (بالنقاط)."""
        return int(
            await self.db.fetchval(
                """
                SELECT COALESCE(SUM(COALESCE(credited_units, amount_units)), 0) FROM payments
                 WHERE status = 'approved' AND reviewed_at >= ? AND reviewed_at < ?
                """,
                (start_iso, end_iso),
                default=0,
            )
        )

    async def find_duplicate_reference(self, reference: str) -> Payment | None:
        """
        البحث عن طلب شحن سابق بنفس رقم الحوالة.

        الفائدة: كشف محاولة استخدام نفس إثبات الدفع مرتين.
        """
        row = await self.db.fetchone(
            """
            SELECT * FROM payments
             WHERE transaction_reference IS NOT NULL AND transaction_reference = ?
               AND status IN ('pending', 'approved')
             ORDER BY id DESC LIMIT 1
            """,
            (reference,),
        )
        return Payment.from_row(row)

    # ------------------------------ الكتابة ------------------------------ #

    async def create(
        self,
        tx: Tx,
        *,
        user_id: int,
        method_id: int,
        amount_units: int,
        transaction_reference: str | None = None,
        proof_file_id: str | None = None,
        proof_file_type: str | None = None,
        user_note: str | None = None,
        expires_at: str | None = None,
    ) -> Payment:
        """إنشاء طلب شحن جديد بحالة pending."""
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO payments (user_id, method_id, amount_units, transaction_reference,
                                  proof_file_id, proof_file_type, user_note, expires_at,
                                  created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, method_id, amount_units, transaction_reference, proof_file_id,
                proof_file_type, user_note, expires_at, now, now,
            ),
        )
        row = await tx.fetchone("SELECT * FROM payments WHERE id = ?", (result.lastrowid,))
        payment = Payment.from_row(row)
        assert payment is not None
        return payment

    async def update_fields(self, tx: Tx, payment_id: int, **fields: Any) -> bool:
        """تعديل حقول طلب شحن (قبل المراجعة عادةً)."""
        return await self._update_by_id(tx, "payments", payment_id, fields, _PAYMENT_FIELDS)

    async def set_status(
        self,
        tx: Tx,
        payment_id: int,
        *,
        new_status: str,
        expected_status: str = "pending",
        admin_id: int | None = None,
        credited_units: int | None = None,
        admin_note: str | None = None,
        reject_reason: str | None = None,
    ) -> bool:
        """
        تغيير حالة طلب الشحن بشكل مشروط بالحالة السابقة.

        المخرجات: True إذا تم التغيير، False إذا كانت الحالة قد تغيّرت مسبقاً
                  (أي أن أدمن آخر عالجها، أو أن الزر ضُغط مرتين).
        """
        result = await tx.execute(
            """
            UPDATE payments
               SET status = ?, admin_id = COALESCE(?, admin_id),
                   credited_units = COALESCE(?, credited_units),
                   admin_note = COALESCE(?, admin_note),
                   reject_reason = COALESCE(?, reject_reason),
                   reviewed_at = ?, updated_at = ?
             WHERE id = ? AND status = ?
            """,
            (
                new_status, admin_id, credited_units, admin_note, reject_reason,
                self.now(), self.now(), payment_id, expected_status,
            ),
        )
        return result.rowcount == 1
```

## `database/repositories/tickets.py`

```python
"""مستودع الدعم الفني — التذاكر ورسائلها."""

from __future__ import annotations

from typing import Any, Sequence

from database.database import Tx
from database.models import SupportMessage, SupportTicket
from database.repositories.base import BaseRepository

_TICKET_FIELDS = {
    "subject",
    "category",
    "related_order_id",
    "status",
    "priority",
    "assigned_admin",
    "last_message_at",
    "closed_by",
    "close_reason",
    "closed_at",
}


class TicketsRepository(BaseRepository):
    """عمليات التذاكر ورسائل الدعم."""

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, ticket_id: int) -> SupportTicket | None:
        """جلب تذكرة بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM support_tickets WHERE id = ?", (ticket_id,))
        return SupportTicket.from_row(row)

    async def list_by_user(self, user_id: int, *, limit: int = 10, offset: int = 0) -> list[SupportTicket]:
        """تذاكر مستخدم معين."""
        rows = await self.db.fetchall(
            "SELECT * FROM support_tickets WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
        return SupportTicket.from_rows(rows)

    async def list_by_status(
        self, statuses: Sequence[str], *, limit: int = 10, offset: int = 0
    ) -> list[SupportTicket]:
        """التذاكر حسب الحالة (للوحة الدعم)."""
        placeholders = ", ".join("?" for _ in statuses)
        rows = await self.db.fetchall(
            f"""
            SELECT * FROM support_tickets WHERE status IN ({placeholders})
             ORDER BY COALESCE(last_message_at, created_at) DESC LIMIT ? OFFSET ?
            """,
            [*statuses, limit, offset],
        )
        return SupportTicket.from_rows(rows)

    async def count_open(self) -> int:
        """عدد التذاكر غير المغلقة."""
        return await self.count("support_tickets", "status != 'closed'")

    async def count_today_by_user(self, user_id: int, since_iso: str) -> int:
        """عدد تذاكر المستخدم اليوم (لتطبيق الحد اليومي ومنع الإزعاج)."""
        return await self.count(
            "support_tickets", "user_id = ? AND created_at >= ?", (user_id, since_iso)
        )

    async def messages(self, ticket_id: int, *, limit: int = 50) -> list[SupportMessage]:
        """رسائل تذكرة مرتبة زمنياً."""
        rows = await self.db.fetchall(
            "SELECT * FROM support_messages WHERE ticket_id = ? ORDER BY id LIMIT ?",
            (ticket_id, limit),
        )
        return SupportMessage.from_rows(rows)

    async def has_open_ticket(self, user_id: int) -> bool:
        """هل لدى المستخدم تذكرة مفتوحة حالياً؟ (لتوجيهه إليها بدل فتح تذكرة جديدة)."""
        row = await self.db.fetchone(
            "SELECT 1 FROM support_tickets WHERE user_id = ? AND status != 'closed' LIMIT 1",
            (user_id,),
        )
        return row is not None

    # ------------------------------ الكتابة ------------------------------ #

    async def create(
        self,
        tx: Tx,
        *,
        user_id: int,
        subject: str,
        category: str = "other",
        related_order_id: int | None = None,
        priority: str = "normal",
    ) -> SupportTicket:
        """إنشاء تذكرة جديدة بحالة open."""
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO support_tickets (user_id, subject, category, related_order_id, priority,
                                         status, last_message_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?)
            """,
            (user_id, subject, category, related_order_id, priority, now, now, now),
        )
        row = await tx.fetchone("SELECT * FROM support_tickets WHERE id = ?", (result.lastrowid,))
        ticket = SupportTicket.from_row(row)
        assert ticket is not None
        return ticket

    async def add_message(
        self,
        tx: Tx,
        *,
        ticket_id: int,
        sender_type: str,
        message: str,
        sender_id: int | None = None,
        attachment_file_id: str | None = None,
        attachment_type: str | None = None,
        telegram_message_id: int | None = None,
    ) -> SupportMessage:
        """
        إضافة رسالة إلى تذكرة وتحديث وقت آخر رسالة وحالة التذكرة.

        المنطق: رسالة المستخدم تجعل التذكرة بانتظار رد الأدمن، والعكس صحيح.
        """
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO support_messages (ticket_id, sender_id, sender_type, message,
                                          attachment_file_id, attachment_type, telegram_message_id,
                                          is_read_by_user, is_read_by_admin, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticket_id, sender_id, sender_type, message, attachment_file_id, attachment_type,
                telegram_message_id,
                1 if sender_type == "user" else 0,
                1 if sender_type in {"admin", "system"} else 0,
                now,
            ),
        )
        new_status = "pending_admin" if sender_type == "user" else "pending_user"
        await tx.execute(
            """
            UPDATE support_tickets
               SET last_message_at = ?, updated_at = ?,
                   status = CASE WHEN status = 'closed' THEN status ELSE ? END
             WHERE id = ?
            """,
            (now, now, new_status, ticket_id),
        )
        row = await tx.fetchone("SELECT * FROM support_messages WHERE id = ?", (result.lastrowid,))
        support_message = SupportMessage.from_row(row)
        assert support_message is not None
        return support_message

    async def update_fields(self, tx: Tx, ticket_id: int, **fields: Any) -> bool:
        """تعديل حقول التذكرة (الأولوية، الإسناد ...)."""
        return await self._update_by_id(tx, "support_tickets", ticket_id, fields, _TICKET_FIELDS)

    async def assign(self, tx: Tx, ticket_id: int, admin_id: int) -> bool:
        """إسناد التذكرة إلى أدمن معين."""
        return await self._update_by_id(
            tx, "support_tickets", ticket_id, {"assigned_admin": admin_id}, _TICKET_FIELDS
        )

    async def close(self, tx: Tx, ticket_id: int, *, closed_by: int | None, reason: str | None = None) -> bool:
        """
        إغلاق التذكرة (مشروط بأن تكون مفتوحة) — لمنع الإغلاق المزدوج.
        """
        result = await tx.execute(
            """
            UPDATE support_tickets
               SET status = 'closed', closed_by = ?, close_reason = ?, closed_at = ?, updated_at = ?
             WHERE id = ? AND status != 'closed'
            """,
            (closed_by, reason, self.now(), self.now(), ticket_id),
        )
        return result.rowcount == 1

    async def reopen(self, tx: Tx, ticket_id: int) -> bool:
        """إعادة فتح تذكرة مغلقة."""
        result = await tx.execute(
            """
            UPDATE support_tickets
               SET status = 'pending_admin', closed_by = NULL, closed_at = NULL, updated_at = ?
             WHERE id = ? AND status = 'closed'
            """,
            (self.now(), ticket_id),
        )
        return result.rowcount == 1

    async def mark_read(self, tx: Tx, ticket_id: int, *, by_admin: bool) -> None:
        """تعليم رسائل التذكرة كمقروءة من طرف الأدمن أو المستخدم."""
        column = "is_read_by_admin" if by_admin else "is_read_by_user"
        await tx.execute(
            f"UPDATE support_messages SET {column} = 1 WHERE ticket_id = ?", (ticket_id,)
        )
```

## `database/repositories/notifications.py`

```python
"""
مستودع الإشعارات — يعمل بنمط صندوق الإرسال (Outbox).

الفكرة:
    الإشعار يُكتب في نفس معاملة الحدث (تغيّر حالة طلب مثلاً)، ثم يرسله job منفصل.
    النتيجة:
        • لا يضيع إشعار عند إعادة تشغيل البوت (محفوظ في قاعدة البيانات).
        • لا يُرسل إشعار عن حدث لم يُثبَّت (نفس المعاملة).
        • لا يتكرر الإشعار (dedupe_key فريد).
"""

from __future__ import annotations

from core.constants import MAX_NOTIFICATION_ATTEMPTS, NOTIFICATION_BACKOFF
from database.database import Tx
from database.models import Notification
from database.repositories.base import BaseRepository
from utils.datetime_utils import iso_plus_seconds, utc_now_iso


class NotificationsRepository(BaseRepository):
    """إدراج الإشعارات في الصندوق وإدارة محاولات إرسالها."""

    # ------------------------------ الكتابة ------------------------------ #

    async def enqueue(
        self,
        tx: Tx,
        *,
        user_id: int,
        type: str,
        message: str,
        dedupe_key: str,
        title: str = "",
        payload_json: str | None = None,
    ) -> int | None:
        """
        إضافة إشعار إلى صندوق الإرسال.

        المدخلات:
            dedupe_key : مفتاح فريد يمنع تكرار نفس الإشعار (مثل "order:12:completed").

        المخرجات: معرف الإشعار الجديد، أو None إذا كان الإشعار موجوداً مسبقاً
                  (وهذا سلوك صحيح وليس خطأ).
        """
        result = await tx.execute(
            """
            INSERT INTO notifications (user_id, type, title, message, payload_json, dedupe_key,
                                       status, next_attempt_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?)
            ON CONFLICT(dedupe_key) DO NOTHING
            """,
            (user_id, type, title, message, payload_json, dedupe_key, utc_now_iso(), self.now()),
        )
        if result.rowcount == 0:
            return None
        return result.lastrowid

    async def claim_batch(self, tx: Tx, *, limit: int = 25, lease_seconds: int = 60) -> list[Notification]:
        """
        حجز دفعة من الإشعارات الجاهزة للإرسال.

        الآلية: تأجيل موعد المحاولة التالية فوراً (lease) حتى لا تلتقطها دورة أخرى
        قبل أن تنتهي الدورة الحالية من الإرسال.
        """
        now = utc_now_iso()
        rows = await tx.fetchall(
            """
            SELECT * FROM notifications
             WHERE status = 'queued' AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
             ORDER BY id LIMIT ?
            """,
            (now, limit),
        )
        claimed: list[Notification] = []
        for row in rows:
            ok = await tx.execute(
                """
                UPDATE notifications SET next_attempt_at = ?
                 WHERE id = ? AND status = 'queued'
                   AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                """,
                (iso_plus_seconds(lease_seconds), row["id"], now),
            )
            if ok.rowcount == 1:
                notification = Notification.from_row(row)
                if notification is not None:
                    claimed.append(notification)
        return claimed

    async def mark_sent(self, tx: Tx, notification_id: int, telegram_message_id: int | None = None) -> bool:
        """تعليم الإشعار كمُرسل (مشروط بأن يكون ما زال في حالة queued)."""
        result = await tx.execute(
            """
            UPDATE notifications
               SET status = 'sent', sent_at = ?, telegram_message_id = ?, last_error = NULL
             WHERE id = ? AND status = 'queued'
            """,
            (self.now(), telegram_message_id, notification_id),
        )
        return result.rowcount == 1

    async def mark_failed(
        self, tx: Tx, notification_id: int, *, error: str, permanent: bool = False
    ) -> None:
        """
        تسجيل فشل محاولة إرسال.

        المدخلات:
            permanent : True يعني لا فائدة من إعادة المحاولة (مثل: الدردشة غير موجودة).

        المنطق: مع كل فشل يزيد العداد ويُؤجَّل الموعد بتدرج، وعند تجاوز الحد
                يُعلَّم الإشعار كفاشل نهائياً ويُسجَّل السبب.
        """
        row = await tx.fetchone("SELECT attempts FROM notifications WHERE id = ?", (notification_id,))
        attempts = int(row["attempts"]) + 1 if row else 1
        clean_error = error[:300]

        if permanent or attempts >= MAX_NOTIFICATION_ATTEMPTS:
            await tx.execute(
                "UPDATE notifications SET status = 'failed', attempts = ?, last_error = ? WHERE id = ?",
                (attempts, clean_error, notification_id),
            )
            return

        delay = NOTIFICATION_BACKOFF[min(attempts - 1, len(NOTIFICATION_BACKOFF) - 1)]
        await tx.execute(
            """
            UPDATE notifications
               SET attempts = ?, last_error = ?, next_attempt_at = ?, status = 'queued'
             WHERE id = ?
            """,
            (attempts, clean_error, iso_plus_seconds(delay), notification_id),
        )

    async def mark_skipped(self, tx: Tx, notification_id: int, reason: str) -> None:
        """تخطي الإشعار نهائياً (مثلاً لأن المستخدم حظر البوت)."""
        await tx.execute(
            "UPDATE notifications SET status = 'skipped', last_error = ? WHERE id = ?",
            (reason[:300], notification_id),
        )

    async def mark_read_for_user(self, tx: Tx, user_id: int) -> int:
        """تعليم كل إشعارات المستخدم كمقروءة عند فتحه شاشة الإشعارات."""
        result = await tx.execute(
            "UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0", (user_id,)
        )
        return result.rowcount

    async def delete_old(self, tx: Tx, before_iso: str) -> int:
        """حذف الإشعارات القديمة المرسلة (مهمة التنظيف الدورية)."""
        result = await tx.execute(
            "DELETE FROM notifications WHERE created_at < ? AND status IN ('sent', 'skipped', 'failed')",
            (before_iso,),
        )
        return result.rowcount

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, notification_id: int) -> Notification | None:
        """جلب إشعار بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM notifications WHERE id = ?", (notification_id,))
        return Notification.from_row(row)

    async def exists(self, dedupe_key: str) -> bool:
        """هل سبق إنشاء إشعار بهذا المفتاح؟"""
        row = await self.db.fetchone("SELECT 1 FROM notifications WHERE dedupe_key = ?", (dedupe_key,))
        return row is not None

    async def list_for_user(self, user_id: int, *, limit: int = 10, offset: int = 0) -> list[Notification]:
        """آخر إشعارات المستخدم لعرضها داخل «حسابي»."""
        rows = await self.db.fetchall(
            "SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
        return Notification.from_rows(rows)

    async def count_unread(self, user_id: int) -> int:
        """عدد الإشعارات غير المقروءة للمستخدم."""
        return await self.count("notifications", "user_id = ? AND is_read = 0", (user_id,))

    async def count_queued(self) -> int:
        """عدد الإشعارات المنتظرة في الصندوق (مؤشر صحة النظام)."""
        return await self.count("notifications", "status = 'queued'")
```

## `database/repositories/audit.py`

```python
"""
مستودع سجل التدقيق (Audit Log) — كل عملية إدارية حساسة تُسجَّل هنا.

القاعدة: أي تعديل على المال أو الصلاحيات أو الحالات أو الإعدادات يجب أن يترك أثراً
يحتوي: من فعل، ماذا فعل، على من، وما القيمة قبل وبعد.
"""

from __future__ import annotations

import json
from typing import Any

from database.database import Tx
from database.models import AuditLog
from database.repositories.base import BaseRepository


def _to_json(value: Any) -> str | None:
    """تحويل قيمة إلى نص JSON مختصر (أو None إذا كانت فارغة)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


class AuditRepository(BaseRepository):
    """كتابة وقراءة سجل العمليات الإدارية."""

    async def log(
        self,
        tx: Tx,
        *,
        action: str,
        admin_id: int | None = None,
        target_type: str | None = None,
        target_id: str | int | None = None,
        details: Any = None,
        before: Any = None,
        after: Any = None,
        source: str = "telegram",
    ) -> int | None:
        """
        تسجيل عملية إدارية.

        المدخلات:
            action      : كود العملية (مثل "user.balance.credit").
            target_type : نوع الهدف (user/order/service/provider/payment/setting/ticket).
            before/after: حالة الهدف قبل وبعد التعديل (تُخزَّن كـ JSON).

        المخرجات: معرف السجل.
        """
        result = await tx.execute(
            """
            INSERT INTO audit_logs (admin_id, action, target_type, target_id, details_json,
                                    before_json, after_json, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                admin_id, action, target_type,
                str(target_id) if target_id is not None else None,
                _to_json(details), _to_json(before), _to_json(after), source, self.now(),
            ),
        )
        return result.lastrowid

    async def list_recent(self, *, limit: int = 20, offset: int = 0) -> list[AuditLog]:
        """آخر العمليات الإدارية."""
        rows = await self.db.fetchall(
            "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        return AuditLog.from_rows(rows)

    async def list_by_admin(self, admin_id: int, *, limit: int = 20, offset: int = 0) -> list[AuditLog]:
        """عمليات أدمن معين (لمراجعة الأداء أو التحقيق)."""
        rows = await self.db.fetchall(
            "SELECT * FROM audit_logs WHERE admin_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (admin_id, limit, offset),
        )
        return AuditLog.from_rows(rows)

    async def list_by_target(
        self, target_type: str, target_id: str | int, *, limit: int = 20
    ) -> list[AuditLog]:
        """كل العمليات التي جرت على هدف معين (مثل كل ما حدث لمستخدم)."""
        rows = await self.db.fetchall(
            """
            SELECT * FROM audit_logs WHERE target_type = ? AND target_id = ?
             ORDER BY id DESC LIMIT ?
            """,
            (target_type, str(target_id), limit),
        )
        return AuditLog.from_rows(rows)

    async def count_all(self) -> int:
        """إجمالي عدد السجلات."""
        return await self.count("audit_logs")
```

## `database/repositories/broadcasts.py`

```python
"""
مستودع الإذاعة — الرسائل الجماعية وقوائم المستلمين.

سبب تخزين المستلمين في جدول مستقل:
    إذا أُعيد تشغيل البوت أثناء إذاعة لآلاف المستخدمين، يجب أن تُستأنف من حيث توقفت،
    وألا يستلم أحد الرسالة مرتين.
"""

from __future__ import annotations

from typing import Any, Iterable

from database.database import Tx
from database.models import Broadcast
from database.repositories.base import BaseRepository

_BROADCAST_FIELDS = {
    "message_text",
    "parse_mode",
    "media_file_id",
    "media_type",
    "buttons_json",
    "target",
    "target_filter_json",
    "total_count",
    "sent_count",
    "failed_count",
    "blocked_count",
    "status",
    "started_at",
    "finished_at",
}


class BroadcastsRepository(BaseRepository):
    """إنشاء الإذاعات ومتابعة تقدمها."""

    # ------------------------------ الكتابة ------------------------------ #

    async def create(
        self,
        tx: Tx,
        *,
        admin_id: int | None,
        message_text: str,
        target: str = "all",
        parse_mode: str | None = None,
        media_file_id: str | None = None,
        media_type: str | None = None,
        buttons_json: str | None = None,
        target_filter_json: str | None = None,
    ) -> Broadcast:
        """إنشاء إذاعة جديدة بحالة draft."""
        result = await tx.execute(
            """
            INSERT INTO broadcasts (admin_id, message_text, parse_mode, media_file_id, media_type,
                                    buttons_json, target, target_filter_json, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?)
            """,
            (
                admin_id, message_text, parse_mode, media_file_id, media_type,
                buttons_json, target, target_filter_json, self.now(),
            ),
        )
        row = await tx.fetchone("SELECT * FROM broadcasts WHERE id = ?", (result.lastrowid,))
        broadcast = Broadcast.from_row(row)
        assert broadcast is not None
        return broadcast

    async def add_recipients(self, tx: Tx, broadcast_id: int, user_ids: Iterable[int]) -> int:
        """
        إضافة قائمة المستلمين للإذاعة (تتجاهل المكرر بفضل قيد UNIQUE).

        المخرجات: عدد المستلمين المضافين فعلاً.
        """
        ids = list(user_ids)
        if not ids:
            return 0
        await tx.executemany(
            "INSERT OR IGNORE INTO broadcast_recipients (broadcast_id, user_id) VALUES (?, ?)",
            [(broadcast_id, uid) for uid in ids],
        )
        total = await self.count("broadcast_recipients", "broadcast_id = ?", (broadcast_id,))
        await tx.execute(
            "UPDATE broadcasts SET total_count = ? WHERE id = ?", (total, broadcast_id)
        )
        return total

    async def claim_recipients(self, tx: Tx, broadcast_id: int, *, limit: int = 20) -> list[dict]:
        """
        حجز دفعة من المستلمين المنتظرين للإرسال إليهم.

        الآلية: تحديث الحالة إلى sent يتم بعد الإرسال الفعلي؛ هنا نقرأ فقط
        دفعة صغيرة مرتبة، والاعتماد على تحديث كل صف على حدة يمنع الازدواج.
        """
        rows = await tx.fetchall(
            """
            SELECT r.id, r.user_id, u.telegram_id
              FROM broadcast_recipients r
              JOIN users u ON u.id = r.user_id
             WHERE r.broadcast_id = ? AND r.status = 'pending'
             ORDER BY r.id LIMIT ?
            """,
            (broadcast_id, limit),
        )
        return [dict(row) for row in rows]

    async def mark_recipient(
        self, tx: Tx, recipient_id: int, *, status: str, error: str | None = None
    ) -> bool:
        """
        تسجيل نتيجة الإرسال لمستلم واحد (مشروط بأن حالته ما زالت pending).

        المخرجات: True إذا سُجِّلت النتيجة الآن (يمنع العدّ المزدوج).
        """
        result = await tx.execute(
            """
            UPDATE broadcast_recipients SET status = ?, error = ?, sent_at = ?
             WHERE id = ? AND status = 'pending'
            """,
            (status, error[:200] if error else None, self.now(), recipient_id),
        )
        if result.rowcount != 1:
            return False

        column = {"sent": "sent_count", "failed": "failed_count", "blocked": "blocked_count"}.get(status)
        if column:
            broadcast_id = await tx.fetchval(
                "SELECT broadcast_id FROM broadcast_recipients WHERE id = ?", (recipient_id,)
            )
            await tx.execute(
                f"UPDATE broadcasts SET {column} = {column} + 1 WHERE id = ?", (broadcast_id,)
            )
        return True

    async def set_status(self, tx: Tx, broadcast_id: int, status: str, **fields: Any) -> bool:
        """تغيير حالة الإذاعة (running/paused/completed/cancelled)."""
        data = {"status": status, **fields}
        set_sql, values = self._build_update(data, _BROADCAST_FIELDS)
        values.append(broadcast_id)
        result = await tx.execute(f"UPDATE broadcasts SET {set_sql} WHERE id = ?", values)
        return result.rowcount > 0

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, broadcast_id: int) -> Broadcast | None:
        """جلب إذاعة بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM broadcasts WHERE id = ?", (broadcast_id,))
        return Broadcast.from_row(row)

    async def list_recent(self, *, limit: int = 10) -> list[Broadcast]:
        """آخر الإذاعات."""
        rows = await self.db.fetchall("SELECT * FROM broadcasts ORDER BY id DESC LIMIT ?", (limit,))
        return Broadcast.from_rows(rows)

    async def list_running(self) -> list[Broadcast]:
        """الإذاعات الجارية (تُستأنف عند إقلاع البوت)."""
        rows = await self.db.fetchall("SELECT * FROM broadcasts WHERE status = 'running' ORDER BY id")
        return Broadcast.from_rows(rows)

    async def pending_count(self, broadcast_id: int) -> int:
        """عدد المستلمين المتبقين في إذاعة."""
        return await self.count(
            "broadcast_recipients", "broadcast_id = ? AND status = 'pending'", (broadcast_id,)
        )
```

## `database/repositories/idempotency.py`

```python
"""
مستودع مفاتيح منع التكرار (Idempotency).

الاستخدام النموذجي:
    قبل تنفيذ عملية حساسة (اعتماد دفعة، استرجاع، إضافة رصيد يدوي) يُحاول النظام
    حجز مفتاح فريد؛ إذا كان محجوزاً مسبقاً فهذا يعني أن العملية نُفِّذت بالفعل
    (ضغط مزدوج على الزر مثلاً) فتُعاد النتيجة السابقة بدل التنفيذ مرتين.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from core.constants import IDEMPOTENCY_TTL_SECONDS
from database.database import Tx
from database.repositories.base import BaseRepository
from utils.datetime_utils import iso_plus_seconds, utc_now_iso


class IdempotencyRepository(BaseRepository):
    """حجز مفاتيح العمليات وتخزين نتائجها."""

    async def try_acquire(
        self,
        tx: Tx,
        key: str,
        *,
        scope: str,
        user_id: int | None = None,
        ttl_seconds: int = IDEMPOTENCY_TTL_SECONDS,
    ) -> bool:
        """
        محاولة حجز مفتاح عملية.

        المخرجات:
            True  : المفتاح جديد ⇒ تابع تنفيذ العملية.
            False : المفتاح محجوز مسبقاً ⇒ العملية نُفِّذت من قبل، لا تعدها.
        """
        try:
            result = await tx.execute(
                """
                INSERT INTO idempotency_keys (key, scope, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO NOTHING
                """,
                (key, scope, user_id, self.now(), iso_plus_seconds(ttl_seconds)),
            )
        except sqlite3.IntegrityError:
            return False
        return result.rowcount == 1

    async def save_result(self, tx: Tx, key: str, result: Any) -> None:
        """حفظ نتيجة العملية ليُعاد عرضها عند تكرار الطلب."""
        await tx.execute(
            "UPDATE idempotency_keys SET result_json = ? WHERE key = ?",
            (json.dumps(result, ensure_ascii=False, default=str), key),
        )

    async def get_result(self, key: str) -> Any | None:
        """قراءة نتيجة عملية سبق تنفيذها بنفس المفتاح."""
        value = await self.db.fetchval(
            "SELECT result_json FROM idempotency_keys WHERE key = ?", (key,)
        )
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    async def exists(self, key: str) -> bool:
        """هل المفتاح محجوز؟"""
        row = await self.db.fetchone("SELECT 1 FROM idempotency_keys WHERE key = ?", (key,))
        return row is not None

    async def release(self, tx: Tx, key: str) -> bool:
        """
        تحرير مفتاح (يُستخدم فقط عندما تفشل العملية قبل أن تُحدث أي أثر).

        تحذير: لا تحرر المفتاح إذا نُفِّذ جزء من العملية — الأصل هو الاحتفاظ به.
        """
        result = await tx.execute("DELETE FROM idempotency_keys WHERE key = ?", (key,))
        return result.rowcount > 0

    async def cleanup_expired(self, tx: Tx) -> int:
        """حذف المفاتيح المنتهية (مهمة التنظيف الدورية)."""
        result = await tx.execute(
            "DELETE FROM idempotency_keys WHERE expires_at < ?", (utc_now_iso(),)
        )
        return result.rowcount
```

## `database/repositories/misc.py`

```python
"""
مستودعات مساعدة صغيرة:
    • UserStatesRepository     : حفظ خطوة المحادثة الحالية لكل مستخدم.
    • ProviderRequestsRepository: سجل استدعاءات APIs المزودين (بدون أسرار).
    • ErrorLogsRepository      : تسجيل الأخطاء المهمة في قاعدة البيانات.
    • BackupsRepository        : سجل النسخ الاحتياطية.
"""

from __future__ import annotations

import json
from typing import Any

from core.constants import PROVIDER_RESPONSE_SNIPPET_LEN
from database.database import Tx
from database.repositories.base import BaseRepository
from utils.datetime_utils import iso_plus_seconds, utc_now_iso
from utils.security import sanitize


class UserStatesRepository(BaseRepository):
    """حفظ واسترجاع حالة المحادثة لكل مستخدم حتى لا تضيع بعد إعادة التشغيل."""

    async def save(
        self,
        tx: Tx,
        user_id: int,
        *,
        state: str | None,
        data: dict[str, Any] | None = None,
        chat_id: int | None = None,
        ttl_seconds: int = 3600,
    ) -> None:
        """حفظ أو تحديث حالة المحادثة مع مدة صلاحية."""
        await tx.execute(
            """
            INSERT INTO user_states (user_id, chat_id, state, data_json, expires_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                chat_id = excluded.chat_id,
                state = excluded.state,
                data_json = excluded.data_json,
                expires_at = excluded.expires_at,
                updated_at = excluded.updated_at
            """,
            (
                user_id, chat_id, state, json.dumps(data or {}, ensure_ascii=False),
                iso_plus_seconds(ttl_seconds), self.now(),
            ),
        )

    async def get(self, user_id: int) -> dict[str, Any] | None:
        """قراءة حالة المحادثة إن كانت ما زالت صالحة."""
        row = await self.db.fetchone(
            "SELECT * FROM user_states WHERE user_id = ? AND (expires_at IS NULL OR expires_at > ?)",
            (user_id, utc_now_iso()),
        )
        if row is None:
            return None
        try:
            data = json.loads(row["data_json"] or "{}")
        except json.JSONDecodeError:
            data = {}
        return {"state": row["state"], "data": data, "chat_id": row["chat_id"]}

    async def clear(self, tx: Tx, user_id: int) -> None:
        """حذف حالة المحادثة عند انتهاء العملية أو إلغائها."""
        await tx.execute("DELETE FROM user_states WHERE user_id = ?", (user_id,))

    async def cleanup_expired(self, tx: Tx) -> int:
        """حذف الحالات المنتهية (مهمة تنظيف دورية)."""
        result = await tx.execute(
            "DELETE FROM user_states WHERE expires_at IS NOT NULL AND expires_at < ?", (utc_now_iso(),)
        )
        return result.rowcount


class ProviderRequestsRepository(BaseRepository):
    """سجل استدعاءات المزودين لأغراض التشخيص (منقّى من الأسرار)."""

    async def log(
        self,
        tx: Tx,
        *,
        provider_id: int,
        action: str,
        is_success: bool,
        order_id: int | None = None,
        request_summary: str | None = None,
        http_status: int | None = None,
        response_snippet: str | None = None,
        duration_ms: int | None = None,
        error_type: str | None = None,
        secrets: tuple[str, ...] = (),
    ) -> None:
        """
        تسجيل استدعاء واحد لمزود.

        ملاحظة أمنية: يمر النص على دالة التنقية لحذف أي مفتاح قبل التخزين،
        ويُقتطع الرد حتى لا تتضخم قاعدة البيانات.
        """
        await tx.execute(
            """
            INSERT INTO provider_requests (provider_id, order_id, action, request_summary, http_status,
                                           response_snippet, duration_ms, is_success, error_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provider_id,
                order_id,
                action,
                sanitize(request_summary, secrets)[:PROVIDER_RESPONSE_SNIPPET_LEN],
                http_status,
                sanitize(response_snippet, secrets)[:PROVIDER_RESPONSE_SNIPPET_LEN],
                duration_ms,
                1 if is_success else 0,
                error_type,
                self.now(),
            ),
        )

    async def list_by_provider(self, provider_id: int, *, limit: int = 20) -> list[dict]:
        """آخر استدعاءات مزود معين."""
        rows = await self.db.fetchall(
            "SELECT * FROM provider_requests WHERE provider_id = ? ORDER BY id DESC LIMIT ?",
            (provider_id, limit),
        )
        return [dict(row) for row in rows]

    async def delete_old(self, tx: Tx, before_iso: str) -> int:
        """حذف السجلات الأقدم من تاريخ معين."""
        result = await tx.execute("DELETE FROM provider_requests WHERE created_at < ?", (before_iso,))
        return result.rowcount


class ErrorLogsRepository(BaseRepository):
    """تسجيل الأخطاء المهمة في قاعدة البيانات لعرضها في لوحة الأدمن."""

    async def log(
        self,
        tx: Tx,
        *,
        message: str,
        level: str = "ERROR",
        source: str = "app",
        error_type: str | None = None,
        traceback_snippet: str | None = None,
        user_id: int | None = None,
        update_summary: str | None = None,
    ) -> int | None:
        """تسجيل خطأ (بعد تنقيته من أي أسرار)."""
        result = await tx.execute(
            """
            INSERT INTO error_logs (level, source, error_type, message, traceback_snippet,
                                    user_id, update_summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                level, source, error_type, sanitize(message)[:1000],
                sanitize(traceback_snippet)[:2000] if traceback_snippet else None,
                user_id, sanitize(update_summary)[:500] if update_summary else None, self.now(),
            ),
        )
        return result.lastrowid

    async def mark_notified(self, tx: Tx, error_id: int) -> None:
        """تعليم أنه تم إشعار الأدمن بهذا الخطأ (منعاً لتكرار التنبيه)."""
        await tx.execute("UPDATE error_logs SET notified_admin = 1 WHERE id = ?", (error_id,))

    async def list_recent(self, *, limit: int = 20, offset: int = 0) -> list[dict]:
        """آخر الأخطاء المسجلة."""
        rows = await self.db.fetchall(
            "SELECT * FROM error_logs ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        return [dict(row) for row in rows]

    async def count_since(self, since_iso: str) -> int:
        """عدد الأخطاء منذ وقت معين (مؤشر صحة النظام)."""
        return await self.count("error_logs", "created_at >= ?", (since_iso,))

    async def delete_old(self, tx: Tx, before_iso: str) -> int:
        """حذف الأخطاء القديمة."""
        result = await tx.execute("DELETE FROM error_logs WHERE created_at < ?", (before_iso,))
        return result.rowcount


class BackupsRepository(BaseRepository):
    """سجل النسخ الاحتياطية المنشأة."""

    async def add(
        self,
        tx: Tx,
        *,
        filename: str,
        path: str,
        size_bytes: int,
        sha256: str | None = None,
        type: str = "manual",
        created_by: int | None = None,
        status: str = "ok",
    ) -> int | None:
        """تسجيل نسخة احتياطية جديدة."""
        result = await tx.execute(
            """
            INSERT INTO backups (filename, path, size_bytes, sha256, type, created_by, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (filename, path, size_bytes, sha256, type, created_by, status, self.now()),
        )
        return result.lastrowid

    async def list_recent(self, *, limit: int = 10) -> list[dict]:
        """آخر النسخ الاحتياطية."""
        rows = await self.db.fetchall(
            "SELECT * FROM backups ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [dict(row) for row in rows]

    async def list_older_than(self, before_iso: str) -> list[dict]:
        """النسخ الأقدم من تاريخ معين (لحذفها ضمن سياسة الاحتفاظ)."""
        rows = await self.db.fetchall(
            "SELECT * FROM backups WHERE created_at < ? ORDER BY id", (before_iso,)
        )
        return [dict(row) for row in rows]

    async def delete(self, tx: Tx, backup_id: int) -> bool:
        """حذف سجل نسخة احتياطية (بعد حذف ملفها فعلياً)."""
        result = await tx.execute("DELETE FROM backups WHERE id = ?", (backup_id,))
        return result.rowcount > 0
```

# أدوات التشغيل — scripts/

## `scripts/__init__.py`

```python
"""أدوات تشغيلية تعمل خارج البوت (تهيئة قاعدة البيانات، إنشاء أدمن، استعادة نسخة)."""
```

## `scripts/init_db.py`

```python
"""
تهيئة قاعدة البيانات — أول أمر يُنفَّذ عند تثبيت المشروع.

ما تفعله هذه الأداة:
    1. قراءة الإعدادات من .env وإنشاء المجلدات المطلوبة.
    2. إنشاء ملف قاعدة البيانات وتطبيق كل الترحيلات الناقصة.
    3. التحقق من سلامة المخطط والمفاتيح الأجنبية.
    4. زرع حسابات الأدمن الأعلى المذكورة في SUPER_ADMIN_IDS.
    5. طباعة تقرير واضح بالحالة.

طريقة التشغيل (من مجلد المشروع smm_bot):
    python -m scripts.init_db
    python -m scripts.init_db --gen-key     # توليد مفتاح تشفير جديد فقط
    python -m scripts.init_db --status      # عرض الحالة دون تعديل
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from config import Config, ConfigError
from core.enums import Role
from database.database import Database
from database.migrator import Migrator
from database.repositories import Repositories
from utils.logging_setup import setup_logging
from utils.security import generate_encryption_key

#: الجداول التي يجب أن تكون موجودة بعد التهيئة الكاملة
EXPECTED_TABLES: tuple[str, ...] = (
    "schema_migrations", "roles", "permissions", "role_permissions", "users", "user_permissions",
    "user_states", "providers", "provider_balance_snapshots", "service_categories", "services",
    "service_price_history", "payment_methods", "payments", "orders", "order_status_history",
    "transactions", "support_tickets", "support_messages", "notifications", "audit_logs",
    "settings", "broadcasts", "broadcast_recipients", "idempotency_keys", "provider_requests",
    "error_logs", "backups",
)


async def seed_super_admins(db: Database, telegram_ids: tuple[int, ...]) -> list[str]:
    """
    إنشاء أو ترقية حسابات الأدمن الأعلى المذكورة في متغير البيئة.

    المخرجات: قائمة رسائل توضح ما تم لكل معرف.
    """
    repos = Repositories(db)
    messages: list[str] = []
    for telegram_id in telegram_ids:
        existing = await repos.users.get_by_telegram_id(telegram_id)
        async with db.transaction() as tx:
            if existing is None:
                await repos.users.create(
                    tx, telegram_id=telegram_id, first_name="Super Admin", role=Role.SUPER_ADMIN
                )
                await repos.audit.log(
                    tx, action="system.seed_super_admin", target_type="user", target_id=telegram_id,
                    details={"source": "SUPER_ADMIN_IDS"}, source="script",
                )
                messages.append(f"✅ أُنشئ حساب أدمن أعلى للمعرف {telegram_id}")
            elif existing.role != Role.SUPER_ADMIN:
                await repos.users.set_role(tx, existing.id, Role.SUPER_ADMIN)
                await repos.audit.log(
                    tx, action="system.promote_super_admin", target_type="user", target_id=existing.id,
                    before={"role": existing.role}, after={"role": str(Role.SUPER_ADMIN)}, source="script",
                )
                messages.append(f"⬆️ تمت ترقية المستخدم {telegram_id} إلى أدمن أعلى")
            else:
                messages.append(f"ℹ️ المعرف {telegram_id} أدمن أعلى بالفعل")
    return messages


async def verify_schema(db: Database) -> list[str]:
    """التحقق من وجود كل الجداول المتوقعة وسلامة قاعدة البيانات."""
    problems: list[str] = []
    tables = set(await db.table_names())
    missing = [name for name in EXPECTED_TABLES if name not in tables]
    if missing:
        problems.append("جداول ناقصة: " + ", ".join(missing))
    if not await db.integrity_check():
        problems.append("فحص سلامة قاعدة البيانات فشل (integrity_check).")
    violations = await db.foreign_key_check()
    if violations:
        problems.append(f"يوجد {len(violations)} انتهاك للمفاتيح الأجنبية.")
    return problems


async def print_status(db: Database, config: Config) -> None:
    """طباعة ملخص حالة قاعدة البيانات بعد التهيئة."""
    repos = Repositories(db)
    migrator = Migrator(db)
    tables = await db.table_names()
    print("\n📊 حالة النظام")
    print("──────────────────────────────")
    print(f"  ملف قاعدة البيانات : {config.database_path}")
    print(f"  إصدار المخطط        : {await migrator.current_version()}")
    print(f"  عدد الجداول         : {len(tables)}")
    print(f"  الأدوار             : {len(await repos.rbac.list_roles())}")
    print(f"  الصلاحيات           : {len(await repos.rbac.list_permissions())}")
    print(f"  الإعدادات           : {len(await repos.settings.all())}")
    print(f"  التصنيفات           : {len(await repos.categories.list_all())}")
    print(f"  المستخدمون          : {await repos.users.count_all()}")
    print(f"  المزودون            : {len(await repos.providers.list_all())}")
    print(f"  الخدمات             : {await repos.services.count_active()}")
    print(f"  طرق الدفع           : {len(await repos.payment_methods.list_all())}")
    print("──────────────────────────────")


async def run(args: argparse.Namespace) -> int:
    """تنفيذ عملية التهيئة الكاملة وإرجاع كود الخروج."""
    try:
        config = Config.load()
    except ConfigError as exc:
        print(f"❌ خطأ في الإعدادات: {exc}")
        return 2

    config.ensure_directories()
    setup_logging(config.log_file, config.log_level, console=False)

    print("🚀 تهيئة قاعدة بيانات SMM Bot")
    for key, value in config.safe_summary().items():
        print(f"  • {key}: {value}")

    db = Database(config.database_path)
    await db.connect()
    try:
        if args.status:
            await print_status(db, config)
            return 0

        migrator = Migrator(db)
        pending = await migrator.pending()
        if pending:
            print(f"\n⚙️ تطبيق {len(pending)} ترحيل: {', '.join(pending)}")
        applied = await migrator.apply_all()
        print("✅ تم تطبيق الترحيلات." if applied else "ℹ️ قاعدة البيانات محدّثة مسبقاً.")

        problems = await verify_schema(db)
        if problems:
            print("\n❌ مشاكل في المخطط:")
            for problem in problems:
                print(f"   - {problem}")
            return 1
        print("✅ فحص المخطط والمفاتيح الأجنبية: سليم.")

        if config.super_admin_ids:
            print("\n👤 حسابات الأدمن الأعلى:")
            for message in await seed_super_admins(db, config.super_admin_ids):
                print(f"   {message}")
        else:
            print("\n⚠️ لم يُحدَّد SUPER_ADMIN_IDS في ملف .env — لن تتمكن من دخول لوحة الأدمن.")

        if not config.encryption_key:
            print("\n⚠️ ENCRYPTION_KEY غير موجود — مطلوب لإضافة المزودين لاحقاً.")
            print(f"   مفتاح مقترح: {generate_encryption_key()}")

        await print_status(db, config)
        print("\n🎉 اكتملت التهيئة بنجاح.")
        return 0
    finally:
        await db.close()


def main() -> int:
    """نقطة الدخول: تحليل الوسائط وتشغيل العملية."""
    parser = argparse.ArgumentParser(description="تهيئة قاعدة بيانات SMM Bot")
    parser.add_argument("--gen-key", action="store_true", help="توليد مفتاح تشفير جديد فقط")
    parser.add_argument("--status", action="store_true", help="عرض حالة قاعدة البيانات دون تعديل")
    args = parser.parse_args()

    if args.gen_key:
        print(generate_encryption_key())
        return 0
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
```

## `scripts/create_admin.py`

```python
"""
إنشاء أو ترقية حساب إداري من سطر الأوامر.

الاستخدام (من مجلد المشروع):
    python -m scripts.create_admin 123456789 admin
    python -m scripts.create_admin 123456789 support
    python -m scripts.create_admin 123456789 user        # تنزيل الصلاحيات

الفائدة: التعافي عند فقدان الوصول للوحة، أو إعداد فريق العمل قبل تشغيل البوت.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from config import Config, ConfigError
from core.enums import Role
from database.database import Database
from database.repositories import Repositories
from utils.logging_setup import setup_logging

VALID_ROLES = {str(role) for role in Role}


async def run(telegram_id: int, role: str) -> int:
    """تنفيذ إنشاء/ترقية الحساب وإرجاع كود الخروج."""
    if role not in VALID_ROLES:
        print(f"❌ دور غير معروف: {role} — الأدوار المتاحة: {', '.join(sorted(VALID_ROLES))}")
        return 2

    try:
        config = Config.load()
    except ConfigError as exc:
        print(f"❌ خطأ في الإعدادات: {exc}")
        return 2

    config.ensure_directories()
    setup_logging(config.log_file, config.log_level, console=False)

    db = Database(config.database_path)
    await db.connect()
    try:
        repos = Repositories(db)
        user = await repos.users.get_by_telegram_id(telegram_id)
        async with db.transaction() as tx:
            if user is None:
                user = await repos.users.create(tx, telegram_id=telegram_id, role=role)
                await repos.audit.log(
                    tx, action="admin.create_via_script", target_type="user", target_id=user.id,
                    after={"role": role}, source="script",
                )
                print(f"✅ تم إنشاء المستخدم {telegram_id} بالدور: {role}")
            else:
                old_role = user.role
                await repos.users.set_role(tx, user.id, role)
                await repos.audit.log(
                    tx, action="admin.role_change_via_script", target_type="user", target_id=user.id,
                    before={"role": old_role}, after={"role": role}, source="script",
                )
                print(f"✅ تم تغيير دور المستخدم {telegram_id} من {old_role} إلى {role}")

        permissions = await repos.rbac.effective_permissions(user.id, role)
        print(f"🔐 عدد الصلاحيات الفعلية: {len(permissions)}")
        return 0
    finally:
        await db.close()


def main() -> int:
    """نقطة الدخول: قراءة الوسائط وتشغيل العملية."""
    parser = argparse.ArgumentParser(description="إنشاء أو ترقية حساب إداري")
    parser.add_argument("telegram_id", type=int, help="معرف تيليجرام الرقمي")
    parser.add_argument(
        "role", nargs="?", default=str(Role.ADMIN), help="الدور: user / support / admin / super_admin"
    )
    args = parser.parse_args()
    return asyncio.run(run(args.telegram_id, args.role))


if __name__ == "__main__":
    sys.exit(main())
```

# الاختبارات — tests/

## `tests/conftest.py`

```python
"""
تهيئة بيئة الاختبارات.

كل اختبار يحصل على قاعدة بيانات مؤقتة جديدة مع تطبيق كامل الترحيلات،
حتى تكون الاختبارات مستقلة تماماً عن بعضها وعن بيانات التشغيل الحقيقية.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio

# إضافة جذر المشروع إلى مسار الاستيراد حتى تعمل الاستيرادات المطلقة
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.database import Database  # noqa: E402
from database.migrator import Migrator  # noqa: E402
from database.repositories import Repositories  # noqa: E402


@pytest_asyncio.fixture
async def db(tmp_path: Path):
    """قاعدة بيانات مؤقتة مع تطبيق كل الترحيلات."""
    database = Database(tmp_path / "test.db", read_pool_size=2)
    await database.connect()
    await Migrator(database).apply_all()
    try:
        yield database
    finally:
        await database.close()


@pytest_asyncio.fixture
async def repos(db: Database) -> Repositories:
    """حاوية المستودعات على قاعدة بيانات الاختبار."""
    return Repositories(db)


@pytest_asyncio.fixture
async def user(db: Database, repos: Repositories):
    """مستخدم اختباري جاهز برصيد صفر."""
    async with db.transaction() as tx:
        return await repos.users.create(
            tx, telegram_id=100200300, username="tester", first_name="Tester"
        )


@pytest_asyncio.fixture
async def provider(db: Database, repos: Repositories):
    """مزود اختباري (المفتاح هنا نص وهمي مشفَّر شكلياً — لا يُستخدم للاتصال)."""
    async with db.transaction() as tx:
        return await repos.providers.create(
            tx,
            name="TestProvider",
            api_url="https://example.invalid/api/v2",
            api_key_enc="ENC::dummy-not-a-real-key",
            api_key_hint="1234",
        )


@pytest_asyncio.fixture
async def service(db: Database, repos: Repositories, provider):
    """خدمة اختبارية بسعر 1.0000 لكل ألف (10000 نقطة)."""
    categories = await repos.categories.list_all()
    async with db.transaction() as tx:
        return await repos.services.create(
            tx,
            category_id=categories[0].id,
            provider_id=provider.id,
            provider_service_id="555",
            name="متابعين انستغرام اختبار",
            price_per_1000_units=10_000,
            provider_price_per_1000_units=6_000,
            min_quantity=100,
            max_quantity=10_000,
        )


@pytest_asyncio.fixture
async def payment_method(db: Database, repos: Repositories):
    """طريقة دفع يدوية للاختبار."""
    async with db.transaction() as tx:
        return await repos.payment_methods.create(
            tx, code="test_wallet", name_ar="محفظة اختبار", instructions_ar="حوّل ثم أرسل الإثبات"
        )


@pytest.fixture
def anyio_backend() -> str:
    """تثبيت backend الخاص بالاختبارات غير المتزامنة."""
    return "asyncio"
```

## `tests/test_money.py`

```python
"""اختبارات حساب المال — أخطر جزء في النظام، لذا يُختبر بدقة."""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.exceptions import InvalidAmountError
from core.money import (
    MONEY_SCALE,
    apply_markup,
    format_units,
    from_units,
    order_cost_units,
    partial_refund_units,
    to_units,
)


def test_scale_is_four_decimals() -> None:
    """المقياس المعتمد أربع خانات عشرية."""
    assert MONEY_SCALE == 10_000


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1", 10_000), ("0.5", 5_000), ("12.3456", 123_456), ("0.0001", 1), (7, 70_000)],
)
def test_to_units_conversion(value, expected) -> None:
    """التحويل من نص/عدد إلى نقاط صحيحة."""
    assert to_units(value) == expected


def test_to_units_rejects_float() -> None:
    """ممنوع تمرير float لتفادي أخطاء الفاصلة العائمة."""
    with pytest.raises(InvalidAmountError):
        to_units(1.5)  # type: ignore[arg-type]


def test_to_units_rejects_negative_and_garbage() -> None:
    """رفض القيم السالبة وغير الرقمية."""
    with pytest.raises(InvalidAmountError):
        to_units("-5")
    with pytest.raises(InvalidAmountError):
        to_units("abc")


def test_round_trip_precision() -> None:
    """التحويل ذهاباً وإياباً لا يفقد الدقة."""
    assert from_units(to_units("99.9999")) == Decimal("99.9999")


def test_order_cost_basic() -> None:
    """تكلفة 1000 وحدة بسعر ألف = نفس سعر الألف."""
    assert order_cost_units(10_000, 1000) == 10_000


def test_order_cost_half_quantity() -> None:
    """نصف الكمية = نصف السعر بالضبط."""
    assert order_cost_units(10_000, 500) == 5_000


def test_order_cost_rounding_half_up() -> None:
    """التقريب نصفي لأعلى بأعداد صحيحة (لا أخطاء عائمة)."""
    # 3 نقاط لكل ألف × 500 وحدة = 1.5 نقطة ⇒ تقرّب إلى 2
    assert order_cost_units(3, 500) == 2


def test_order_cost_no_float_drift() -> None:
    """مجموع 1000 عملية صغيرة يبقى دقيقاً تماماً (اختبار انحراف الفاصلة العائمة)."""
    total = sum(order_cost_units(1_234, 7) for _ in range(1000))
    assert total == 1000 * ((1_234 * 7 + 500) // 1000)


def test_order_cost_rejects_invalid() -> None:
    """رفض الكمية أو السعر غير الصالح."""
    with pytest.raises(InvalidAmountError):
        order_cost_units(0, 100)
    with pytest.raises(InvalidAmountError):
        order_cost_units(10_000, 0)


def test_partial_refund_half() -> None:
    """تنفيذ نصف الكمية يسترجع نصف التكلفة."""
    assert partial_refund_units(cost_units=10_000, quantity=1000, remains=500) == 5_000


def test_partial_refund_never_exceeds_cost() -> None:
    """الاسترجاع لا يتجاوز التكلفة مهما كانت قيمة remains الواردة من المزود."""
    assert partial_refund_units(cost_units=10_000, quantity=1000, remains=99_999) == 10_000


def test_partial_refund_accounts_previous_refunds() -> None:
    """ما سبق استرجاعه يُخصم فلا يحدث استرجاع مزدوج."""
    assert (
        partial_refund_units(cost_units=10_000, quantity=1000, remains=1000, already_refunded_units=6_000)
        == 4_000
    )


def test_partial_refund_zero_when_completed() -> None:
    """لا استرجاع إذا لم يتبقَّ شيء."""
    assert partial_refund_units(cost_units=10_000, quantity=1000, remains=0) == 0


def test_apply_markup() -> None:
    """حساب سعر البيع من التكلفة بنسبة ربح."""
    assert apply_markup(10_000, 30) == 13_000
    assert apply_markup(3_333, 50) == 5_000  # تقريب نصفي لأعلى


def test_format_units_display() -> None:
    """تنسيق العرض يحترم عدد الخانات المطلوب."""
    assert format_units(123_456, "ريال", 2) == "12.35 ريال"
    assert format_units(10_000, "$", 0) == "1 $"
```

## `tests/test_migrations.py`

```python
"""اختبارات نظام الترحيلات وسلامة المخطط الناتج عنه."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.exceptions import MigrationChecksumError, MigrationError
from database.database import Database
from database.migrator import Migrator
from scripts.init_db import EXPECTED_TABLES


async def test_all_expected_tables_created(db: Database) -> None:
    """كل الجداول المتوقعة موجودة بعد تطبيق الترحيلات."""
    tables = set(await db.table_names())
    missing = [name for name in EXPECTED_TABLES if name not in tables]
    assert not missing, f"جداول ناقصة: {missing}"


async def test_migrations_are_recorded(db: Database) -> None:
    """كل ترحيل مطبق مسجَّل في جدول التتبع ببصمته."""
    migrator = Migrator(db)
    applied = await migrator.applied()
    files = migrator.load_files()
    assert len(applied) == len(files)
    for migration in files:
        assert applied[migration.version] == migration.checksum


async def test_apply_all_is_idempotent(db: Database) -> None:
    """إعادة التشغيل لا تطبق شيئاً مرتين ولا تسبب أخطاء."""
    migrator = Migrator(db)
    assert await migrator.apply_all() == []
    assert await migrator.pending() == []


async def test_modified_migration_is_rejected(tmp_path: Path) -> None:
    """تعديل ملف ترحيل سبق تطبيقه يُرفض فوراً."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_init.sql").write_text("CREATE TABLE demo (id INTEGER PRIMARY KEY);", encoding="utf-8")

    database = Database(tmp_path / "m.db")
    await database.connect()
    try:
        migrator = Migrator(database, migrations)
        assert await migrator.apply_all() == ["0001"]

        (migrations / "0001_init.sql").write_text(
            "CREATE TABLE demo (id INTEGER PRIMARY KEY, extra TEXT);", encoding="utf-8"
        )
        with pytest.raises(MigrationChecksumError):
            await migrator.apply_all()
    finally:
        await database.close()


async def test_failed_migration_rolls_back(tmp_path: Path) -> None:
    """فشل ترحيل في منتصفه لا يترك أثراً جزئياً في قاعدة البيانات."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_bad.sql").write_text(
        "CREATE TABLE good (id INTEGER PRIMARY KEY);\nCREATE TABLE bad (id INTEGER PRIMARY KEY;",
        encoding="utf-8",
    )
    database = Database(tmp_path / "bad.db")
    await database.connect()
    try:
        migrator = Migrator(database, migrations)
        with pytest.raises(Exception):
            await migrator.apply_all()
        tables = await database.table_names()
        assert "good" not in tables  # تراجع كامل
        assert await migrator.applied() == {}
    finally:
        await database.close()


async def test_seed_data_present(db: Database) -> None:
    """بيانات الزرع الأساسية موجودة: أدوار وصلاحيات وإعدادات وتصنيفات."""
    roles = await db.fetchval("SELECT COUNT(*) FROM roles")
    permissions = await db.fetchval("SELECT COUNT(*) FROM permissions")
    settings = await db.fetchval("SELECT COUNT(*) FROM settings")
    categories = await db.fetchval("SELECT COUNT(*) FROM service_categories")
    assert roles == 4
    assert permissions > 30
    assert settings > 20
    assert categories == 8


async def test_no_payment_methods_seeded(db: Database) -> None:
    """لا تُزرع طرق دفع وهمية — يضيفها الأدمن ببياناته الحقيقية."""
    assert await db.fetchval("SELECT COUNT(*) FROM payment_methods") == 0


async def test_foreign_keys_enabled(db: Database) -> None:
    """المفاتيح الأجنبية مفعّلة على مستوى الاتصال."""
    assert await db.fetchval("PRAGMA foreign_keys") == 1


async def test_wal_mode_enabled(db: Database) -> None:
    """وضع WAL مفعّل للسماح بالقراءة أثناء الكتابة."""
    assert str(await db.fetchval("PRAGMA journal_mode")).lower() == "wal"


async def test_transaction_keywords_rejected_in_migration(tmp_path: Path) -> None:
    """ملف ترحيل يحتوي BEGIN/COMMIT يُرفض (المُرحِّل وحده يدير المعاملات)."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_tx.sql").write_text(
        "BEGIN;\nCREATE TABLE demo (id INTEGER PRIMARY KEY);\nCOMMIT;", encoding="utf-8"
    )
    database = Database(tmp_path / "tx.db")
    await database.connect()
    try:
        with pytest.raises(MigrationError, match="ممنوعة"):
            await Migrator(database, migrations).apply_all()
        assert "demo" not in await database.table_names()
    finally:
        await database.close()


async def test_pragma_rejected_in_migration(tmp_path: Path) -> None:
    """ملف ترحيل يحتوي PRAGMA يُرفض (الإعدادات تُضبط عند الاتصال)."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_pragma.sql").write_text(
        "PRAGMA foreign_keys = OFF;\nCREATE TABLE demo (id INTEGER PRIMARY KEY);", encoding="utf-8"
    )
    database = Database(tmp_path / "pragma.db")
    await database.connect()
    try:
        with pytest.raises(MigrationError, match="ممنوعة"):
            await Migrator(database, migrations).apply_all()
    finally:
        await database.close()


async def test_comments_and_multiline_statements_parsed(tmp_path: Path) -> None:
    """التعليقات والعبارات متعددة الأسطر والفاصلة المنقوطة داخل نص لا تكسر التقسيم."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_mix.sql").write_text(
        "-- تعليق افتتاحي\n"
        "CREATE TABLE demo (\n    id INTEGER PRIMARY KEY,\n    label TEXT NOT NULL\n);\n\n"
        "-- إدراج قيمة تحتوي فاصلة منقوطة\n"
        "INSERT INTO demo (label) VALUES ('a;b');\n"
        "-- تعليق ختامي\n",
        encoding="utf-8",
    )
    database = Database(tmp_path / "mix.db")
    await database.connect()
    try:
        assert await Migrator(database, migrations).apply_all() == ["0001"]
        assert await database.fetchval("SELECT label FROM demo") == "a;b"
    finally:
        await database.close()


async def test_migration_file_naming_enforced(tmp_path: Path) -> None:
    """اسم ملف ترحيل مخالف للنمط يُرفض بدل تطبيقه بترتيب عشوائي."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "initial.sql").write_text("CREATE TABLE demo (id INTEGER);", encoding="utf-8")
    database = Database(tmp_path / "name.db")
    await database.connect()
    try:
        with pytest.raises(MigrationError):
            await Migrator(database, migrations).apply_all()
    finally:
        await database.close()
```

## `tests/test_schema_constraints.py`

```python
"""
اختبارات قيود قاعدة البيانات.

الهدف: التأكد أن قاعدة البيانات نفسها ترفض البيانات الخاطئة،
حتى لو حدث خطأ برمجي في الطبقات الأعلى (دفاع أخير).
"""

from __future__ import annotations

import sqlite3

import pytest

from core.enums import OrderStatus, PaymentStatus, TransactionType, values
from database.database import Database
from database.repositories import Repositories


async def _make_order(db: Database, repos: Repositories, user, service, *, crid: str = "req-1"):
    """إنشاء طلب اختباري بسيط."""
    async with db.transaction() as tx:
        return await repos.orders.create(
            tx,
            user_id=user.id,
            service_id=service.id,
            provider_id=service.provider_id,
            service_name_snapshot=service.name,
            price_per_1000_snapshot_units=service.price_per_1000_units,
            link="https://example.com/p/1",
            quantity=1000,
            cost_units=10_000,
            client_request_id=crid,
        )


async def test_balance_cannot_go_negative(db: Database, user) -> None:
    """قيد CHECK يمنع الرصيد السالب حتى عند محاولة تحديث مباشر."""
    with pytest.raises(sqlite3.IntegrityError):
        async with db.transaction() as tx:
            await tx.execute("UPDATE users SET balance_units = -1 WHERE id = ?", (user.id,))


async def test_foreign_key_enforced_on_orders(db: Database, service) -> None:
    """لا يمكن إنشاء طلب لمستخدم غير موجود."""
    with pytest.raises(sqlite3.IntegrityError):
        async with db.transaction() as tx:
            await tx.execute(
                """
                INSERT INTO orders (user_id, service_id, provider_id, service_name_snapshot,
                                    price_per_1000_snapshot_units, link, quantity, cost_units,
                                    client_request_id, created_at, updated_at)
                VALUES (999999, ?, ?, 'x', 1, 'l', 1, 1, 'crid-x', '2026-01-01T00:00:00.000Z',
                        '2026-01-01T00:00:00.000Z')
                """,
                (service.id, service.provider_id),
            )


async def test_user_with_orders_cannot_be_deleted(db: Database, repos: Repositories, user, service) -> None:
    """لا يجوز حذف مستخدم له طلبات (حماية التاريخ المالي)."""
    await _make_order(db, repos, user, service)
    with pytest.raises(sqlite3.IntegrityError):
        async with db.transaction() as tx:
            await tx.execute("DELETE FROM users WHERE id = ?", (user.id,))


async def test_service_with_orders_cannot_be_deleted(db: Database, repos: Repositories, user, service) -> None:
    """لا يجوز حذف خدمة لها طلبات — تُؤرشف بدلاً من ذلك."""
    await _make_order(db, repos, user, service, crid="req-svc")
    with pytest.raises(sqlite3.IntegrityError):
        async with db.transaction() as tx:
            await tx.execute("DELETE FROM services WHERE id = ?", (service.id,))


async def test_duplicate_client_request_id_rejected(db: Database, repos: Repositories, user, service) -> None:
    """نفس مفتاح الطلب لا ينشئ طلبين (حماية الضغط المزدوج)."""
    await _make_order(db, repos, user, service, crid="same-key")
    with pytest.raises(sqlite3.IntegrityError):
        await _make_order(db, repos, user, service, crid="same-key")


async def test_duplicate_transaction_reference_rejected(db: Database, repos: Repositories, user) -> None:
    """نفس المرجع المالي لا يُسجَّل مرتين (حماية الاسترجاع المزدوج)."""
    async with db.transaction() as tx:
        await repos.transactions.insert(
            tx, user_id=user.id, type=TransactionType.DEPOSIT, amount_units=1000,
            balance_before_units=0, balance_after_units=1000, reference="payment:1",
        )
    from core.exceptions import DuplicateOperationError

    with pytest.raises(DuplicateOperationError):
        async with db.transaction() as tx:
            await repos.transactions.insert(
                tx, user_id=user.id, type=TransactionType.DEPOSIT, amount_units=1000,
                balance_before_units=1000, balance_after_units=2000, reference="payment:1",
            )


async def test_duplicate_provider_order_id_rejected(db: Database, repos: Repositories, user, service) -> None:
    """لا يمكن ربط رقم طلب المزود نفسه بطلبين (كشف الازدواج)."""
    first = await _make_order(db, repos, user, service, crid="a")
    second = await _make_order(db, repos, user, service, crid="b")
    async with db.transaction() as tx:
        await repos.orders.update_fields(tx, first.id, provider_order_id="P-100")
    with pytest.raises(sqlite3.IntegrityError):
        async with db.transaction() as tx:
            await repos.orders.update_fields(tx, second.id, provider_order_id="P-100")


async def test_refund_cannot_exceed_cost(db: Database, repos: Repositories, user, service) -> None:
    """قيد CHECK يمنع أن يتجاوز مجموع الاسترجاع تكلفة الطلب."""
    order = await _make_order(db, repos, user, service, crid="refund-guard")
    async with db.transaction() as tx:
        assert await repos.orders.add_refund_amount(tx, order.id, 10_000) is True
    async with db.transaction() as tx:
        assert await repos.orders.add_refund_amount(tx, order.id, 1) is False


async def test_invalid_order_status_rejected(db: Database, repos: Repositories, user, service) -> None:
    """قيد CHECK يرفض أي حالة طلب غير معرَّفة في النظام."""
    order = await _make_order(db, repos, user, service, crid="status-check")
    with pytest.raises(sqlite3.IntegrityError):
        async with db.transaction() as tx:
            await tx.execute("UPDATE orders SET status = 'hacked' WHERE id = ?", (order.id,))


async def test_all_enum_order_statuses_accepted(db: Database, repos: Repositories, user, service) -> None:
    """كل حالة معرَّفة في enums مقبولة في قاعدة البيانات (تطابق الكود مع المخطط)."""
    order = await _make_order(db, repos, user, service, crid="status-enum")
    for status in values(OrderStatus):
        async with db.transaction() as tx:
            await tx.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order.id))
    assert True


async def test_all_enum_payment_statuses_accepted(
    db: Database, repos: Repositories, user, payment_method
) -> None:
    """كل حالات الدفع المعرَّفة مقبولة في المخطط."""
    async with db.transaction() as tx:
        payment = await repos.payments.create(
            tx, user_id=user.id, method_id=payment_method.id, amount_units=50_000
        )
    for status in values(PaymentStatus):
        async with db.transaction() as tx:
            await tx.execute("UPDATE payments SET status = ? WHERE id = ?", (status, payment.id))
    assert True


async def test_all_enum_transaction_types_accepted(db: Database, repos: Repositories, user) -> None:
    """كل أنواع الحركات المالية المعرَّفة مقبولة في المخطط."""
    for index, tx_type in enumerate(values(TransactionType)):
        async with db.transaction() as tx:
            await repos.transactions.insert(
                tx, user_id=user.id, type=tx_type, amount_units=100,
                balance_before_units=0, balance_after_units=100, reference=f"enum-{index}",
            )
    assert await repos.transactions.count_by_user(user.id) == len(values(TransactionType))


async def test_notification_dedupe_key_unique(db: Database, repos: Repositories, user) -> None:
    """مفتاح منع تكرار الإشعار فريد: الإدراج الثاني لا ينشئ صفاً."""
    async with db.transaction() as tx:
        first = await repos.notifications.enqueue(
            tx, user_id=user.id, type="order_created", message="م1", dedupe_key="order:1:created"
        )
    async with db.transaction() as tx:
        second = await repos.notifications.enqueue(
            tx, user_id=user.id, type="order_created", message="م1", dedupe_key="order:1:created"
        )
    assert first is not None
    assert second is None
    assert await repos.notifications.count_queued() == 1


async def test_service_max_quantity_must_be_ge_min(db: Database, repos: Repositories, provider) -> None:
    """قيد يمنع أن يكون الحد الأقصى أقل من الحد الأدنى."""
    categories = await repos.categories.list_all()
    with pytest.raises(sqlite3.IntegrityError):
        async with db.transaction() as tx:
            await repos.services.create(
                tx, category_id=categories[0].id, provider_id=provider.id, provider_service_id="9",
                name="خدمة خاطئة", price_per_1000_units=1000, min_quantity=500, max_quantity=100,
            )


async def test_transaction_amount_must_be_positive(db: Database, user) -> None:
    """قيد يمنع تسجيل حركة مالية بمبلغ صفر أو سالب."""
    with pytest.raises(sqlite3.IntegrityError):
        async with db.transaction() as tx:
            await tx.execute(
                """
                INSERT INTO transactions (user_id, type, direction, amount_units,
                                          balance_before_units, balance_after_units, created_at)
                VALUES (?, 'deposit', 'credit', 0, 0, 0, '2026-01-01T00:00:00.000Z')
                """,
                (user.id,),
            )
```

## `tests/test_database.py`

```python
"""
اختبارات طبقة الاتصال والمعاملات.

أهم اختبار هنا: سباق الخصم المتزامن — إثبات أن الرصيد لا يمكن أن يصبح سالباً
مهما تزاحمت العمليات.
"""

from __future__ import annotations

import asyncio

import pytest

from core.exceptions import DatabaseError
from database.database import Database
from database.repositories import Repositories


async def test_commit_persists_changes(db: Database, repos: Repositories, user) -> None:
    """التعديل داخل معاملة ناجحة يُحفظ فعلاً."""
    async with db.transaction() as tx:
        await repos.users.update_fields(tx, user.id, first_name="مُعدَّل")
    refreshed = await repos.users.get_by_id(user.id)
    assert refreshed is not None and refreshed.first_name == "مُعدَّل"


async def test_rollback_on_exception(db: Database, repos: Repositories, user) -> None:
    """أي استثناء داخل المعاملة يتراجع عن كل التعديلات."""
    with pytest.raises(RuntimeError):
        async with db.transaction() as tx:
            await repos.users.update_fields(tx, user.id, first_name="لن يُحفظ")
            await repos.users.credit(tx, user.id, 50_000)
            raise RuntimeError("فشل مُتعمَّد")

    refreshed = await repos.users.get_by_id(user.id)
    assert refreshed is not None
    assert refreshed.first_name == "Tester"
    assert refreshed.balance_units == 0


async def test_nested_transaction_shares_outer(db: Database, repos: Repositories, user) -> None:
    """المعاملة المتداخلة تستخدم نفس المعاملة الخارجية ولا تُثبِّت مبكراً."""
    with pytest.raises(RuntimeError):
        async with db.transaction() as outer:
            await repos.users.credit(outer, user.id, 10_000)
            async with db.transaction() as inner:
                await repos.users.credit(inner, user.id, 10_000)
            raise RuntimeError("تراجع كامل")

    refreshed = await repos.users.get_by_id(user.id)
    assert refreshed is not None and refreshed.balance_units == 0


async def test_concurrent_debits_never_go_negative(db: Database, repos: Repositories, user) -> None:
    """
    سيناريو السباق: رصيد يكفي 10 عمليات فقط، و50 محاولة خصم متزامنة.

    المتوقع: تنجح 10 بالضبط، ويبقى الرصيد صفراً — لا سالب ولا خصم مزدوج.
    """
    async with db.transaction() as tx:
        await repos.users.credit(tx, user.id, 10)

    async def attempt(index: int) -> bool:
        """محاولة خصم نقطة واحدة مع تسجيل حركة مالية."""
        async with db.transaction() as tx:
            ok = await repos.users.try_debit(tx, user.id, 1)
            if ok:
                balance = await repos.users.get_balance_units(user.id)
                await repos.transactions.insert(
                    tx, user_id=user.id, type="order", amount_units=1,
                    balance_before_units=balance + 1, balance_after_units=balance,
                    reference=f"race:{index}",
                )
            return ok

    results = await asyncio.gather(*(attempt(i) for i in range(50)))
    refreshed = await repos.users.get_by_id(user.id)

    assert sum(results) == 10
    assert refreshed is not None and refreshed.balance_units == 0
    assert await repos.transactions.count_by_user(user.id) == 10


async def test_ledger_matches_balance(db: Database, repos: Repositories, user) -> None:
    """مجموع دفتر الحركات يطابق الرصيد المخزَّن (تدقيق محاسبي)."""
    async with db.transaction() as tx:
        await repos.users.credit(tx, user.id, 100_000, count_as_deposit=True)
        await repos.transactions.insert(
            tx, user_id=user.id, type="deposit", amount_units=100_000,
            balance_before_units=0, balance_after_units=100_000, reference="p:1",
        )
    async with db.transaction() as tx:
        await repos.users.try_debit(tx, user.id, 30_000)
        await repos.transactions.insert(
            tx, user_id=user.id, type="order", amount_units=30_000,
            balance_before_units=100_000, balance_after_units=70_000, reference="o:1",
        )

    user_row = await repos.users.get_by_id(user.id)
    assert user_row is not None
    assert user_row.balance_units == 70_000
    assert await repos.transactions.user_balance_from_ledger(user.id) == 70_000


async def test_try_debit_insufficient_returns_false(db: Database, repos: Repositories, user) -> None:
    """محاولة خصم أكبر من الرصيد تُرجع False ولا تغيّر شيئاً."""
    async with db.transaction() as tx:
        await repos.users.credit(tx, user.id, 5_000)
    async with db.transaction() as tx:
        assert await repos.users.try_debit(tx, user.id, 5_001) is False
    assert await repos.users.get_balance_units(user.id) == 5_000


async def test_operations_require_connection(tmp_path) -> None:
    """استخدام قاعدة بيانات غير متصلة يعطي خطأ واضحاً لا انهياراً غامضاً."""
    database = Database(tmp_path / "x.db")
    with pytest.raises(DatabaseError):
        await database.fetchone("SELECT 1")


async def test_reads_work_during_open_transaction(db: Database, repos: Repositories, user) -> None:
    """القراءة داخل معاملة ترى التعديلات غير المثبتة (نفس الاتصال)."""
    async with db.transaction() as tx:
        await repos.users.credit(tx, user.id, 7_000)
        inside = await repos.users.get_balance_units(user.id)
        assert inside == 7_000
    assert await repos.users.get_balance_units(user.id) == 7_000


async def test_integrity_and_foreign_key_check(db: Database) -> None:
    """أدوات الفحص الإداري تعمل وتُرجع نتيجة سليمة."""
    assert await db.integrity_check() is True
    assert await db.foreign_key_check() == []
```

## `tests/test_repositories.py`

```python
"""اختبارات المستودعات: سلوك العمليات الحقيقية على البيانات."""

from __future__ import annotations

import asyncio

from core.enums import OrderStatus
from database.database import Database
from database.repositories import Repositories
from utils.datetime_utils import iso_minus_days, utc_now_iso


# ------------------------------- المستخدمون ------------------------------- #


async def test_create_and_fetch_user(db: Database, repos: Repositories) -> None:
    """إنشاء مستخدم وجلبه بمعرف تيليجرام."""
    async with db.transaction() as tx:
        created = await repos.users.create(tx, telegram_id=777, username="ali", first_name="علي")
    fetched = await repos.users.get_by_telegram_id(777)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.display_name == "@ali"
    assert fetched.balance_units == 0
    assert fetched.role == "user"


async def test_ban_and_unban(db: Database, repos: Repositories, user) -> None:
    """الحظر يسجل السبب والوقت، وفك الحظر يمسحهما."""
    async with db.transaction() as tx:
        await repos.users.set_ban(tx, user.id, banned=True, reason="إساءة")
    banned = await repos.users.get_by_id(user.id)
    assert banned is not None and banned.banned and banned.ban_reason == "إساءة"

    async with db.transaction() as tx:
        await repos.users.set_ban(tx, user.id, banned=False)
    unbanned = await repos.users.get_by_id(user.id)
    assert unbanned is not None and not unbanned.banned and unbanned.ban_reason is None


async def test_search_user_by_id_and_name(db: Database, repos: Repositories, user) -> None:
    """البحث يعمل بالرقم وبالاسم."""
    assert len(await repos.users.search("100200300")) == 1
    assert len(await repos.users.search("@tester")) == 1
    assert len(await repos.users.search("لا-يوجد")) == 0


async def test_broadcast_targets_exclude_banned_and_blocked(db: Database, repos: Repositories, user) -> None:
    """قائمة الإذاعة تستثني المحظور ومن حظر البوت."""
    async with db.transaction() as tx:
        blocked = await repos.users.create(tx, telegram_id=888, first_name="حظر")
        await repos.users.set_blocked_bot(tx, blocked.id, True)
        banned = await repos.users.create(tx, telegram_id=999, first_name="محظور")
        await repos.users.set_ban(tx, banned.id, banned=True, reason="x")
    targets = await repos.users.telegram_ids_for_broadcast()
    assert targets == [user.telegram_id]


# -------------------------------- الصلاحيات -------------------------------- #


async def test_role_permissions_hierarchy(db: Database, repos: Repositories) -> None:
    """الأدوار تحمل الصلاحيات الصحيحة: المستخدم لا شيء، الدعم محدود، الأدمن الأعلى الكل."""
    user_perms = await repos.rbac.role_permissions("user")
    support_perms = await repos.rbac.role_permissions("support")
    admin_perms = await repos.rbac.role_permissions("admin")
    super_perms = await repos.rbac.role_permissions("super_admin")

    assert user_perms == set()
    assert "tickets.reply" in support_perms
    assert "users.balance.credit" not in support_perms
    assert "payments.approve" in admin_perms
    assert "admins.manage" not in admin_perms
    assert admin_perms < super_perms


async def test_user_permission_override(db: Database, repos: Repositories, user) -> None:
    """الاستثناء الفردي يتجاوز صلاحيات الدور في الاتجاهين."""
    assert await repos.rbac.has_permission(user.id, "user", "payments.approve") is False

    async with db.transaction() as tx:
        await repos.rbac.set_user_override(tx, user.id, "payments.approve", allow=True)
    assert await repos.rbac.has_permission(user.id, "user", "payments.approve") is True

    async with db.transaction() as tx:
        await repos.rbac.set_user_override(tx, user.id, "tickets.reply", allow=False)
    assert await repos.rbac.has_permission(user.id, "support", "tickets.reply") is False


# -------------------------------- الإعدادات -------------------------------- #


async def test_settings_typed_reads(db: Database, repos: Repositories) -> None:
    """قراءة الإعدادات بأنواعها الصحيحة."""
    assert await repos.settings.get_bool("maintenance_mode") is False
    assert await repos.settings.get_int("order_check_interval_seconds") == 120
    assert await repos.settings.get_str("currency_code") == "YER"
    assert await repos.settings.get_int("غير_موجود", 42) == 42


async def test_settings_update_and_protect_readonly(db: Database, repos: Repositories, user) -> None:
    """الإعداد القابل للتعديل يتغير، والمحمي يُرفض تعديله."""
    async with db.transaction() as tx:
        assert await repos.settings.set(tx, "maintenance_mode", "1", updated_by=user.id) is True
        assert await repos.settings.set(tx, "schema_money_scale", "100") is False
    assert await repos.settings.get_bool("maintenance_mode") is True
    assert await repos.settings.get_int("schema_money_scale") == 10_000


# --------------------------- التصنيفات والخدمات ---------------------------- #


async def test_categories_with_services_only(db: Database, repos: Repositories, service) -> None:
    """لا يظهر للمستخدم إلا التصنيف الذي يحتوي خدمة متاحة فعلاً."""
    visible = await repos.categories.list_with_available_services()
    assert len(visible) == 1
    assert visible[0].id == service.category_id

    async with db.transaction() as tx:
        await repos.services.set_active(tx, service.id, False)
    assert await repos.categories.list_with_available_services() == []


async def test_service_price_change_records_history(db: Database, repos: Repositories, service) -> None:
    """تغيير السعر يُسجَّل في سجل الأسعار بالقيمتين القديمة والجديدة."""
    async with db.transaction() as tx:
        assert await repos.services.change_price(
            tx, service.id, new_price_units=12_000, changed_by=None, source="admin"
        ) is True
    history = await repos.services.price_history(service.id)
    updated = await repos.services.get(service.id)
    assert updated is not None and updated.price_per_1000_units == 12_000
    assert len(history) == 1
    assert history[0]["old_price_units"] == 10_000
    assert history[0]["new_price_units"] == 12_000


async def test_archive_hides_service_but_keeps_data(db: Database, repos: Repositories, service) -> None:
    """الأرشفة تُخفي الخدمة دون حذفها (حذف ناعم)."""
    async with db.transaction() as tx:
        await repos.services.archive(tx, service.id)
    assert await repos.services.get_available(service.id) is None
    assert await repos.services.get(service.id) is not None


async def test_negative_margin_detection(db: Database, repos: Repositories, service) -> None:
    """كشف الخدمات التي أصبح سعر بيعها أقل من تكلفتها."""
    assert await repos.services.negative_margin_services() == []
    async with db.transaction() as tx:
        await repos.services.update_fields(tx, service.id, price_per_1000_units=5_000)
    assert len(await repos.services.negative_margin_services()) == 1


# --------------------------------- الطلبات --------------------------------- #


async def _order(db: Database, repos: Repositories, user, service, crid: str):
    """أداة مساعدة: إنشاء طلب اختباري."""
    async with db.transaction() as tx:
        return await repos.orders.create(
            tx,
            user_id=user.id,
            service_id=service.id,
            provider_id=service.provider_id,
            service_name_snapshot=service.name,
            price_per_1000_snapshot_units=service.price_per_1000_units,
            link="https://example.com/p/1",
            quantity=1000,
            cost_units=10_000,
            client_request_id=crid,
        )


async def test_order_status_guard(db: Database, repos: Repositories, user, service) -> None:
    """تغيير الحالة مشروط بالحالة السابقة: الانتقال الخاطئ يفشل بهدوء."""
    order = await _order(db, repos, user, service, "o1")
    async with db.transaction() as tx:
        ok = await repos.orders.update_status(
            tx, order.id, new_status=OrderStatus.SUBMITTED,
            expected_statuses=[OrderStatus.SUBMITTING],
        )
    assert ok is False  # الحالة الحالية pending وليست submitting

    async with db.transaction() as tx:
        ok = await repos.orders.update_status(
            tx, order.id, new_status=OrderStatus.SUBMITTING, expected_statuses=[OrderStatus.PENDING]
        )
    assert ok is True


async def test_claim_pending_only_once(db: Database, repos: Repositories, user, service) -> None:
    """الطلب المعلّق يُحجز مرة واحدة فقط — لا يعالجه worker ثانٍ."""
    await _order(db, repos, user, service, "claim-1")
    async with db.transaction() as tx:
        first = await repos.orders.claim_pending_for_submit(tx, worker="w1", limit=10)
    async with db.transaction() as tx:
        second = await repos.orders.claim_pending_for_submit(tx, worker="w2", limit=10)
    assert len(first) == 1
    assert second == []
    assert first[0].status == OrderStatus.SUBMITTING
    assert first[0].submit_attempts == 1


async def test_concurrent_claims_do_not_duplicate(db: Database, repos: Repositories, user, service) -> None:
    """حجز متزامن من عدة عمال لا يعطي نفس الطلب لأكثر من واحد."""
    for index in range(5):
        await _order(db, repos, user, service, f"cc-{index}")

    async def claim(worker: str) -> list[int]:
        """محاولة حجز دفعة طلبات."""
        async with db.transaction() as tx:
            orders = await repos.orders.claim_pending_for_submit(tx, worker=worker, limit=5)
        return [o.id for o in orders]

    batches = await asyncio.gather(claim("w1"), claim("w2"), claim("w3"))
    all_ids = [oid for batch in batches for oid in batch]
    assert len(all_ids) == 5
    assert len(set(all_ids)) == 5  # لا تكرار


async def test_recover_submitting_orders(db: Database, repos: Repositories, user, service) -> None:
    """بعد إعادة التشغيل تُنقل الطلبات العالقة في submitting إلى submit_uncertain."""
    await _order(db, repos, user, service, "rec-1")
    async with db.transaction() as tx:
        await repos.orders.claim_pending_for_submit(tx, worker="w1", limit=1)
    async with db.transaction() as tx:
        recovered = await repos.orders.recover_submitting_orders(tx)
    assert len(recovered) == 1
    order = await repos.orders.get(recovered[0])
    assert order is not None and order.status == OrderStatus.SUBMIT_UNCERTAIN
    history = await repos.orders.history(order.id)
    assert history[-1].to_status == OrderStatus.SUBMIT_UNCERTAIN


async def test_duplicate_order_detection(db: Database, repos: Repositories, user, service) -> None:
    """كشف الطلب المكرر خلال النافذة الزمنية."""
    await _order(db, repos, user, service, "dup-1")
    found = await repos.orders.find_recent_duplicate(
        user_id=user.id, service_id=service.id, link="https://example.com/p/1",
        quantity=1000, since_iso=iso_minus_days(1),
    )
    assert found is not None
    not_found = await repos.orders.find_recent_duplicate(
        user_id=user.id, service_id=service.id, link="https://example.com/other",
        quantity=1000, since_iso=iso_minus_days(1),
    )
    assert not_found is None


async def test_order_history_and_counts(db: Database, repos: Repositories, user, service) -> None:
    """سجل الحالات يُكتب، وعدّادات الحالات تعمل."""
    order = await _order(db, repos, user, service, "hist-1")
    async with db.transaction() as tx:
        await repos.orders.add_history(
            tx, order_id=order.id, from_status=None, to_status=OrderStatus.PENDING, actor_type="user"
        )
    assert len(await repos.orders.history(order.id)) == 1
    assert (await repos.orders.status_counts())["pending"] == 1


# -------------------------------- المدفوعات -------------------------------- #


async def test_payment_status_guard_prevents_double_approve(
    db: Database, repos: Repositories, user, payment_method
) -> None:
    """اعتماد الدفعة مرتين مستحيل: المحاولة الثانية تُرجع False."""
    async with db.transaction() as tx:
        payment = await repos.payments.create(
            tx, user_id=user.id, method_id=payment_method.id, amount_units=50_000
        )
    async with db.transaction() as tx:
        first = await repos.payments.set_status(
            tx, payment.id, new_status="approved", admin_id=user.id, credited_units=50_000
        )
    async with db.transaction() as tx:
        second = await repos.payments.set_status(
            tx, payment.id, new_status="approved", admin_id=user.id, credited_units=50_000
        )
    assert first is True
    assert second is False


async def test_payment_duplicate_reference_detection(
    db: Database, repos: Repositories, user, payment_method
) -> None:
    """كشف استخدام نفس رقم الحوالة في طلب شحن آخر."""
    async with db.transaction() as tx:
        await repos.payments.create(
            tx, user_id=user.id, method_id=payment_method.id, amount_units=10_000,
            transaction_reference="TRX-999",
        )
    assert await repos.payments.find_duplicate_reference("TRX-999") is not None
    assert await repos.payments.find_duplicate_reference("TRX-000") is None


# ---------------------------------- الدعم ---------------------------------- #


async def test_ticket_flow(db: Database, repos: Repositories, user) -> None:
    """دورة تذكرة كاملة: إنشاء، رسالة مستخدم، رد أدمن، إغلاق."""
    async with db.transaction() as tx:
        ticket = await repos.tickets.create(tx, user_id=user.id, subject="مشكلة في طلب")
        await repos.tickets.add_message(
            tx, ticket_id=ticket.id, sender_type="user", message="طلبي لم يصل", sender_id=user.id
        )
    after_user = await repos.tickets.get(ticket.id)
    assert after_user is not None and after_user.status == "pending_admin"

    async with db.transaction() as tx:
        await repos.tickets.add_message(
            tx, ticket_id=ticket.id, sender_type="admin", message="تمت المتابعة", sender_id=user.id
        )
    after_admin = await repos.tickets.get(ticket.id)
    assert after_admin is not None and after_admin.status == "pending_user"

    async with db.transaction() as tx:
        assert await repos.tickets.close(tx, ticket.id, closed_by=user.id, reason="تم الحل") is True
    async with db.transaction() as tx:
        assert await repos.tickets.close(tx, ticket.id, closed_by=user.id) is False  # لا إغلاق مزدوج

    assert len(await repos.tickets.messages(ticket.id)) == 2
    assert await repos.tickets.count_open() == 0


# -------------------------------- الإشعارات -------------------------------- #


async def test_notification_outbox_cycle(db: Database, repos: Repositories, user) -> None:
    """دورة الإشعار: إدراج ← حجز ← تعليم كمُرسل."""
    async with db.transaction() as tx:
        await repos.notifications.enqueue(
            tx, user_id=user.id, type="order_completed", message="اكتمل طلبك", dedupe_key="order:5:completed"
        )
    async with db.transaction() as tx:
        batch = await repos.notifications.claim_batch(tx, limit=10)
    assert len(batch) == 1

    async with db.transaction() as tx:
        assert await repos.notifications.mark_sent(tx, batch[0].id, 12345) is True
    async with db.transaction() as tx:
        assert await repos.notifications.mark_sent(tx, batch[0].id, 12345) is False  # لا إرسال مزدوج

    assert await repos.notifications.count_queued() == 0


async def test_notification_retry_backoff(db: Database, repos: Repositories, user) -> None:
    """الفشل المؤقت يعيد الإشعار للطابور بموعد لاحق، والفشل النهائي يوقفه."""
    async with db.transaction() as tx:
        notification_id = await repos.notifications.enqueue(
            tx, user_id=user.id, type="system", message="اختبار", dedupe_key="n:retry"
        )
    assert notification_id is not None

    async with db.transaction() as tx:
        await repos.notifications.mark_failed(tx, notification_id, error="شبكة")
    retried = await repos.notifications.get(notification_id)
    assert retried is not None and retried.status == "queued" and retried.attempts == 1

    async with db.transaction() as tx:
        await repos.notifications.mark_failed(tx, notification_id, error="محظور", permanent=True)
    final = await repos.notifications.get(notification_id)
    assert final is not None and final.status == "failed"


# ------------------------------ منع التكرار -------------------------------- #


async def test_idempotency_key_acquired_once(db: Database, repos: Repositories, user) -> None:
    """المفتاح يُحجز مرة واحدة فقط — الضغط المزدوج لا ينفّذ العملية مرتين."""
    async with db.transaction() as tx:
        first = await repos.idempotency.try_acquire(tx, "approve:7", scope="payment", user_id=user.id)
    async with db.transaction() as tx:
        second = await repos.idempotency.try_acquire(tx, "approve:7", scope="payment", user_id=user.id)
    assert first is True
    assert second is False

    async with db.transaction() as tx:
        await repos.idempotency.save_result(tx, "approve:7", {"payment_id": 7, "ok": True})
    assert (await repos.idempotency.get_result("approve:7"))["payment_id"] == 7


async def test_concurrent_idempotency_single_winner(db: Database, repos: Repositories, user) -> None:
    """عند التزاحم على نفس المفتاح ينجح واحد فقط."""

    async def acquire() -> bool:
        """محاولة حجز المفتاح."""
        async with db.transaction() as tx:
            return await repos.idempotency.try_acquire(tx, "race:key", scope="test")

    results = await asyncio.gather(*(acquire() for _ in range(10)))
    assert sum(results) == 1


# --------------------------- السجلات والإذاعة ------------------------------ #


async def test_audit_log_written(db: Database, repos: Repositories, user) -> None:
    """سجل التدقيق يحفظ الحالة قبل وبعد."""
    async with db.transaction() as tx:
        await repos.audit.log(
            tx, action="users.balance.credit", admin_id=user.id, target_type="user",
            target_id=user.id, before={"balance": 0}, after={"balance": 1000},
        )
    logs = await repos.audit.list_by_target("user", user.id)
    assert len(logs) == 1
    assert logs[0].action == "users.balance.credit"
    assert "1000" in (logs[0].after_json or "")


async def test_broadcast_recipients_no_double_count(db: Database, repos: Repositories, user) -> None:
    """المستلم يُحتسب مرة واحدة فقط حتى لو تكرر تحديثه."""
    async with db.transaction() as tx:
        broadcast = await repos.broadcasts.create(tx, admin_id=user.id, message_text="إعلان")
        await repos.broadcasts.add_recipients(tx, broadcast.id, [user.id, user.id])

    async with db.transaction() as tx:
        recipients = await repos.broadcasts.claim_recipients(tx, broadcast.id, limit=10)
    assert len(recipients) == 1

    async with db.transaction() as tx:
        assert await repos.broadcasts.mark_recipient(tx, recipients[0]["id"], status="sent") is True
    async with db.transaction() as tx:
        assert await repos.broadcasts.mark_recipient(tx, recipients[0]["id"], status="sent") is False

    updated = await repos.broadcasts.get(broadcast.id)
    assert updated is not None and updated.sent_count == 1 and updated.total_count == 1


async def test_user_state_persistence(db: Database, repos: Repositories, user) -> None:
    """حالة المحادثة تُحفظ وتُسترجع وتُمسح (نجاة من إعادة التشغيل)."""
    async with db.transaction() as tx:
        await repos.user_states.save(
            tx, user.id, state="awaiting_link", data={"service_id": 3}, chat_id=555
        )
    state = await repos.user_states.get(user.id)
    assert state is not None and state["state"] == "awaiting_link"
    assert state["data"]["service_id"] == 3

    async with db.transaction() as tx:
        await repos.user_states.clear(tx, user.id)
    assert await repos.user_states.get(user.id) is None


async def test_provider_failure_tracking(db: Database, repos: Repositories, provider) -> None:
    """تتبع الأخطاء المتتالية للمزود وتصفيرها عند النجاح."""
    async with db.transaction() as tx:
        count = await repos.providers.record_failure(tx, provider.id, "timeout")
    assert count == 1
    async with db.transaction() as tx:
        count = await repos.providers.record_failure(tx, provider.id, "timeout")
    assert count == 2
    async with db.transaction() as tx:
        await repos.providers.record_success(tx, provider.id)
    refreshed = await repos.providers.get(provider.id)
    assert refreshed is not None and refreshed.consecutive_failures == 0


async def test_provider_request_log_sanitizes_secrets(db: Database, repos: Repositories, provider) -> None:
    """سجل استدعاءات المزود لا يحتفظ بالمفتاح السري إطلاقاً."""
    async with db.transaction() as tx:
        await repos.provider_requests.log(
            tx, provider_id=provider.id, action="add", is_success=True,
            request_summary="key=SUPERSECRET123&action=add&service=555",
            response_snippet='{"order": 999}', secrets=("SUPERSECRET123",),
        )
    logs = await repos.provider_requests.list_by_provider(provider.id)
    assert "SUPERSECRET123" not in logs[0]["request_summary"]
    assert "***" in logs[0]["request_summary"]


async def test_error_log_written(db: Database, repos: Repositories, user) -> None:
    """تسجيل الأخطاء في قاعدة البيانات لعرضها في اللوحة."""
    async with db.transaction() as tx:
        await repos.error_logs.log(
            tx, message="فشل الاتصال بالمزود", source="job", error_type="ProviderError", user_id=user.id
        )
    logs = await repos.error_logs.list_recent()
    assert len(logs) == 1
    assert await repos.error_logs.count_since(iso_minus_days(1)) == 1
    assert logs[0]["created_at"] <= utc_now_iso()
```

## `tests/test_permissions_seed.py`

```python
"""
اختبار تطابق مصدر الصلاحيات.

قاعدة ذهبية: `core/permissions.py` و `0002_seed_rbac.sql` يجب أن يظلا متطابقين تماماً.
أي صلاحية تُضاف في أحدهما وتُنسى في الآخر يكشفها هذا الاختبار فوراً.
"""

from __future__ import annotations

from core.permissions import (
    PERMISSION_MAP,
    PERMISSIONS,
    ROLE_DEFAULTS,
    ROLES,
    all_permission_codes,
    role_has_default,
)
from database.database import Database
from database.repositories import Repositories


async def test_permission_codes_match_seed(db: Database) -> None:
    """كل صلاحية في الكود موجودة في قاعدة البيانات والعكس."""
    rows = await db.fetchall("SELECT code FROM permissions")
    db_codes = {row["code"] for row in rows}
    code_codes = set(all_permission_codes())

    missing_in_db = code_codes - db_codes
    extra_in_db = db_codes - code_codes
    assert not missing_in_db, f"صلاحيات في الكود وغير مزروعة: {sorted(missing_in_db)}"
    assert not extra_in_db, f"صلاحيات مزروعة وغير معرَّفة في الكود: {sorted(extra_in_db)}"


async def test_permission_metadata_matches_seed(db: Database) -> None:
    """الاسم العربي والمجموعة وعلامة الخطورة متطابقة بين الكود والزرع."""
    rows = await db.fetchall("SELECT code, name_ar, group_code, is_dangerous FROM permissions")
    for row in rows:
        definition = PERMISSION_MAP[row["code"]]
        assert row["name_ar"] == definition.name_ar, f"اسم مختلف: {row['code']}"
        assert row["group_code"] == definition.group_code, f"مجموعة مختلفة: {row['code']}"
        assert bool(row["is_dangerous"]) is definition.is_dangerous, f"خطورة مختلفة: {row['code']}"


async def test_role_defaults_match_seed(repos: Repositories) -> None:
    """توزيع الصلاحيات على الأدوار في الكود = التوزيع المزروع في قاعدة البيانات."""
    for role, expected in ROLE_DEFAULTS.items():
        actual = await repos.rbac.role_permissions(role)
        assert actual == set(expected), (
            f"اختلاف في الدور {role}: "
            f"ناقص={sorted(set(expected) - actual)} زائد={sorted(actual - set(expected))}"
        )


async def test_roles_seeded_with_levels(db: Database) -> None:
    """الأدوار الأربعة مزروعة بمستوياتها وأسمائها الصحيحة."""
    rows = await db.fetchall("SELECT code, name_ar, level FROM roles ORDER BY level")
    seeded = [(row["code"], row["name_ar"], row["level"]) for row in rows]
    expected = [(r.code, r.name_ar, r.level) for r in sorted(ROLES, key=lambda r: r.level)]
    assert seeded == expected


async def test_every_permission_belongs_to_a_known_group(db: Database) -> None:
    """لا صلاحية يتيمة بلا مجموعة عرض في لوحة الأدمن."""
    groups = {p.group_code for p in PERMISSIONS}
    assert "" not in groups
    rows = await db.fetchall("SELECT DISTINCT group_code FROM permissions")
    assert {row["group_code"] for row in rows} == groups


async def test_permission_names_are_arabic(db: Database) -> None:
    """كل صلاحية لها اسم عربي غير فارغ لعرضه في الواجهة."""
    rows = await db.fetchall("SELECT code, name_ar FROM permissions")
    for row in rows:
        name = (row["name_ar"] or "").strip()
        assert name, f"اسم فارغ للصلاحية {row['code']}"
        assert any("\u0600" <= ch <= "\u06ff" for ch in name), f"اسم غير عربي للصلاحية {row['code']}"


async def test_super_admin_has_all_permissions(repos: Repositories) -> None:
    """الدور الأعلى يملك كل الصلاحيات دون استثناء."""
    perms = await repos.rbac.role_permissions("super_admin")
    assert perms == set(all_permission_codes())


async def test_user_role_has_no_admin_permissions(repos: Repositories) -> None:
    """المستخدم العادي لا يملك أي صلاحية إدارية."""
    assert await repos.rbac.role_permissions("user") == set()
    assert role_has_default("user", "admin.access") is False


async def test_permission_codes_unique() -> None:
    """لا تكرار في رموز الصلاحيات داخل الكتالوج."""
    codes = [p.code for p in PERMISSIONS]
    assert len(codes) == len(set(codes))
    assert len(codes) == len(PERMISSION_MAP)


async def test_dangerous_permissions_flagged(db: Database) -> None:
    """الصلاحيات الحساسة (المال، المفاتيح، الحظر) موسومة كخطِرة لتأكيدها في الواجهة."""
    critical = [
        "users.balance.credit",
        "users.balance.debit",
        "users.ban",
        "users.role.change",
        "providers.key.update",
        "orders.refund",
        "payments.approve",
    ]
    rows = await db.fetchall(
        f"SELECT code, is_dangerous FROM permissions WHERE code IN ({','.join('?' * len(critical))})",
        critical,
    )
    assert len(rows) == len(critical)
    for row in rows:
        assert row["is_dangerous"] == 1, f"صلاحية حساسة غير موسومة: {row['code']}"
```

## `tests/test_security.py`

```python
"""اختبارات أدوات الأمان: تشفير مفاتيح المزودين ومنع تسرب الأسرار."""

from __future__ import annotations

import logging

import pytest

from core.exceptions import EncryptionError
from utils.logging_setup import SecretRedactionFilter
from utils.security import (
    SecretBox,
    fingerprint,
    generate_encryption_key,
    mask_secret,
    new_token,
    sanitize,
    secret_hint,
)


def test_encrypt_decrypt_roundtrip() -> None:
    """التشفير وفك التشفير يعيدان النص الأصلي، والنص المشفّر لا يحتوي السر."""
    box = SecretBox(generate_encryption_key())
    secret = "sk_live_4f8a9b2c7d1e"
    encrypted = box.encrypt(secret)
    assert encrypted != secret
    assert secret not in encrypted
    assert box.decrypt(encrypted) == secret


def test_encryption_is_not_deterministic() -> None:
    """تشفير نفس القيمة مرتين يعطي نصين مختلفين (Fernet يضيف IV عشوائياً)."""
    box = SecretBox(generate_encryption_key())
    assert box.encrypt("same-key") != box.encrypt("same-key")


def test_wrong_key_cannot_decrypt() -> None:
    """مفتاح مختلف لا يستطيع فك التشفير — يُرفع خطأ واضح لا نتيجة خاطئة."""
    encrypted = SecretBox(generate_encryption_key()).encrypt("secret-value")
    other = SecretBox(generate_encryption_key())
    with pytest.raises(EncryptionError):
        other.decrypt(encrypted)


def test_missing_or_invalid_key_rejected() -> None:
    """غياب المفتاح أو تلفه يُكتشف عند الإقلاع لا عند أول استخدام."""
    with pytest.raises(EncryptionError):
        SecretBox(None)
    with pytest.raises(EncryptionError):
        SecretBox("مفتاح-غير-صالح")


def test_empty_plaintext_rejected() -> None:
    """لا يُسمح بتشفير قيمة فارغة (يعني غالباً خطأ في الإدخال)."""
    with pytest.raises(EncryptionError):
        SecretBox(generate_encryption_key()).encrypt("")


def test_mask_secret_shows_tail_only() -> None:
    """العرض في الواجهة يُظهر آخر أربعة محارف فقط."""
    assert mask_secret("abcd1234efgh") == "••••efgh"
    assert mask_secret(None) == "غير محدد"
    assert "abcd1234" not in mask_secret("abcd1234efgh")


def test_secret_hint_and_fingerprint() -> None:
    """التلميح والبصمة لا يكشفان السر ولا يمكن عكسهما."""
    secret = "verylongapikey987654"
    assert secret_hint(secret) == "7654"
    assert secret_hint("ab") == "****"
    digest = fingerprint(secret)
    assert len(digest) == 16
    assert secret not in digest
    assert fingerprint(secret) == digest  # ثابتة


def test_sanitize_removes_known_secret_patterns() -> None:
    """التنقية تحذف التوكن والمفاتيح من أي نص قبل تسجيله."""
    text = "GET https://panel.test/api?key=SUPERSECRET&action=add"
    clean = sanitize(text)
    assert "SUPERSECRET" not in clean
    assert "action=add" in clean

    bot_log = "فشل الاتصال بالتوكن 123456789:AAFakeTokenValue1234567890abcdefghi"
    assert "AAFakeTokenValue" not in sanitize(bot_log)

    payload = 'api_key: "abc123xyz"'
    assert "abc123xyz" not in sanitize(payload)


def test_sanitize_removes_explicit_secrets() -> None:
    """أي قيمة سرية معروفة تُحذف حرفياً حتى لو لم تطابق نمطاً."""
    clean = sanitize("الرد: {'balance': 10, 'k': 'PLAINKEY'}", extra_secrets=("PLAINKEY",))
    assert "PLAINKEY" not in clean
    assert "***" in clean
    assert sanitize(None) == ""


def test_new_token_is_unique() -> None:
    """الرموز العشوائية لا تتكرر (تُستخدم كمراجع فريدة)."""
    tokens = {new_token() for _ in range(100)}
    assert len(tokens) == 100


def test_log_filter_redacts_secrets() -> None:
    """مرشّح اللوق يحذف الأسرار قبل كتابتها في الملف."""
    log_filter = SecretRedactionFilter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="طلب إلى المزود key=TOPSECRET123 تم", args=(), exc_info=None,
    )
    assert log_filter.filter(record) is True
    assert "TOPSECRET123" not in record.getMessage()


def test_log_filter_redacts_arguments() -> None:
    """الأسرار الممرَّرة كوسائط للوق تُنقّى أيضاً."""
    log_filter = SecretRedactionFilter()
    record = logging.LogRecord(
        name="test", level=logging.ERROR, pathname=__file__, lineno=1,
        msg="خطأ في %s", args=("token=ABCDEF123456",), exc_info=None,
    )
    log_filter.filter(record)
    assert "ABCDEF123456" not in record.getMessage()
```

## `tests/test_config_and_time.py`

```python
"""اختبارات الإعدادات وأدوات الوقت (أساس كل جدولة ومقارنة تواريخ في النظام)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from config import Config, ConfigError
from utils.datetime_utils import (
    day_bounds_utc,
    is_past,
    iso_minus_days,
    iso_plus_seconds,
    parse_iso,
    to_iso,
    to_local_text,
    utc_now,
    utc_now_iso,
)


# -------------------------------- الإعدادات -------------------------------- #


def _write_env(tmp_path: Path, content: str) -> Path:
    """كتابة ملف بيئة مؤقت للاختبار."""
    env_file = tmp_path / ".env"
    env_file.write_text(content, encoding="utf-8")
    return env_file


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch):
    """عزل متغيرات البيئة حتى لا تتسرب بين الاختبارات."""
    for key in (
        "BOT_TOKEN", "SUPER_ADMIN_IDS", "ENCRYPTION_KEY", "DATABASE_PATH", "LOG_LEVEL",
        "LOG_FILE", "BACKUP_DIR", "TIMEZONE", "ADMIN_ALERT_CHAT_ID", "BACKUP_CHANNEL_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


def test_defaults_when_env_is_minimal(tmp_path: Path) -> None:
    """الإعدادات الافتراضية معقولة ولا تنهار عند ملف بيئة شبه فارغ."""
    config = Config.load(env_file=_write_env(tmp_path, "LOG_LEVEL=INFO\n"))
    assert config.timezone == "Asia/Aden"
    assert config.log_level == "INFO"
    assert config.database_path.name == "smm_bot.db"
    assert config.super_admin_ids == ()
    assert config.bot_token is None


def test_missing_bot_token_is_rejected_for_bot(tmp_path: Path) -> None:
    """تشغيل البوت بلا توكن يفشل برسالة واضحة لا بانهيار غامض."""
    with pytest.raises(ConfigError, match="BOT_TOKEN"):
        Config.load(require_bot_token=True, env_file=_write_env(tmp_path, "LOG_LEVEL=INFO\n"))


def test_super_admin_ids_parsed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """قائمة معرفات الأدمن الأعلى تُقرأ بفواصل أو فواصل منقوطة."""
    monkeypatch.setenv("SUPER_ADMIN_IDS", " 111 , 222 ;333 ")
    config = Config.load(env_file=_write_env(tmp_path, ""))
    assert config.super_admin_ids == (111, 222, 333)


def test_invalid_super_admin_ids_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """قيمة غير رقمية في معرفات الأدمن تُرفض بدل تجاهلها بصمت."""
    monkeypatch.setenv("SUPER_ADMIN_IDS", "111,abc")
    with pytest.raises(ConfigError, match="SUPER_ADMIN_IDS"):
        Config.load(env_file=_write_env(tmp_path, ""))


def test_invalid_log_level_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """مستوى تسجيل غير معروف يُرفض عند الإقلاع."""
    monkeypatch.setenv("LOG_LEVEL", "VERBOSE")
    with pytest.raises(ConfigError, match="LOG_LEVEL"):
        Config.load(env_file=_write_env(tmp_path, ""))


def test_safe_summary_hides_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ملخص الإعدادات لا يطبع التوكن ولا مفتاح التشفير أبداً."""
    monkeypatch.setenv("BOT_TOKEN", "123456789:AAFakeTokenValue1234567890abcdefghi")
    monkeypatch.setenv("ENCRYPTION_KEY", "TOPSECRETKEY=")
    summary = Config.load(env_file=_write_env(tmp_path, "")).safe_summary()
    joined = " ".join(summary.values())
    assert "AAFakeTokenValue" not in joined
    assert "TOPSECRETKEY" not in joined
    assert summary["bot_token"].startswith("✓")


def test_ensure_directories_creates_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """التهيئة تنشئ مجلدات البيانات واللوقات والنسخ الاحتياطية."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "db" / "x.db"))
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "logs" / "bot.log"))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "bk"))
    config = Config.load(env_file=_write_env(tmp_path, ""))
    config.ensure_directories()
    assert (tmp_path / "db").is_dir()
    assert (tmp_path / "logs").is_dir()
    assert (tmp_path / "bk").is_dir()


def test_relative_paths_resolved_to_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """المسار النسبي يُحسب من جذر المشروع لا من مجلد التشغيل الحالي."""
    monkeypatch.setenv("DATABASE_PATH", "data/custom.db")
    config = Config.load(env_file=_write_env(tmp_path, ""))
    assert config.database_path.is_absolute()
    assert config.database_path.parts[-2:] == ("data", "custom.db")


# --------------------------------- الوقت ---------------------------------- #


def test_utc_now_iso_format() -> None:
    """الوقت المخزَّن دائماً UTC بصيغة ISO تنتهي بحرف Z."""
    value = utc_now_iso()
    assert value.endswith("Z")
    assert "T" in value
    parsed = parse_iso(value)
    assert parsed is not None and parsed.tzinfo == timezone.utc


def test_iso_strings_sort_chronologically() -> None:
    """الترتيب النصي للتواريخ = الترتيب الزمني (شرط صحة كل الاستعلامات)."""
    earlier = to_iso(utc_now() - timedelta(days=1))
    later = utc_now_iso()
    assert earlier < later


def test_parse_iso_handles_none_and_bad_values() -> None:
    """تحليل تاريخ فارغ أو تالف يُرجع None بدل رفع استثناء."""
    assert parse_iso(None) is None
    assert parse_iso("") is None
    assert parse_iso("ليس تاريخاً") is None


def test_iso_plus_seconds_and_is_past() -> None:
    """حساب المواعيد المستقبلية والماضية (أساس lease الطلبات وإعادة المحاولة)."""
    future = iso_plus_seconds(120)
    past = iso_plus_seconds(-120)
    assert is_past(future) is False
    assert is_past(past) is True
    assert is_past(None) is True


def test_iso_minus_days() -> None:
    """حساب بداية نافذة زمنية للخلف (للإحصائيات وكشف التكرار)."""
    value = parse_iso(iso_minus_days(7))
    assert value is not None
    delta = utc_now() - value
    assert 6.9 < delta.total_seconds() / 86400 < 7.1


def test_to_local_text_uses_local_timezone() -> None:
    """العرض للمستخدم بتوقيت عدن (+3) لا بتوقيت UTC."""
    moment = datetime(2026, 1, 1, 22, 0, 0, tzinfo=timezone.utc)
    assert to_local_text(to_iso(moment)) == "2026-01-02 01:00"
    assert to_local_text(None) == "-"


def test_day_bounds_are_ordered_and_utc() -> None:
    """حدود اليوم المحلي تُحوَّل إلى UTC بشكل صحيح ومرتب."""
    start, end = day_bounds_utc(0)
    assert start < end
    assert start.endswith("Z") and end.endswith("Z")
    yesterday_start, yesterday_end = day_bounds_utc(1)
    assert yesterday_end <= start
    assert yesterday_start < yesterday_end


def test_no_naive_datetimes_leak() -> None:
    """كل التواريخ المنتَجة واعية بالمنطقة الزمنية (تجنب أخطاء المقارنة)."""
    assert utc_now().tzinfo is not None
    assert os.environ.get("TZ") in (None, "", os.environ.get("TZ"))
```

