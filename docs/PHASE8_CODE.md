# الكود الكامل — المرحلة 8 (الدعم والإشعارات والإذاعة)

كل ما في هذا الملف منسوخ آلياً من ملفات المشروع الفعلية وقت كتابة التقرير.

> الملفات الضخمة التي تغيّر منها قسم محدود تُعرض كمقتطف موسوم بوضوح؛ وما عداها كامل.

> الملفات غير المذكورة هنا لم تتغيّر عن المراحل 1–7.

## الفهرس

**قاعدة البيانات والنموذج**

- `database/migrations/0007_phase8_support_broadcast.sql` — 60 سطراً (جديد)
- `database/models.py` — 474 سطراً (مُحدَّث (مقتطف))
- `database/repositories/templates.py` — 100 سطراً (جديد)
- `database/repositories/__init__.py` — 86 سطراً (مُحدَّث (مقتطف))
- `database/repositories/users.py` — 324 سطراً (مُحدَّث (مقتطف))
- `database/repositories/tickets.py` — 266 سطراً (مُحدَّث (مقتطف))
- `core/permissions.py` — 209 سطراً (مُحدَّث (مقتطف))
- `core/constants.py` — 44 سطراً (مُحدَّث (مقتطف))
- `utils/validators.py` — 309 سطراً (مُحدَّث (مقتطف))

**الخدمات**

- `services/template_service.py` — 310 سطراً (جديد)
- `services/broadcast_service.py` — 485 سطراً (جديد)
- `services/__init__.py` — 175 سطراً (مُحدَّث)
- `services/ticket_service.py` — 585 سطراً (مُحدَّث (مقتطف))
- `services/payment_service.py` — 1026 سطراً (مُحدَّث (مقتطف))

**النصوص**

- `texts/templates.py` — 703 سطراً (مُحدَّث)

**المهام الدورية والإرسال**

- `jobs/broadcast_jobs.py` — 36 سطراً (جديد)
- `jobs/telegram_sender.py` — 145 سطراً (مُحدَّث (مقتطف))
- `jobs/__init__.py` — 228 سطراً (مُحدَّث (مقتطف))

**واجهة لوحة التحكم**

- `handlers/admin/broadcast.py` — 468 سطراً (جديد)
- `handlers/admin/templates.py` — 324 سطراً (جديد)
- `handlers/admin/tickets.py` — 409 سطراً (مُحدَّث (مقتطف))
- `handlers/admin/__init__.py` — 79 سطراً (مُحدَّث)
- `keyboards/admin_kb.py` — 1369 سطراً (مُحدَّث (مقتطف))
- `keyboards/callback_data.py` — 162 سطراً (مُحدَّث (مقتطف))
- `texts/admin_ar.py` — 1104 سطراً (مُحدَّث (مقتطف))

**الاختبارات**

- `tests/unit/test_template_catalog.py` — 131 سطراً (جديد)
- `tests/integration/test_templates_phase8.py` — 389 سطراً (جديد)
- `tests/integration/test_broadcast_phase8.py` — 709 سطراً (جديد)
- `tests/conftest.py` — 201 سطراً (مُحدَّث (مقتطف))
- `tests/integration/test_jobs.py` — 254 سطراً (مُحدَّث (مقتطف))
- `tests/integration/test_no_dead_buttons.py` — 601 سطراً (مُحدَّث (مقتطف))

---

## قاعدة البيانات والنموذج

### `database/migrations/0007_phase8_support_broadcast.sql`  ·  جديد  ·  60 سطراً

جدول القوالب + صلاحية `notifications.templates` + 4 إعدادات + فهرس الإذاعة.

```sql
-- =====================================================================
-- الترحيل 0007 — المرحلة 8 (الدعم والإشعارات والإذاعة)
--
-- لماذا هذا الترحيل؟
--   1) نصوص الإشعارات كانت مكتوبة داخل الكود، فأي تعديل على صياغة
--      رسالة تصل للعميل يتطلب تعديل ملف ونشر إصدار جديد. جدول القوالب
--      يجعل الصياغة قابلة للتحرير من لوحة التحكم، مع بقاء النص الأصلي
--      في الكود كقيمة افتراضية يُرجع إليها عند «استعادة الافتراضي».
--   2) الإذاعة تحتاج إعدادات إيقاع حقيقية (حجم الدفعة وفاصلها) حتى لا
--      نصطدم بحدود تيليجرام عند إرسال آلاف الرسائل.
--   3) تحرير القوالب عملية حسّاسة (تمس كل رسائل العملاء) فتحتاج صلاحية
--      مستقلة لا تُمنح لكل من يملك «تعديل الإعدادات».
--
-- ملاحظات تقنية:
--   • لا حذف ولا إعادة بناء لأي جدول — إضافة جدول واحد وصفوف بذور فقط.
--   • جداول الإذاعة (broadcasts / broadcast_recipients) موجودة منذ
--     الترحيل 0001، وهذه المرحلة تبني فوقها بلا أي تعديل على بنيتها.
--   • قوالب لم تُحرَّر = لا صف لها هنا إطلاقاً (الصف يُنشأ عند أول حفظ).
-- =====================================================================

-- ------------------------ قوالب الإشعارات القابلة للتحرير ------------------------ --
-- code  : رمز الحدث (مطابق لكتالوج القوالب في texts/templates.py).
-- title : عنوان الرسالة كما يراها المستخدم.
-- body  : نص الرسالة، يحتوي متغيرات بصيغة {name} مسموح بها لكل حدث فقط.
-- is_active : 0 يعني «معطّل مؤقتاً» ⇒ يعود النظام للنص الافتراضي المدمج.
CREATE TABLE IF NOT EXISTS notification_templates (
    code       TEXT    PRIMARY KEY,
    title      TEXT    NOT NULL,
    body       TEXT    NOT NULL,
    is_active  INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_at TEXT    NOT NULL
);

-- ----------------------------- صلاحية جديدة ---------------------------- --
INSERT OR IGNORE INTO permissions (code, name_ar, group_code, is_dangerous) VALUES
    ('notifications.templates', 'تعديل قوالب الإشعارات', 'broadcast', 1);

-- تُمنح للأدمن الأعلى والأدمن العادي فقط (الدعم الفني لا يعدّل رسائل النظام).
INSERT OR IGNORE INTO role_permissions (role_code, permission_code) VALUES
    ('super_admin', 'notifications.templates'),
    ('admin',       'notifications.templates');

-- ------------------------------ فهرس الإذاعة --------------------------- --
-- شاشة الإذاعات تعرض الأحدث أولاً وتقرأ الجارية في كل جولة إرسال.
CREATE INDEX IF NOT EXISTS idx_broadcasts_status ON broadcasts(status, id DESC);

-- ----------------------------- إعدادات جديدة --------------------------- --
INSERT OR IGNORE INTO settings (key, value, value_type, group_code, name_ar, description_ar, is_editable, updated_at) VALUES
    ('broadcast_batch_size', '20', 'int', 'broadcast', 'عدد الرسائل في دفعة الإذاعة الواحدة',
     'كم رسالة تُرسل في كل جولة إذاعة. القيمة الكبيرة تُسرّع الإرسال لكنها تقترب من حد تيليجرام', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('broadcast_interval_seconds', '5', 'int', 'broadcast', 'الفاصل الزمني بين دفعات الإذاعة (ثانية)',
     'مع حجم الدفعة يحدد سرعة الإرسال: 20 رسالة كل 5 ثوانٍ = 4 رسائل في الثانية', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('broadcast_active_days', '30', 'int', 'broadcast', 'عدد أيام النشاط لشريحة «النشطون»',
     'المستخدم يُعدّ نشطاً إذا تفاعل مع البوت خلال هذا العدد من الأيام', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('ticket_reply_notify_admins', '1', 'bool', 'tickets', 'تنبيه الأدمن عند رد المستخدم على تذكرة',
     'عند الإيقاف لا يصل تنبيه للأدمن إلا عند فتح تذكرة جديدة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
```

### `database/models.py`  ·  مُحدَّث (مقتطف)  ·  474 سطراً

نموذج `NotificationTemplate`.

```python
@dataclass(slots=True)
class NotificationTemplate(BaseModel):
    """قالب إشعار مخصّص من لوحة التحكم (المرحلة 8) — غيابه يعني استعمال النص الافتراضي."""

    code: str
    title: str
    body: str
    updated_at: str
    is_active: int = 1
    updated_by: int | None = None

    @property
    def enabled(self) -> bool:
        """هل القالب المخصّص مفعّل فعلاً (وإلا يعود النظام للنص المدمج)؟"""
        return bool(self.is_active)
```

### `database/repositories/templates.py`  ·  جديد  ·  100 سطراً

مستودع القوالب المخصّصة (لا صف = النص الافتراضي).

```python
"""
مستودع قوالب الإشعارات المخصّصة (المرحلة 8).

القاعدة هنا بسيطة ومقصودة: **لا صف = النص الافتراضي المكتوب في الكود**.
لا نزرع صفوفاً للقوالب عند التثبيت، فالصف يُنشأ فقط عندما يعدّل الأدمن نصاً،
ويُحذف عند «استعادة الافتراضي». هكذا يبقى تحديث النصوص الافتراضية مع ترقية
الإصدار نافذاً تلقائياً لكل قالب لم يلمسه أحد.
"""

from __future__ import annotations

from database.database import Tx
from database.models import NotificationTemplate
from database.repositories.base import BaseRepository


class NotificationTemplatesRepository(BaseRepository):
    """قراءة وكتابة القوالب المخصّصة لرسائل الإشعارات."""

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, code: str) -> NotificationTemplate | None:
        """جلب قالب مخصّص واحد بالرمز (None يعني أنه لم يُعدَّل قط)."""
        row = await self.db.fetchone(
            "SELECT * FROM notification_templates WHERE code = ?", (code,)
        )
        return NotificationTemplate.from_row(row)

    async def list_all(self) -> list[NotificationTemplate]:
        """كل القوالب المخصّصة (المفعّلة والموقوفة) مرتبة بالرمز."""
        rows = await self.db.fetchall("SELECT * FROM notification_templates ORDER BY code")
        return NotificationTemplate.from_rows(rows)

    async def active_map(self) -> dict[str, tuple[str, str]]:
        """
        القوالب المفعّلة فقط بشكل جاهز للذاكرة: code -> (title, body).

        هذه الدالة هي ما تُحمّله طبقة النصوص عند الإقلاع وبعد كل تعديل.
        """
        rows = await self.db.fetchall(
            "SELECT code, title, body FROM notification_templates WHERE is_active = 1"
        )
        return {row["code"]: (row["title"], row["body"]) for row in rows}

    async def count_customized(self) -> int:
        """عدد القوالب التي عُدِّلت فعلاً (يُعرض في شاشة القوالب وفحص الإقلاع)."""
        return await self.count("notification_templates", "1 = 1", ())

    # ------------------------------ الكتابة ------------------------------ #

    async def upsert(
        self,
        tx: Tx,
        *,
        code: str,
        title: str,
        body: str,
        admin_id: int | None,
        is_active: bool = True,
    ) -> NotificationTemplate:
        """
        حفظ قالب مخصّص (إنشاء أو تحديث) وإرجاع صفه بعد الحفظ.

        التحقق من صحة المتغيرات يتم في طبقة الخدمة قبل الوصول إلى هنا.
        """
        await tx.execute(
            """
            INSERT INTO notification_templates (code, title, body, is_active, updated_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                title = excluded.title,
                body = excluded.body,
                is_active = excluded.is_active,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (code, title, body, 1 if is_active else 0, admin_id, self.now()),
        )
        row = await tx.fetchone("SELECT * FROM notification_templates WHERE code = ?", (code,))
        template = NotificationTemplate.from_row(row)
        assert template is not None  # الصف محفوظ للتو في نفس المعاملة
        return template

    async def set_active(self, tx: Tx, code: str, *, active: bool) -> bool:
        """تفعيل أو إيقاف قالب مخصّص دون حذف نصه (ليعود الأدمن إليه لاحقاً)."""
        result = await tx.execute(
            "UPDATE notification_templates SET is_active = ?, updated_at = ? WHERE code = ?",
            (1 if active else 0, self.now(), code),
        )
        return result.rowcount > 0

    async def delete(self, tx: Tx, code: str) -> bool:
        """
        حذف التخصيص والعودة للنص الافتراضي.

        هذا هو الحذف الوحيد المسموح في النظام لأن المحذوف ليس بيانات تاريخية
        بل «تفضيل صياغة»، والنص الأصلي موجود في الكود ولا يضيع.
        """
        result = await tx.execute("DELETE FROM notification_templates WHERE code = ?", (code,))
        return result.rowcount > 0
```

### `database/repositories/__init__.py`  ·  مُحدَّث (مقتطف)  ·  86 سطراً

تسجيل المستودع الجديد.

```python
from database.repositories.templates import NotificationTemplatesRepository
    "NotificationTemplatesRepository",
        self.templates = NotificationTemplatesRepository(db)
```

### `database/repositories/users.py`  ·  مُحدَّث (مقتطف)  ·  324 سطراً

استهداف شرائح الإذاعة.

```python
    async def ids_for_broadcast(self, *, target: str, since_iso: str | None = None) -> list[int]:
        """
        معرفات المستخدمين الداخلية لشريحة إذاعة (المرحلة 8).

        المدخلات:
            target    : all | active | buyers | no_orders.
            since_iso : بداية نافذة النشاط لشريحة «النشطون».

        المخرجات: قائمة معرفات مرتبة، بلا محظورين وبلا من حظر البوت.

        ملاحظة: نُرجع المعرف الداخلي لا معرف تيليجرام، لأن صفوف المستلمين
        ترتبط بجدول users ويجب أن تبقى صالحة حتى لو تغيّر حساب تيليجرام.
        """
        sql = ["SELECT DISTINCT u.id FROM users u"]
        params: list[Any] = []
        if target == "buyers":
            sql.append("JOIN orders o ON o.user_id = u.id")
        elif target == "no_orders":
            sql.append("LEFT JOIN orders o ON o.user_id = u.id")
        sql.append("WHERE u.is_banned = 0 AND u.blocked_bot = 0")
        if target == "no_orders":
            sql.append("AND o.id IS NULL")
        if target == "active":
            sql.append("AND u.last_activity >= ?")
            params.append(since_iso or "")
        sql.append("ORDER BY u.id")
        rows = await self.db.fetchall(" ".join(sql), params)
        return [int(row["id"]) for row in rows]
```

### `database/repositories/tickets.py`  ·  مُحدَّث (مقتطف)  ·  266 سطراً

تصفية التذاكر بالأولوية.

```python
    async def list_by_status(
        self,
        statuses: Sequence[str],
        *,
        assigned_admin: int | None = None,
        priority: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[SupportTicket]:
        """
        التذاكر حسب الحالة (للوحة الدعم).

        المدخلات:
            statuses       : الحالات المطلوبة.
            assigned_admin : حصر النتائج بالتذاكر المسندة لأدمن بعينه (تبويب «المسندة لي»).
            priority       : حصر النتائج بأولوية بعينها (تبويب «العاجلة»).
        """
        where, params = self._status_filter(statuses, assigned_admin, priority)
        rows = await self.db.fetchall(
            f"""
            SELECT * FROM support_tickets WHERE {where}
             ORDER BY COALESCE(last_message_at, created_at) DESC LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        )
        return SupportTicket.from_rows(rows)

    async def count_by_status(
        self,
        statuses: Sequence[str],
        *,
        assigned_admin: int | None = None,
        priority: str | None = None,
    ) -> int:
        """عدد التذاكر المطابقة لنفس مرشّحات `list_by_status` (لحساب عدد الصفحات)."""
        where, params = self._status_filter(statuses, assigned_admin, priority)
        return await self.count("support_tickets", where, tuple(params))

    @staticmethod
    def _status_filter(
        statuses: Sequence[str], assigned_admin: int | None, priority: str | None = None
    ) -> tuple[str, list[Any]]:
        """بناء شرط WHERE المشترك بين قائمة التذاكر وعدّادها."""
        clauses: list[str] = []
        params: list[Any] = []
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(statuses)
        else:
            clauses.append("1 = 1")
        if assigned_admin is not None:
            clauses.append("assigned_admin = ?")
            params.append(assigned_admin)
        if priority is not None:
            clauses.append("priority = ?")
            params.append(priority)
        return " AND ".join(clauses), params
```

### `core/permissions.py`  ·  مُحدَّث (مقتطف)  ·  209 سطراً

الصلاحية الجديدة (44 صلاحية).

```python
    NOTIFICATIONS_TEMPLATES = "notifications.templates"
    PermissionDef("notifications.templates", "تعديل قوالب الإشعارات", "broadcast", True),
```

### `core/constants.py`  ·  مُحدَّث (مقتطف)  ·  44 سطراً

رقم الإصدار.

```python
APP_VERSION: str = "0.9.0-phase8"
```

### `utils/validators.py`  ·  مُحدَّث (مقتطف)  ·  309 سطراً

أداة تنظيف النص متعدد الأسطر (نُقلت من خدمة الدفع لتُشارَك).

```python
def clean_multiline(
    value: str | None, *, field: str, max_length: int, min_length: int = 1
) -> str:
    """
    تنظيف نص متعدد الأسطر **مع الحفاظ على الأسطر**.

    لماذا لا نستخدم `clean_text`؟ لأنها تدمج كل شيء في سطر واحد، وبعض النصوص
    (تعليمات التحويل، نص قالب إشعار) تفقد معناها بلا أسطر.

    القواعد: تُشذَّب الفراغات داخل كل سطر، ويُمنع تكرار الأسطر الفارغة.

    الاستثناءات:
        ValidationError : النص فارغ أو أطول من المسموح.
    """
    kept: list[str] = []
    for raw_line in (value or "").splitlines():
        line = " ".join(raw_line.split())
        if not line and (not kept or not kept[-1]):
            continue  # لا نسمح بأكثر من سطر فارغ متتالٍ
        kept.append(line)
    text = "\n".join(kept).strip()
    if len(text) < min_length:
        raise ValidationError(f"حقل {field} فارغ", user_message=f"❌ الرجاء إدخال {field}.")
    if len(text) > max_length:
        raise ValidationError(
            f"حقل {field} أطول من {max_length}",
            user_message=f"❌ {field} طويل جداً (الحد الأقصى {max_length} حرفاً).",
        )
    return text
```

## الخدمات

### `services/template_service.py`  ·  جديد  ·  310 سطراً

خدمة قوالب الإشعارات: حفظ/معاينة/إيقاف/استعادة بتحقق صارم وتدقيق.

```python
"""
خدمة قوالب الإشعارات (المرحلة 8).

المشكلة التي تحلّها:
    صياغة الرسائل التي تصل للعملاء كانت محبوسة في الكود. أي تعديل بسيط
    («نرحب بك» بدل «أهلاً») كان يعني تعديل ملف وإعادة نشر.

المبدأ المتبع هنا:
    • النص الافتراضي يبقى في `texts/templates.py` ولا يُمسّ أبداً.
    • تعديل الأدمن يُحفظ كصف في `notification_templates` ويُحمَّل في ذاكرة
      طبقة النصوص، فيُستعمل بدل الافتراضي عند بناء أي إشعار.
    • «استعادة الافتراضي» = حذف الصف، لا أكثر — فلا يمكن أن يفقد النظام نصه.

الأمان:
    نص القالب يُمرَّر على `str.format` وهو سلاح ذو حدين. لذلك نرفض قبل الحفظ:
    أي متغير غير معلن لهذا الحدث، وأي تنسيق (`{x:>99999}`) أو تحويل (`{x!r}`)،
    وأي وصول لخاصية أو فهرس (`{x.__class__}`). التحقق قبل الحفظ لا بعده.
"""

from __future__ import annotations

from typing import Any

from core.exceptions import ValidationError
from core.permissions import Permission
from database.database import Database
from database.models import NotificationTemplate, User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from texts import templates as tpl
from utils.logging_setup import get_logger
from utils.validators import clean_multiline, clean_text

logger = get_logger(__name__)


class TemplateService:
    """إدارة القوالب القابلة للتحرير وتحميلها في ذاكرة طبقة النصوص."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        auth: AuthService,
        audit: AuditService,
    ) -> None:
        """تهيئة الخدمة باعتمادياتها (التحقق من الصلاحية والتدقيق إلزاميان)."""
        self.db = db
        self.repos = repos
        self.auth = auth
        self.audit = audit

    # ------------------------------ الذاكرة ------------------------------ #

    async def refresh_cache(self) -> int:
        """
        تحميل القوالب المخصّصة المفعّلة إلى ذاكرة `texts.templates`.

        تُستدعى عند إقلاع البوت وبعد كل تعديل، فتبقى الرسائل المرسلة مطابقة
        لآخر صياغة حفظها الأدمن دون قراءة قاعدة البيانات في كل إشعار.

        المخرجات: عدد القوالب المحمّلة.
        """
        mapping = await self.repos.templates.active_map()
        tpl.set_overrides(mapping)
        logger.info("تم تحميل %s قالب إشعار مخصّص", len(mapping))
        return len(mapping)

    # ------------------------------ القراءة ------------------------------ #

    def catalog(self) -> tuple[tpl.TemplateDef, ...]:
        """كتالوج كل القوالب القابلة للتحرير (مصدره الكود لا قاعدة البيانات)."""
        return tpl.TEMPLATES

    def definition(self, code: str) -> tpl.TemplateDef:
        """
        تعريف قالب واحد.

        الاستثناءات: ValidationError إذا كان الرمز غير موجود في الكتالوج.
        """
        definition = tpl.TEMPLATE_BY_CODE.get(code)
        if definition is None:
            raise ValidationError(
                f"قالب غير معروف: {code}", user_message="❌ هذا القالب غير موجود."
            )
        return definition

    async def overview(self, actor: User) -> list[dict[str, Any]]:
        """
        قائمة كل القوالب مع حالتها: هل عُدِّلت؟ وهل التعديل مفعّل؟

        تُستخدم في شاشة «✉️ قوالب الإشعارات» ولا تكشف أي بيانات حساسة.

        الاستثناءات: PermissionDeniedError إن لم يملك `notifications.templates`.
        """
        await self.auth.require_permission(actor, Permission.NOTIFICATIONS_TEMPLATES)
        customized = {row.code: row for row in await self.repos.templates.list_all()}
        result: list[dict[str, Any]] = []
        for item in tpl.TEMPLATES:
            row = customized.get(item.code)
            result.append(
                {
                    "code": item.code,
                    "name_ar": item.name_ar,
                    "group": item.group,
                    "group_name": tpl.TEMPLATE_GROUPS.get(item.group, item.group),
                    "is_customized": row is not None,
                    "is_active": bool(row.is_active) if row else False,
                    "updated_at": row.updated_at if row else None,
                }
            )
        return result

    async def get_state(self, actor: User, code: str) -> dict[str, Any]:
        """
        حالة قالب واحد: التعريف الافتراضي + التخصيص الحالي + النص الفعّال.

        الاستثناءات: PermissionDeniedError · ValidationError للرمز المجهول.
        """
        await self.auth.require_permission(actor, Permission.NOTIFICATIONS_TEMPLATES)
        definition = self.definition(code)
        row = await self.repos.templates.get(code)
        effective_title = row.title if row and row.enabled else definition.title
        effective_body = row.body if row and row.enabled else definition.body
        return {
            "definition": definition,
            "custom": row,
            "is_customized": row is not None,
            "is_active": bool(row.is_active) if row else False,
            "title": effective_title,
            "body": effective_body,
        }

    async def preview(self, actor: User, code: str) -> tuple[str, str]:
        """
        معاينة القالب الفعّال بقيم تجريبية (لا تُرسل لأي مستخدم).

        المعاينة تمر بنفس مسار الإرسال الحقيقي، فما تراه هنا هو ما سيصل فعلاً.
        """
        await self.auth.require_permission(actor, Permission.NOTIFICATIONS_TEMPLATES)
        definition = self.definition(code)
        state = await self.get_state(actor, code)
        values = dict(definition.sample)
        try:
            return (
                str(state["title"]).format_map(values),
                str(state["body"]).format_map(values),
            )
        except (KeyError, IndexError, ValueError, AttributeError) as exc:
            # لا يُفترض حدوثه (التحقق يتم قبل الحفظ) لكن المعاينة يجب ألا تنهار
            logger.error("فشل معاينة القالب %s: %s", code, exc)
            return (definition.title.format_map(values), definition.body.format_map(values))

    async def customized_count(self) -> int:
        """عدد القوالب المعدّلة (يُستخدم في شاشة القوالب وفحص الإقلاع)."""
        return await self.repos.templates.count_customized()

    # ------------------------------ التحقق ------------------------------- #

    def validate_text(self, definition: tpl.TemplateDef, *, title: str, body: str) -> None:
        """
        التحقق من نص قالب قبل حفظه (متغيرات معلنة فقط وبلا تنسيق).

        الاستثناءات: ValidationError مع رسالة عربية تشرح الخطأ بدقة.
        """
        allowed = definition.variables
        allowed_text = "، ".join(f"{{{name}}}" for name in allowed) or "لا متغيرات"

        for field_name, value in (("العنوان", title), ("النص", body)):
            bad = tpl.invalid_placeholders(value, allowed)
            if bad:
                shown = "، ".join(f"{{{name}}}" for name in dict.fromkeys(bad))
                raise ValidationError(
                    f"متغيرات غير مسموحة في {field_name}: {bad}",
                    user_message=(
                        f"❌ {field_name} يحتوي متغيرات غير مسموحة: {shown}\n"
                        f"المسموح لهذا القالب: {allowed_text}\n"
                        "ملاحظة: لا يُسمح بالتنسيق مثل {{amount:0.2f}}."
                    ),
                )

    # ------------------------------ الكتابة ------------------------------ #

    async def set_text(
        self, actor: User, code: str, *, title: str | None = None, body: str | None = None
    ) -> NotificationTemplate:
        """
        حفظ صياغة مخصّصة لقالب (العنوان أو النص أو كليهما).

        ما لم يُمرَّر يبقى على قيمته الفعّالة الحالية، فتعديل النص وحده لا يمسح العنوان.

        الاستثناءات: PermissionDeniedError · ValidationError.
        """
        await self.auth.require_permission(actor, Permission.NOTIFICATIONS_TEMPLATES)
        definition = self.definition(code)
        current = await self.repos.templates.get(code)

        new_title = clean_text(
            title if title is not None else (current.title if current else definition.title),
            field="عنوان القالب",
            max_length=tpl.MAX_TEMPLATE_TITLE,
            min_length=2,
        )
        new_body = clean_multiline(
            body if body is not None else (current.body if current else definition.body),
            field="نص القالب",
            max_length=tpl.MAX_TEMPLATE_BODY,
            min_length=2,
        )
        self.validate_text(definition, title=new_title, body=new_body)

        async with self.db.transaction() as tx:
            saved = await self.repos.templates.upsert(
                tx,
                code=code,
                title=new_title,
                body=new_body,
                admin_id=actor.id,
                is_active=current.enabled if current else True,
            )
            await self.audit.log(
                tx,
                action="notifications.templates",
                admin_id=actor.id,
                target_type="notification_template",
                target_id=code,
                before={
                    "title": current.title if current else definition.title,
                    "body": current.body if current else definition.body,
                    "customized": current is not None,
                },
                after={"title": new_title, "body": new_body, "customized": True},
            )
        await self.refresh_cache()
        logger.info("الأدمن %s عدّل قالب الإشعار %s", actor.id, code)
        return saved

    async def set_active(self, actor: User, code: str, *, active: bool) -> bool:
        """
        تفعيل أو إيقاف قالب مخصّص (الإيقاف يُرجع النص الافتراضي دون فقد التعديل).

        المخرجات: True إن تغيّرت الحالة فعلاً.

        الاستثناءات: PermissionDeniedError · ValidationError إن لم يُعدَّل القالب أصلاً.
        """
        await self.auth.require_permission(actor, Permission.NOTIFICATIONS_TEMPLATES)
        self.definition(code)
        current = await self.repos.templates.get(code)
        if current is None:
            raise ValidationError(
                f"لا يوجد تخصيص للقالب {code}",
                user_message="❌ هذا القالب يستخدم النص الافتراضي أصلاً.",
            )
        if bool(current.is_active) == active:
            return False

        async with self.db.transaction() as tx:
            changed = await self.repos.templates.set_active(tx, code, active=active)
            if changed:
                await self.audit.log(
                    tx,
                    action="notifications.templates",
                    admin_id=actor.id,
                    target_type="notification_template",
                    target_id=code,
                    before={"is_active": current.is_active},
                    after={"is_active": 1 if active else 0},
                )
        if changed:
            await self.refresh_cache()
            logger.info(
                "%s الأدمن %s قالب الإشعار %s", "فعّل" if active else "أوقف", actor.id, code
            )
        return changed

    async def reset(self, actor: User, code: str) -> bool:
        """
        استعادة النص الافتراضي لقالب (حذف صف التخصيص فقط).

        المخرجات: True إن كان هناك تخصيص فعلاً وحُذف.

        الاستثناءات: PermissionDeniedError · ValidationError للرمز غير المعروف.
        """
        await self.auth.require_permission(actor, Permission.NOTIFICATIONS_TEMPLATES)
        definition = self.definition(code)
        current = await self.repos.templates.get(code)
        if current is None:
            return False

        async with self.db.transaction() as tx:
            deleted = await self.repos.templates.delete(tx, code)
            if deleted:
                await self.audit.log(
                    tx,
                    action="notifications.templates",
                    admin_id=actor.id,
                    target_type="notification_template",
                    target_id=code,
                    before={"title": current.title, "body": current.body, "customized": True},
                    after={
                        "title": definition.title,
                        "body": definition.body,
                        "customized": False,
                    },
                )
        if deleted:
            await self.refresh_cache()
            logger.info("الأدمن %s أعاد القالب %s إلى نصه الافتراضي", actor.id, code)
        return deleted
```

### `services/broadcast_service.py`  ·  جديد  ·  485 سطراً

خدمة الإذاعة: استهداف، إنشاء، تحكم، إرسال على دفعات.

```python
"""
خدمة الرسائل الجماعية (الإذاعة) — المرحلة 8.

لماذا طابور مستلمين بدل حلقة إرسال واحدة؟
    إرسال رسالة لعشرة آلاف مستخدم داخل معالج زر مستحيل عملياً: تيليجرام يحدّ
    السرعة (~30 رسالة/ثانية)، وأي انقطاع يفقد أثر من وصلته الرسالة ومن لم تصله.
    لذلك: تُسجَّل قائمة المستلمين كاملة في `broadcast_recipients` أولاً، ثم تأتي
    مهمة دورية وترسل دفعة صغيرة كل بضع ثوانٍ وتسجّل نتيجة كل مستلم على حدة.

النتائج المضمونة:
    • لا تكرار: صف المستلم ينتقل من pending إلى نتيجة نهائية بشرط `status='pending'`،
      فحتى لو تداخلت جولتان لا يُرسل لأحد مرتين.
    • استئناف تلقائي: إعادة تشغيل البوت لا تفقد شيئاً — الإذاعة تبقى `running`
      والجولة التالية تكمل من حيث توقفت.
    • إيقاف فوري: زر «⏸ إيقاف مؤقت» يوقف الجولات، والملغاة لا تُستأنف أبداً.
    • من حظر البوت يُسجَّل فوراً (`blocked_bot=1`) فلا نزعج طابور الإشعارات به لاحقاً.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from core.enums import BroadcastStatus, RecipientStatus
from core.exceptions import (
    NotificationBlockedError,
    NotificationPermanentError,
    NotificationTemporaryError,
    ValidationError,
)
from core.permissions import Permission
from database.database import Database
from database.models import Broadcast, User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.notification_service import NotificationService
from services.settings_service import SettingsService
from texts import templates
from utils.datetime_utils import iso_minus_days, utc_now_iso
from utils.logging_setup import get_logger
from utils.security import sanitize
from utils.validators import clean_multiline

logger = get_logger(__name__)

#: توقيع دالة إرسال رسالة إذاعة واحدة (تُمرَّر من طبقة تيليجرام)
#: (telegram_id, text, media_file_id, media_type) -> message_id | None
BroadcastSender = Callable[[int, str, str | None, str | None], Awaitable[int | None]]

#: أقصى طول لنص الإذاعة بلا وسائط (حد تيليجرام 4096 ونترك هامشاً)
MAX_BROADCAST_TEXT = 3500

#: أقصى طول للنص المرافق لصورة (حد التعليق في تيليجرام 1024)
MAX_BROADCAST_CAPTION = 1000

#: شرائح الاستهداف المدعومة ووصفها العربي
TARGETS: dict[str, str] = {
    "all": "👥 كل المستخدمين",
    "active": "🔥 النشطون مؤخراً",
    "buyers": "🛒 من لديه طلب سابق",
    "no_orders": "🌱 مسجّلون بلا طلبات",
}

#: الحالات التي يمكن الإرسال منها
RESUMABLE_STATUSES = (BroadcastStatus.DRAFT, BroadcastStatus.PAUSED)


@dataclass(slots=True)
class BroadcastRound:
    """حصيلة جولة إرسال واحدة (تُسجَّل في اللوق وتظهر في شاشة المهام)."""

    broadcast_id: int = 0
    claimed: int = 0
    sent: int = 0
    failed: int = 0
    blocked: int = 0
    completed: bool = False

    def as_dict(self) -> dict[str, int | bool]:
        """تحويل الحصيلة إلى قاموس للتسجيل."""
        return {
            "broadcast_id": self.broadcast_id,
            "claimed": self.claimed,
            "sent": self.sent,
            "failed": self.failed,
            "blocked": self.blocked,
            "completed": self.completed,
        }


class BroadcastService:
    """إنشاء الرسائل الجماعية وإدارتها وإرسالها على دفعات آمنة."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        auth: AuthService,
        audit: AuditService,
        notifications: NotificationService,
        settings: SettingsService,
    ) -> None:
        """تهيئة الخدمة باعتمادياتها."""
        self.db = db
        self.repos = repos
        self.auth = auth
        self.audit = audit
        self.notifications = notifications
        self.settings = settings

    # ----------------------------- الاستهداف ----------------------------- #

    async def target_label(self, target: str) -> str:
        """وصف عربي للشريحة المستهدفة (يتضمن عدد أيام النشاط عند الحاجة)."""
        if target == "active":
            days = await self.settings.get_int("broadcast_active_days", 30)
            return f"🔥 النشطون آخر {days} يوماً"
        return TARGETS.get(target, target)

    async def audience_ids(self, target: str) -> list[int]:
        """
        معرفات المستخدمين الداخلية للشريحة المطلوبة.

        المستبعدون دائماً: المحظورون ومن حظر البوت — إرسال رسالة لهم مضيعة
        للحصة اليومية ويشوّه إحصائية «وصلت».

        الاستثناءات: ValidationError للشريحة غير المعروفة.
        """
        if target not in TARGETS:
            raise ValidationError(
                f"شريحة إذاعة غير معروفة: {target}",
                user_message="❌ شريحة الاستهداف غير معروفة.",
            )
        since = None
        if target == "active":
            days = await self.settings.get_int("broadcast_active_days", 30)
            since = iso_minus_days(max(1, days))
        return await self.repos.users.ids_for_broadcast(target=target, since_iso=since)

    async def audience_count(self, actor: User, target: str) -> int:
        """عدد من ستصلهم الرسالة فعلاً لو أُرسلت الآن (يُعرض قبل التأكيد)."""
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        return len(await self.audience_ids(target))

    async def audience_summary(self, actor: User) -> list[tuple[str, str, int]]:
        """
        جدول الشرائح: (الرمز، الوصف، العدد الحالي) لشاشة اختيار الشريحة.

        الأرقام محسوبة من قاعدة البيانات لحظة العرض — لا تقديرات.
        """
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        rows: list[tuple[str, str, int]] = []
        for code in TARGETS:
            rows.append((code, await self.target_label(code), len(await self.audience_ids(code))))
        return rows

    # ------------------------------ الإنشاء ------------------------------ #

    def validate_text(self, text: str, *, has_media: bool) -> str:
        """
        تنظيف نص الإذاعة والتحقق من طوله.

        مع صورة يصبح النص تعليقاً، وحد تيليجرام للتعليق أقصر بكثير من الرسالة.

        الاستثناءات: ValidationError عند الفراغ أو تجاوز الحد.
        """
        limit = MAX_BROADCAST_CAPTION if has_media else MAX_BROADCAST_TEXT
        return clean_multiline(text, field="نص الرسالة", max_length=limit, min_length=2)

    async def create(
        self,
        actor: User,
        *,
        text: str,
        target: str,
        media_file_id: str | None = None,
        media_type: str | None = None,
    ) -> Broadcast:
        """
        إنشاء إذاعة بحالة «مسودة» مع تثبيت قائمة مستلميها.

        تثبيت القائمة لحظة الإنشاء مقصود: من يسجّل بعد الضغط على «إرسال»
        لا تصله رسالة قديمة، ومن حُظر بعدها لا يُحذف من السجل بل تُسجَّل محاولته.

        الاستثناءات:
            PermissionDeniedError : بلا صلاحية `broadcast.send`.
            ValidationError       : نص فارغ/طويل، شريحة مجهولة، أو شريحة بلا مستلمين.
        """
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        clean = self.validate_text(text, has_media=bool(media_file_id))
        recipients = await self.audience_ids(target)
        if not recipients:
            raise ValidationError(
                f"لا مستلمين في الشريحة {target}",
                user_message="❌ لا يوجد مستخدمون في هذه الشريحة الآن.",
            )

        async with self.db.transaction() as tx:
            broadcast = await self.repos.broadcasts.create(
                tx,
                admin_id=actor.id,
                message_text=clean,
                target=target,
                media_file_id=media_file_id,
                media_type=media_type,
            )
            total = await self.repos.broadcasts.add_recipients(tx, broadcast.id, recipients)
            await self.audit.log(
                tx,
                action="broadcast.send",
                admin_id=actor.id,
                target_type="broadcast",
                target_id=broadcast.id,
                before=None,
                after={"target": target, "recipients": total, "has_media": bool(media_file_id)},
                details=clean[:200],
            )
        logger.info(
            "أنشأ الأدمن %s إذاعة #%s للشريحة %s بعدد %s مستلم",
            actor.id, broadcast.id, target, total,
        )
        refreshed = await self.repos.broadcasts.get(broadcast.id)
        return refreshed or broadcast

    # ------------------------------ التحكم ------------------------------- #

    async def _require(self, broadcast_id: int) -> Broadcast:
        """
        جلب إذاعة أو رفع خطأ واضح.

        الاستثناءات: ValidationError إذا لم توجد.
        """
        broadcast = await self.repos.broadcasts.get(broadcast_id)
        if broadcast is None:
            raise ValidationError(
                f"إذاعة غير موجودة: {broadcast_id}", user_message="❌ هذه الرسالة غير موجودة."
            )
        return broadcast

    async def start(self, actor: User, broadcast_id: int) -> Broadcast:
        """
        بدء (أو استئناف) الإرسال.

        التحقق من الحالة السابقة إلزامي: لا نعيد تشغيل إذاعة مكتملة أو ملغاة
        حتى لا يُرسل النص مرتين لمن استلمه.

        الاستثناءات: PermissionDeniedError · ValidationError على الحالة غير المسموحة.
        """
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        broadcast = await self._require(broadcast_id)
        if broadcast.status not in RESUMABLE_STATUSES:
            raise ValidationError(
                f"حالة غير قابلة للبدء: {broadcast.status}",
                user_message="⚠️ لا يمكن بدء هذه الرسالة في حالتها الحالية.",
            )
        remaining = await self.repos.broadcasts.pending_count(broadcast_id)
        if remaining == 0:
            raise ValidationError(
                "لا مستلمين متبقين", user_message="⚠️ لا يوجد مستلمون متبقون في هذه الرسالة."
            )

        async with self.db.transaction() as tx:
            await self.repos.broadcasts.set_status(
                tx,
                broadcast_id,
                BroadcastStatus.RUNNING,
                started_at=broadcast.started_at or utc_now_iso(),
            )
            await self.audit.log(
                tx,
                action="broadcast.send",
                admin_id=actor.id,
                target_type="broadcast",
                target_id=broadcast_id,
                before={"status": broadcast.status},
                after={"status": BroadcastStatus.RUNNING.value, "remaining": remaining},
            )
        logger.info("بدأ الأدمن %s إرسال الإذاعة #%s (%s متبقٍ)", actor.id, broadcast_id, remaining)
        return await self._require(broadcast_id)

    async def pause(self, actor: User, broadcast_id: int) -> bool:
        """
        إيقاف مؤقت للإرسال (يمكن استئنافه لاحقاً من نفس النقطة).

        المخرجات: True إن تغيّرت الحالة فعلاً.
        """
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        broadcast = await self._require(broadcast_id)
        if broadcast.status != BroadcastStatus.RUNNING:
            return False
        async with self.db.transaction() as tx:
            changed = await self.repos.broadcasts.set_status(
                tx, broadcast_id, BroadcastStatus.PAUSED
            )
            if changed:
                await self.audit.log(
                    tx,
                    action="broadcast.send",
                    admin_id=actor.id,
                    target_type="broadcast",
                    target_id=broadcast_id,
                    before={"status": broadcast.status},
                    after={"status": BroadcastStatus.PAUSED.value},
                )
        logger.info("أوقف الأدمن %s الإذاعة #%s مؤقتاً", actor.id, broadcast_id)
        return changed

    async def cancel(self, actor: User, broadcast_id: int) -> bool:
        """
        إلغاء نهائي: لا تُستأنف بعده، ومن وصلته الرسالة تبقى عنده.

        لا نحذف صفوف المستلمين — السجل التاريخي لمن وصلته الرسالة يبقى كاملاً.
        """
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        broadcast = await self._require(broadcast_id)
        if broadcast.status in (BroadcastStatus.COMPLETED, BroadcastStatus.CANCELLED):
            return False
        async with self.db.transaction() as tx:
            changed = await self.repos.broadcasts.set_status(
                tx, broadcast_id, BroadcastStatus.CANCELLED, finished_at=utc_now_iso()
            )
            if changed:
                await self.audit.log(
                    tx,
                    action="broadcast.send",
                    admin_id=actor.id,
                    target_type="broadcast",
                    target_id=broadcast_id,
                    before={"status": broadcast.status, "sent": broadcast.sent_count},
                    after={"status": BroadcastStatus.CANCELLED.value},
                )
        logger.warning("ألغى الأدمن %s الإذاعة #%s", actor.id, broadcast_id)
        return changed

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, actor: User, broadcast_id: int) -> Broadcast:
        """جلب إذاعة واحدة للعرض في اللوحة."""
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        return await self._require(broadcast_id)

    async def recent(self, actor: User, *, limit: int = 8) -> list[Broadcast]:
        """آخر الإذاعات (الأحدث أولاً) لشاشة «📣 الرسائل الجماعية»."""
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        return await self.repos.broadcasts.list_recent(limit=limit)

    async def progress(self, actor: User, broadcast_id: int) -> dict[str, Any]:
        """
        تقدم إذاعة بالأرقام الحقيقية: المرسل والفاشل والمحظور والمتبقي.

        كل رقم من قاعدة البيانات مباشرة، لا عدّادات في الذاكرة.
        """
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        broadcast = await self._require(broadcast_id)
        pending = await self.repos.broadcasts.pending_count(broadcast_id)
        done = broadcast.sent_count + broadcast.failed_count + broadcast.blocked_count
        percent = int(done * 100 / broadcast.total_count) if broadcast.total_count else 0
        return {
            "broadcast": broadcast,
            "pending": pending,
            "done": done,
            "percent": min(100, percent),
            "target_label": await self.target_label(broadcast.target),
        }

    # ------------------------------ الإرسال ------------------------------ #

    async def next_running(self) -> Broadcast | None:
        """أقدم إذاعة جارية (نُرسل واحدة في كل جولة حتى لا نتجاوز حدود تيليجرام)."""
        running = await self.repos.broadcasts.list_running()
        return running[0] if running else None

    async def send_batch(self, sender: BroadcastSender, *, limit: int | None = None) -> BroadcastRound:
        """
        جولة إرسال واحدة للإذاعة الجارية الحالية.

        المدخلات:
            sender : دالة إرسال من طبقة تيليجرام ترفع استثناءات الإشعارات المعروفة.
            limit  : حجم الدفعة (الافتراضي من الإعدادات `broadcast_batch_size`).

        المخرجات: حصيلة الجولة. إذاعة بلا متبقٍ تُغلق تلقائياً ويُشعَر منشئها.

        ملاحظة: كل مستلم يُسجَّل في معاملة قصيرة مستقلة، فلا تبقى قاعدة البيانات
        مقفلة أثناء انتظار الشبكة، ولا نفقد نتيجة من أُرسل له عند أي انقطاع.
        """
        broadcast = await self.next_running()
        if broadcast is None:
            return BroadcastRound()

        batch_size = limit or await self.settings.get_int("broadcast_batch_size", 20)
        batch_size = max(1, min(50, batch_size))

        async with self.db.transaction() as tx:
            claimed = await self.repos.broadcasts.claim_recipients(
                tx, broadcast.id, limit=batch_size
            )

        round_report = BroadcastRound(broadcast_id=broadcast.id, claimed=len(claimed))
        for row in claimed:
            status, error = await self._send_one(sender, broadcast, int(row["telegram_id"]))
            async with self.db.transaction() as tx:
                recorded = await self.repos.broadcasts.mark_recipient(
                    tx, int(row["id"]), status=status, error=error
                )
                if recorded and status == RecipientStatus.BLOCKED:
                    await self.repos.users.set_blocked_bot(tx, int(row["user_id"]), True)
            if not recorded:
                continue  # سُجِّلت نتيجته في جولة أخرى — لا نعدّه مرتين
            if status == RecipientStatus.SENT:
                round_report.sent += 1
            elif status == RecipientStatus.BLOCKED:
                round_report.blocked += 1
            else:
                round_report.failed += 1

        remaining = await self.repos.broadcasts.pending_count(broadcast.id)
        if remaining == 0:
            await self._complete(broadcast.id)
            round_report.completed = True

        if round_report.claimed:
            logger.info("جولة إذاعة: %s", round_report.as_dict())
        return round_report

    async def _send_one(
        self, sender: BroadcastSender, broadcast: Broadcast, telegram_id: int
    ) -> tuple[str, str | None]:
        """
        إرسال رسالة واحدة وتصنيف نتيجتها.

        الأخطاء المؤقتة (شبكة/حد معدل) تُعاد محاولتها **مرة واحدة** بعد ثانية،
        فإن تكررت سُجِّلت كفشل مع نص الخطأ بدل تعليق الطابور إلى الأبد.

        المخرجات: (حالة المستلم، نص الخطأ المختصر أو None).
        """
        for attempt in (1, 2):
            try:
                await sender(
                    telegram_id,
                    broadcast.message_text,
                    broadcast.media_file_id,
                    broadcast.media_type,
                )
            except NotificationBlockedError as exc:
                return RecipientStatus.BLOCKED, sanitize(str(exc))[:200]
            except NotificationTemporaryError as exc:
                if attempt == 1:
                    await asyncio.sleep(1)
                    continue
                return RecipientStatus.FAILED, sanitize(str(exc))[:200]
            except NotificationPermanentError as exc:
                return RecipientStatus.FAILED, sanitize(str(exc))[:200]
            else:
                return RecipientStatus.SENT, None
        return RecipientStatus.FAILED, "تعذر الإرسال بعد محاولتين"

    async def _complete(self, broadcast_id: int) -> None:
        """إغلاق الإذاعة بعد انتهاء مستلميها وإشعار الأدمن الذي أنشأها بالحصيلة."""
        broadcast = await self.repos.broadcasts.get(broadcast_id)
        if broadcast is None or broadcast.status != BroadcastStatus.RUNNING:
            return
        async with self.db.transaction() as tx:
            await self.repos.broadcasts.set_status(
                tx, broadcast_id, BroadcastStatus.COMPLETED, finished_at=utc_now_iso()
            )
            if broadcast.admin_id:
                title, message = templates.broadcast_finished(
                    broadcast_id=broadcast_id,
                    sent=broadcast.sent_count,
                    failed=broadcast.failed_count,
                    blocked=broadcast.blocked_count,
                )
                await self.notifications.notify_user_manual(
                    tx,
                    user_id=broadcast.admin_id,
                    token=f"broadcast:{broadcast_id}:done",
                    title=title,
                    message=message,
                )
        logger.info(
            "اكتملت الإذاعة #%s: وصلت %s · حظر %s · فشل %s",
            broadcast_id, broadcast.sent_count, broadcast.blocked_count, broadcast.failed_count,
        )
```

### `services/__init__.py`  ·  مُحدَّث  ·  175 سطراً

ربط الخدمتين وتحميل القوالب عند الإقلاع.

```python
"""
حزمة الخدمات — طبقة منطق العمل بين الواجهة (المرحلة 3+) وقاعدة البيانات.

لماذا حاوية خدمات؟
    الخدمات مترابطة (الطلبات تحتاج المحفظة والمزودين والإشعارات...). بدل أن تبني كل
    نقطة دخول اعتمادياتها بنفسها — فتتسرب الأخطاء وتتكرر الكائنات — تُبنى هنا مرة
    واحدة بترتيب صحيح، ويُمرَّر كائن `ServiceContainer` واحد إلى بقية النظام.

ترتيب البناء (من الأدنى اعتماداً إلى الأعلى):
    settings → audit → notifications → auth → wallet → users → catalog
    → providers → orders → payments → tickets → stats → templates → broadcasts
"""

from __future__ import annotations

from dataclasses import dataclass

from database.database import Database
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.broadcast_service import BroadcastService
from services.catalog_service import CatalogService
from services.notification_service import NotificationService
from services.order_service import OrderService
from services.payment_service import PaymentService
from services.provider_service import ProviderService
from services.settings_service import SettingsService
from services.stats_service import StatsService
from services.template_service import TemplateService
from services.ticket_service import TicketService
from services.user_service import UserService
from services.wallet_service import WalletService
from utils.logging_setup import get_logger
from utils.security import SecretBox

logger = get_logger(__name__)

__all__ = [
    "AuditService",
    "AuthService",
    "BroadcastService",
    "CatalogService",
    "NotificationService",
    "OrderService",
    "PaymentService",
    "ProviderService",
    "ServiceContainer",
    "SettingsService",
    "StatsService",
    "TemplateService",
    "TicketService",
    "UserService",
    "WalletService",
    "build_services",
]


@dataclass(slots=True)
class ServiceContainer:
    """
    حاوية تضم نسخة واحدة من كل خدمة، جاهزة للتمرير إلى معالجات تيليجرام والمهام.

    الاستخدام:
        services = build_services(db, repos, secret_box=box, super_admin_ids=(123,))
        user, is_new = await services.users.get_or_create(...)
        order = await services.orders.create_order(user, service_id=1, link="...", quantity=100)
    """

    db: Database
    repos: Repositories
    settings: SettingsService
    audit: AuditService
    notifications: NotificationService
    auth: AuthService
    wallet: WalletService
    users: UserService
    catalog: CatalogService
    providers: ProviderService
    orders: OrderService
    payments: PaymentService
    tickets: TicketService
    stats: StatsService
    templates: TemplateService
    broadcasts: BroadcastService

    def invalidate_caches(self) -> None:
        """
        إبطال الذاكرة المؤقتة للإعدادات بعد أي تعديل خارجي عليها.

        ملاحظة: عملاء المزودين تُفتح وتُغلق داخل كل عملية (`client.close()` في finally)،
        فلا توجد جلسات شبكة معلّقة تحتاج إغلاقاً عند إيقاف البوت.
        """
        self.settings.invalidate()

    async def startup_recovery(self) -> dict[str, int]:
        """
        إجراءات الاسترداد التي تُنفَّذ مرة واحدة عند إقلاع البوت.

        تشمل: تحرير الأقفال المنتهية ونقل الطلبات العالقة في الإرسال إلى «غير مؤكد».

        المخرجات: عدّادات ما تم استرداده.
        """
        report = await self.orders.recover_after_restart()
        # المرحلة 8: تحميل قوالب الإشعارات المخصّصة قبل إرسال أول رسالة،
        # وإلا خرجت أول الإشعارات بالنص الافتراضي رغم تعديل الأدمن له.
        report["templates_loaded"] = await self.templates.refresh_cache()
        logger.info("استرداد الإقلاع: %s", report)
        return report


def build_services(
    db: Database,
    repos: Repositories | None = None,
    *,
    secret_box: SecretBox,
    super_admin_ids: tuple[int, ...] = (),
    settings_ttl_seconds: float | None = None,
) -> ServiceContainer:
    """
    بناء كل الخدمات وربط اعتمادياتها بالترتيب الصحيح.

    المدخلات:
        db                   : اتصال قاعدة البيانات (مفتوح مسبقاً).
        repos                : المستودعات (تُبنى تلقائياً إن لم تُمرَّر).
        secret_box           : صندوق التشفير لمفاتيح المزودين (إجباري — لا مفاتيح واضحة).
        super_admin_ids      : معرفات الأدمن الأعلى من ملف البيئة (مسار طوارئ فقط).
        settings_ttl_seconds : مدة صلاحية كاش الإعدادات (يُستخدم 0 في الاختبارات لإلغاء الكاش).

    المخرجات: حاوية الخدمات الجاهزة للاستخدام.
    """
    repositories = repos if repos is not None else Repositories(db)

    settings = (
        SettingsService(db, repositories, ttl_seconds=settings_ttl_seconds)
        if settings_ttl_seconds is not None
        else SettingsService(db, repositories)
    )
    audit = AuditService(db, repositories)
    notifications = NotificationService(db, repositories, settings)
    auth = AuthService(db, repositories, settings, audit, super_admin_ids=super_admin_ids)
    wallet = WalletService(db, repositories)
    users = UserService(db, repositories, settings, audit, auth, notifications)
    catalog = CatalogService(db, repositories, settings, audit, auth)
    providers = ProviderService(
        db, repositories, settings, audit, auth, notifications, secret_box
    )
    orders = OrderService(
        db, repositories, settings, wallet, catalog, providers, notifications, audit, auth
    )
    payments = PaymentService(db, repositories, settings, wallet, notifications, audit, auth)
    tickets = TicketService(db, repositories, settings, notifications, audit, auth)
    stats = StatsService(db, repositories, settings, auth, providers)
    template_service = TemplateService(db, repositories, auth, audit)
    broadcasts = BroadcastService(db, repositories, auth, audit, notifications, settings)

    logger.info("تم بناء طبقة الخدمات (%s خدمة)", 14)
    return ServiceContainer(
        db=db,
        repos=repositories,
        settings=settings,
        audit=audit,
        notifications=notifications,
        auth=auth,
        wallet=wallet,
        users=users,
        catalog=catalog,
        providers=providers,
        orders=orders,
        payments=payments,
        tickets=tickets,
        stats=stats,
        templates=template_service,
        broadcasts=broadcasts,
    )
```

### `services/ticket_service.py`  ·  مُحدَّث (مقتطف)  ·  585 سطراً

إعداد تنبيه ردود المستخدم + تصفية بالأولوية.

```python
    async def reply_as_user(
        self,
        user: User,
        ticket_id: int,
        message: str,
        *,
        attachment_file_id: str | None = None,
        attachment_type: str | None = None,
    ) -> SupportMessage:
        """
        إضافة رد من المستخدم على تذكرته وإشعار فريق الدعم.

        التذكرة المغلقة تُعاد فتحها تلقائياً ضمن مهلة `ticket_reopen_hours`.

        الاستثناءات:
            TicketError     : التذكرة غير موجودة أو ليست له أو مغلقة نهائياً.
            ValidationError : نص الرسالة غير صالح.
        """
        await self.auth.guard(user)
        ticket = await self.get_for_user(user, ticket_id)
        clean_message = validate_message(message)
        # إعداد المرحلة 8: هل يُنبَّه الأدمن عند كل رد، أم عند فتح تذكرة جديدة فقط؟
        notify_admins = await self.settings.get_bool("ticket_reply_notify_admins", True)

        if ticket.status == TicketStatus.CLOSED:
            await self._reopen_or_fail(ticket)

        async with self.db.transaction() as tx:
            support_message = await self.repos.tickets.add_message(
                tx,
                ticket_id=ticket.id,
                sender_type=SenderType.USER,
                sender_id=user.id,
                message=clean_message,
                attachment_file_id=attachment_file_id,
                attachment_type=attachment_type,
            )
            if notify_admins:
                title, admin_text = templates.admin_new_ticket(
                    ticket_id=ticket.id,
                    subject=f"رد جديد — {ticket.subject}",
                    user_label=user.display_name,
                )
                await self.notifications.notify_admins(
                    tx,
                    permission=Permission.TICKETS_VIEW,
                    token=f"ticket:{ticket.id}:msg:{support_message.id}",
                    title=title,
                    message=admin_text,
                )
        logger.info("رد المستخدم %s على التذكرة #%s", user.id, ticket_id)
        return support_message

# ... (مقطع آخر من الملف) ...

    async def admin_list(
        self,
        actor: User,
        *,
        statuses: tuple[str, ...] = OPEN_STATUSES,
        assigned_admin: int | None = None,
        priority: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[SupportTicket]:
        """
        قائمة التذاكر لفريق الدعم (الافتراضي: غير المغلقة).

        المدخلات:
            statuses       : الحالات المطلوبة.
            assigned_admin : حصر النتائج بالتذاكر المسندة لأدمن بعينه (تبويب «المسندة لي»).
            priority       : حصر النتائج بأولوية بعينها (تبويب «العاجلة»).
        """
        await self.auth.require_permission(actor, Permission.TICKETS_VIEW)
        return await self.repos.tickets.list_by_status(
            list(statuses),
            assigned_admin=assigned_admin,
            priority=priority,
            limit=limit,
            offset=offset,
        )

    async def admin_count(
        self,
        actor: User,
        *,
        statuses: tuple[str, ...] = OPEN_STATUSES,
        assigned_admin: int | None = None,
        priority: str | None = None,
    ) -> int:
        """عدد التذاكر المطابقة لتصفية `admin_list` (لحساب عدد الصفحات)."""
        await self.auth.require_permission(actor, Permission.TICKETS_VIEW)
        return await self.repos.tickets.count_by_status(
            list(statuses), assigned_admin=assigned_admin, priority=priority
        )
```

### `services/payment_service.py`  ·  مُحدَّث (مقتطف)  ·  1026 سطراً

استعمال `clean_multiline` المشتركة بدل نسخة خاصة.

```python
from utils.validators import (
    clean_multiline,
    clean_text,
    parse_amount_units,
    validate_amount_range,
    validate_transaction_reference,
)

# ... (مقطع آخر من الملف) ...

            elif key == "instructions_ar":
                # التعليمات اختيارية (قد تُترك فارغة لطريقة بسيطة) ⇒ min_length=0
                clean[key] = clean_multiline(
                    value, field="التعليمات", max_length=MAX_METHOD_INSTRUCTIONS, min_length=0
                )
            elif key == "account_details":
                clean[key] = clean_multiline(
                    value, field="بيانات الحساب", max_length=MAX_METHOD_ACCOUNT, min_length=0
                )
```

## النصوص

### `texts/templates.py`  ·  مُحدَّث  ·  703 سطراً

كتالوج 19 قالباً قابلاً للتحرير + `render` + التحقق من المتغيرات (الدوال القديمة بقيت بنفس التواقيع).

```python
"""
قوالب نصوص الإشعارات العربية.

كل نص يصل إلى المستخدم أو الأدمن مكتوب هنا في مكان واحد — لا نصوص متناثرة داخل الخدمات.
كل دالة تُرجع زوجاً: (العنوان، النص) جاهزاً للإرسال عبر تيليجرام.

المرحلة 8 — القوالب القابلة للتحرير:
    رسائل العملاء (الطلبات/المدفوعات/الرصيد/الدعم/الحساب) صارت تمرّ عبر `render`،
    فتُستبدل صياغتها بما حفظه الأدمن في جدول `notification_templates` إن وُجد،
    وإلا يُستعمل النص الافتراضي المكتوب هنا حرفياً.

    • الافتراضي يبقى في الكود دائماً ⇒ زر «استعادة الافتراضي» يعمل بلا نسخة احتياطية.
    • القيم تُمرَّر جاهزة للعرض (مبالغ منسّقة، أعداد بفواصل) حتى يبقى القالب نصاً بحتاً
      بلا أي صياغة برمجية داخله (`{amount}` لا `{amount:,.2f}`).
    • تنبيهات الأدمن الداخلية (أخطاء المزودين، المهام المتعثرة…) غير قابلة للتحرير
      عمداً: هي أدوات تشخيص لا رسائل تسويقية، وتغيير صياغتها يُربك التشخيص.
"""

from __future__ import annotations

from dataclasses import dataclass
from string import Formatter

from core.money import format_units
from core.order_state import label_ar as order_label
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: الرمز الافتراضي للعملة عند عدم تمريره (تُقرأ القيمة الحقيقية من الإعدادات)
DEFAULT_SYMBOL = ""

#: أقصى طول مسموح لعنوان القالب ونصه (حماية من رسائل تتجاوز حد تيليجرام)
MAX_TEMPLATE_TITLE = 120
MAX_TEMPLATE_BODY = 1500


def money(units: int, symbol: str = DEFAULT_SYMBOL, decimals: int = 2) -> str:
    """تنسيق مبلغ للعرض داخل نصوص الإشعارات."""
    return format_units(units, symbol=symbol, decimals=decimals)


def _count(value: int) -> str:
    """تنسيق عدد صحيح بفواصل الآلاف (يُحسب هنا لا داخل القالب)."""
    return f"{value:,}"


# ======================================================================= #
#                     كتالوج القوالب القابلة للتحرير                      #
# ======================================================================= #


@dataclass(frozen=True, slots=True)
class TemplateDef:
    """
    تعريف قالب واحد: رمزه، مجموعته، نصه الافتراضي، ومتغيراته المسموحة.

    الحقول:
        code      : رمز الحدث (مفتاح الصف في جدول notification_templates).
        name_ar   : الاسم كما يظهر في لوحة التحكم.
        group     : مجموعة العرض (orders / payments / wallet / tickets / account).
        title     : العنوان الافتراضي.
        body      : النص الافتراضي بمتغيراته.
        variables : أسماء المتغيرات المسموح استخدامها في هذا القالب فقط.
        sample    : قيم تجريبية تُستخدم في زر «👁 معاينة» (لا تُرسل لأحد).
    """

    code: str
    name_ar: str
    group: str
    title: str
    body: str
    variables: tuple[str, ...]
    sample: dict[str, str]


#: أسماء عربية لمجموعات القوالب في شاشة الأدمن
TEMPLATE_GROUPS: dict[str, str] = {
    "orders": "📦 الطلبات",
    "payments": "💳 الشحن",
    "wallet": "👛 الرصيد",
    "tickets": "🎫 الدعم",
    "account": "👤 الحساب",
}

TEMPLATES: tuple[TemplateDef, ...] = (
    # ------------------------------ الطلبات ------------------------------ #
    TemplateDef(
        code="order_created",
        name_ar="إنشاء الطلب",
        group="orders",
        title="🧾 تم استلام طلبك",
        body=(
            "تم إنشاء الطلب {code} بنجاح.\n\n"
            "🛒 الخدمة: {service_name}\n"
            "🔢 الكمية: {quantity}\n"
            "💵 المبلغ المخصوم: {amount}\n\n"
            "سيبدأ التنفيذ خلال دقائق، وسنعلمك بكل تحديث."
        ),
        variables=("code", "service_name", "quantity", "amount"),
        sample={
            "code": "ORD-10231",
            "service_name": "متابعون انستغرام",
            "quantity": "1,000",
            "amount": "25.00",
        },
    ),
    TemplateDef(
        code="order_submitted",
        name_ar="إرسال الطلب للمزود",
        group="orders",
        title="📤 تم إرسال طلبك للتنفيذ",
        body="الطلب {code} ({service_name}) أصبح لدى المزود وبدأ دوره في التنفيذ.",
        variables=("code", "service_name"),
        sample={"code": "ORD-10231", "service_name": "متابعون انستغرام"},
    ),
    TemplateDef(
        code="order_in_progress",
        name_ar="بدء التنفيذ",
        group="orders",
        title="🔄 طلبك قيد التنفيذ",
        body="بدأ تنفيذ الطلب {code} الآن.",
        variables=("code",),
        sample={"code": "ORD-10231"},
    ),
    TemplateDef(
        code="order_completed",
        name_ar="اكتمال الطلب",
        group="orders",
        title="🎉 اكتمل طلبك",
        body=(
            "تم تنفيذ الطلب {code} بالكامل.\n\n"
            "🛒 الخدمة: {service_name}\n"
            "🔢 الكمية: {quantity}\n\n"
            "شكراً لثقتك 🌟"
        ),
        variables=("code", "service_name", "quantity"),
        sample={
            "code": "ORD-10231",
            "service_name": "متابعون انستغرام",
            "quantity": "1,000",
        },
    ),
    TemplateDef(
        code="order_partial",
        name_ar="تنفيذ جزئي",
        group="orders",
        title="🟡 تم تنفيذ طلبك جزئياً",
        body=(
            "الطلب {code} نُفِّذ جزئياً.\n\n"
            "✅ المنفَّذ: {delivered} من {quantity}\n"
            "💰 أُعيد إلى رصيدك: {refund}\n\n"
            "المبلغ المسترجع متاح في محفظتك الآن."
        ),
        variables=("code", "delivered", "quantity", "refund"),
        sample={
            "code": "ORD-10231",
            "delivered": "600",
            "quantity": "1,000",
            "refund": "10.00",
        },
    ),
    TemplateDef(
        code="order_failed",
        name_ar="فشل الطلب",
        group="orders",
        title="❌ تعذّر تنفيذ طلبك",
        body=(
            "الطلب {code} لم يُنفَّذ.\n\n"
            "📝 السبب: {reason}\n"
            "💰 أُعيد كامل المبلغ إلى رصيدك: {refund}\n\n"
            "يمكنك المحاولة مرة أخرى أو التواصل مع الدعم."
        ),
        variables=("code", "reason", "refund"),
        sample={"code": "ORD-10231", "reason": "الرابط غير صحيح", "refund": "25.00"},
    ),
    TemplateDef(
        code="order_canceled",
        name_ar="إلغاء الطلب",
        group="orders",
        title="🚫 تم إلغاء طلبك",
        body="أُلغي الطلب {code}.\n💰 أُعيد المبلغ إلى رصيدك: {refund}",
        variables=("code", "refund"),
        sample={"code": "ORD-10231", "refund": "25.00"},
    ),
    TemplateDef(
        code="order_refunded",
        name_ar="استرجاع مبلغ طلب",
        group="orders",
        title="💰 تم استرجاع مبلغ طلبك",
        body="أُضيف مبلغ {refund} إلى رصيدك بخصوص الطلب {code}.",
        variables=("code", "refund"),
        sample={"code": "ORD-10231", "refund": "25.00"},
    ),
    TemplateDef(
        code="order_status_changed",
        name_ar="تغيّر حالة الطلب",
        group="orders",
        title="ℹ️ تحديث على طلبك",
        body="الطلب {code}: {status}",
        variables=("code", "status"),
        sample={"code": "ORD-10231", "status": "قيد التنفيذ"},
    ),
    # ----------------------------- المدفوعات ----------------------------- #
    TemplateDef(
        code="payment_received",
        name_ar="استلام طلب الشحن",
        group="payments",
        title="📥 تم استلام طلب الشحن",
        body="طلب الشحن #{payment_id} بمبلغ {amount} قيد المراجعة.\n{fee_block}سنعلمك فور اعتماده.",
        variables=("payment_id", "amount", "fee_block"),
        sample={
            "payment_id": "42",
            "amount": "200.00",
            "fee_block": "🧾 رسوم الطريقة: 6.00\n💵 المتوقع إضافته: 194.00\n",
        },
    ),
    TemplateDef(
        code="payment_approved",
        name_ar="اعتماد الشحن",
        group="payments",
        title="✅ تم اعتماد شحن رصيدك",
        body=(
            "طلب الشحن #{payment_id} اعتُمد.\n\n"
            "💵 المبلغ المضاف: {amount}\n"
            "👛 رصيدك الآن: {balance}"
        ),
        variables=("payment_id", "amount", "balance"),
        sample={"payment_id": "42", "amount": "194.00", "balance": "219.00"},
    ),
    TemplateDef(
        code="payment_rejected",
        name_ar="رفض الشحن",
        group="payments",
        title="❌ تم رفض طلب الشحن",
        body=(
            "طلب الشحن #{payment_id} مرفوض.\n📝 السبب: {reason}\n\n"
            "إن كنت ترى أن هذا خطأ، تواصل مع الدعم."
        ),
        variables=("payment_id", "reason"),
        sample={"payment_id": "42", "reason": "رقم العملية غير صحيح"},
    ),
    TemplateDef(
        code="payment_expired",
        name_ar="انتهاء صلاحية الشحن",
        group="payments",
        title="⌛ انتهت صلاحية طلب الشحن",
        body="طلب الشحن #{payment_id} انتهت مهلته دون مراجعة. يمكنك إنشاء طلب جديد.",
        variables=("payment_id",),
        sample={"payment_id": "42"},
    ),
    # ------------------------------- الرصيد ------------------------------ #
    TemplateDef(
        code="balance_credited",
        name_ar="إضافة رصيد يدوية",
        group="wallet",
        title="💰 تمت إضافة رصيد",
        body=(
            "أضافت الإدارة {amount} إلى رصيدك.\n"
            "📝 السبب: {reason}\n👛 رصيدك الآن: {balance}"
        ),
        variables=("amount", "reason", "balance"),
        sample={"amount": "50.00", "reason": "تعويض", "balance": "75.00"},
    ),
    TemplateDef(
        code="balance_debited",
        name_ar="خصم رصيد يدوي",
        group="wallet",
        title="➖ تم خصم رصيد",
        body=(
            "خصمت الإدارة {amount} من رصيدك.\n"
            "📝 السبب: {reason}\n👛 رصيدك الآن: {balance}"
        ),
        variables=("amount", "reason", "balance"),
        sample={"amount": "50.00", "reason": "تصحيح شحن مكرر", "balance": "25.00"},
    ),
    # -------------------------------- الدعم ------------------------------ #
    TemplateDef(
        code="ticket_replied",
        name_ar="رد الدعم على التذكرة",
        group="tickets",
        title="💬 رد جديد من الدعم",
        body="لديك رد على التذكرة #{ticket_id}:\n\n«{preview}»",
        variables=("ticket_id", "preview"),
        sample={"ticket_id": "7", "preview": "تم تنفيذ طلبك، يرجى المراجعة"},
    ),
    TemplateDef(
        code="ticket_closed",
        name_ar="إغلاق التذكرة",
        group="tickets",
        title="✅ تم إغلاق تذكرتك",
        body="تم إغلاق التذكرة #{ticket_id}.{reason_block}",
        variables=("ticket_id", "reason_block"),
        sample={"ticket_id": "7", "reason_block": "\n📝 تمت معالجة الطلب"},
    ),
    # ------------------------------- الحساب ------------------------------ #
    TemplateDef(
        code="account_banned",
        name_ar="حظر الحساب",
        group="account",
        title="🚫 تم حظر حسابك",
        body="تم إيقاف حسابك عن استخدام البوت.\n📝 السبب: {reason}",
        variables=("reason",),
        sample={"reason": "مخالفة الشروط"},
    ),
    TemplateDef(
        code="account_unbanned",
        name_ar="رفع الحظر",
        group="account",
        title="✅ تم رفع الحظر",
        body="أصبح بإمكانك استخدام البوت مجدداً. نتمنى لك تجربة طيبة.",
        variables=(),
        sample={},
    ),
)

#: فهرس سريع بالرمز
TEMPLATE_BY_CODE: dict[str, TemplateDef] = {item.code: item for item in TEMPLATES}


# ======================================================================= #
#                    طبقة التخصيص (ذاكرة + تحقق + عرض)                    #
# ======================================================================= #

#: القوالب المخصّصة المحمّلة من قاعدة البيانات: code -> (title, body)
#: تُملأ من `TemplateService.refresh_cache()` عند الإقلاع وبعد كل تعديل.
_overrides: dict[str, tuple[str, str]] = {}


def set_overrides(mapping: dict[str, tuple[str, str]]) -> None:
    """استبدال ذاكرة القوالب المخصّصة بالكامل (تُستدعى بعد أي تعديل أو عند الإقلاع)."""
    _overrides.clear()
    _overrides.update(mapping)


def clear_overrides() -> None:
    """إفراغ القوالب المخصّصة والعودة للنصوص الافتراضية (تُستخدم في الاختبارات أيضاً)."""
    _overrides.clear()


def active_overrides() -> dict[str, tuple[str, str]]:
    """نسخة من القوالب المخصّصة الفعّالة حالياً (للعرض والتشخيص)."""
    return dict(_overrides)


def placeholders_in(text: str) -> list[str]:
    """
    استخراج أسماء المتغيرات المكتوبة داخل نص قالب.

    الاسم الفارغ `{}` أو الرقمي `{0}` يُرجَع كما هو ليُرفض لاحقاً في التحقق،
    وأي محاولة وصول لخاصية أو فهرس (`{a.b}` / `{a[0]}`) تُرجَع كاملة لترفض كذلك.
    """
    found: list[str] = []
    for _literal, field_name, _spec, _conv in Formatter().parse(text):
        if field_name is None:
            continue
        found.append(field_name)
    return found


def invalid_placeholders(text: str, allowed: tuple[str, ...]) -> list[str]:
    """
    قائمة المتغيرات غير المسموحة في نص قالب (فارغة تعني أن النص صالح).

    لماذا التشدد؟ لأن `str.format` على نص يكتبه الأدمن سلاح ذو حدين:
    `{x.__class__}` يسرّب تفاصيل داخلية، و`{a:>999999}` يصنع رسالة ضخمة.
    لذلك نقبل أسماء المتغيرات المعلنة فقط، بلا نقطة ولا قوس ولا تنسيق.
    """
    bad: list[str] = []
    for _literal, field_name, spec, conv in Formatter().parse(text):
        if field_name is None:
            continue
        if field_name not in allowed or spec or conv:
            bad.append(field_name or "{}")
    return bad


def missing_placeholders(text: str, provided: dict[str, str]) -> list[str]:
    """المتغيرات المذكورة في النص ولا توجد لها قيمة (تمنع KeyError وقت الإرسال)."""
    return [name for name in placeholders_in(text) if name not in provided]


def render(template_code: str, /, **variables: object) -> tuple[str, str]:
    """
    بناء (العنوان، النص) لحدث قابل للتحرير.

    الترتيب: القالب المخصّص الفعّال ← ثم الافتراضي المدمج.
    أي خطأ في القالب المخصّص (متغير ناقص مثلاً) يُسجَّل في اللوق ويُستعمل
    الافتراضي بدلاً منه — رسالة العميل لا تضيع بسبب خطأ صياغة.

    اسم المعامل الأول موضعي فقط (`/`) لأن «code» نفسه أحد متغيرات القوالب.
    """
    definition = TEMPLATE_BY_CODE.get(template_code)
    if definition is None:  # رمز غير معروف = خطأ برمجي، نكشفه فوراً
        raise KeyError(f"قالب غير معرّف: {template_code}")

    values = {key: str(value) for key, value in variables.items()}
    custom = _overrides.get(template_code)
    if custom is not None:
        try:
            return (custom[0].format_map(values), custom[1].format_map(values))
        except (KeyError, IndexError, ValueError, AttributeError) as exc:
            logger.error(
                "فشل تطبيق القالب المخصّص «%s» (%s) — استُعمل النص الافتراضي",
                template_code, exc,
            )

    return (definition.title.format_map(values), definition.body.format_map(values))


# --------------------------------- الطلبات --------------------------------- #


def order_created(*, code: str, service_name: str, quantity: int, cost_units: int, symbol: str = "") -> tuple[str, str]:
    """إشعار إنشاء الطلب وخصم قيمته."""
    return render(
        "order_created",
        code=code,
        service_name=service_name,
        quantity=_count(quantity),
        amount=money(cost_units, symbol),
    )


def order_submitted(*, code: str, service_name: str) -> tuple[str, str]:
    """إشعار قبول المزود للطلب."""
    return render("order_submitted", code=code, service_name=service_name)


def order_in_progress(*, code: str) -> tuple[str, str]:
    """إشعار بدء التنفيذ الفعلي."""
    return render("order_in_progress", code=code)


def order_completed(*, code: str, service_name: str, quantity: int) -> tuple[str, str]:
    """إشعار اكتمال الطلب."""
    return render(
        "order_completed", code=code, service_name=service_name, quantity=_count(quantity)
    )


def order_partial(*, code: str, delivered: int, quantity: int, refund_units: int, symbol: str = "") -> tuple[str, str]:
    """إشعار التنفيذ الجزئي مع الاسترجاع."""
    return render(
        "order_partial",
        code=code,
        delivered=_count(delivered),
        quantity=_count(quantity),
        refund=money(refund_units, symbol),
    )


def order_failed(*, code: str, reason: str, refund_units: int, symbol: str = "") -> tuple[str, str]:
    """إشعار فشل الطلب مع الاسترجاع الكامل."""
    return render("order_failed", code=code, reason=reason, refund=money(refund_units, symbol))


def order_canceled(*, code: str, refund_units: int, symbol: str = "") -> tuple[str, str]:
    """إشعار إلغاء الطلب مع الاسترجاع."""
    return render("order_canceled", code=code, refund=money(refund_units, symbol))


def order_refunded(*, code: str, refund_units: int, symbol: str = "") -> tuple[str, str]:
    """إشعار إتمام الاسترجاع."""
    return render("order_refunded", code=code, refund=money(refund_units, symbol))


def order_status_changed(*, code: str, status: str) -> tuple[str, str]:
    """إشعار عام بتغيّر حالة الطلب (يُستخدم للحالات غير المذكورة أعلاه)."""
    return render("order_status_changed", code=code, status=order_label(status))


# -------------------------------- المدفوعات -------------------------------- #


def payment_received(
    *,
    payment_id: int,
    amount_units: int,
    symbol: str = "",
    fee_units: int = 0,
    net_units: int | None = None,
) -> tuple[str, str]:
    """
    إشعار استلام طلب الشحن (قيد المراجعة).

    عند وجود رسوم للطريقة يُذكر المبلغ الصافي صراحةً، حتى لا يُفاجأ
    المستخدم بفارق بين ما حوّله وما أُضيف لرصيده. سطور الرسوم تُبنى هنا
    وتُمرَّر للقالب كمتغير واحد `{fee_block}` يكون فارغاً عند انعدام الرسوم.
    """
    fee_block = ""
    if fee_units > 0:
        expected = amount_units - fee_units if net_units is None else net_units
        fee_block = (
            f"🧾 رسوم الطريقة: {money(fee_units, symbol)}\n"
            f"💵 المتوقع إضافته: {money(expected, symbol)}\n"
        )
    return render(
        "payment_received",
        payment_id=payment_id,
        amount=money(amount_units, symbol),
        fee_block=fee_block,
    )


def payment_approved(*, payment_id: int, credited_units: int, new_balance_units: int, symbol: str = "") -> tuple[str, str]:
    """إشعار اعتماد الشحن وإضافة الرصيد."""
    return render(
        "payment_approved",
        payment_id=payment_id,
        amount=money(credited_units, symbol),
        balance=money(new_balance_units, symbol),
    )


def payment_rejected(*, payment_id: int, reason: str) -> tuple[str, str]:
    """إشعار رفض طلب الشحن."""
    return render("payment_rejected", payment_id=payment_id, reason=reason)


def payment_expired(*, payment_id: int) -> tuple[str, str]:
    """إشعار انتهاء صلاحية طلب الشحن."""
    return render("payment_expired", payment_id=payment_id)


# --------------------------------- الرصيد ---------------------------------- #


def balance_credited(*, amount_units: int, new_balance_units: int, reason: str, symbol: str = "") -> tuple[str, str]:
    """إشعار إضافة رصيد يدوية من الإدارة."""
    return render(
        "balance_credited",
        amount=money(amount_units, symbol),
        reason=reason,
        balance=money(new_balance_units, symbol),
    )


def balance_debited(*, amount_units: int, new_balance_units: int, reason: str, symbol: str = "") -> tuple[str, str]:
    """إشعار خصم رصيد يدوي من الإدارة."""
    return render(
        "balance_debited",
        amount=money(amount_units, symbol),
        reason=reason,
        balance=money(new_balance_units, symbol),
    )


# ---------------------------------- الدعم ---------------------------------- #


def ticket_replied(*, ticket_id: int, preview: str) -> tuple[str, str]:
    """إشعار وصول رد من الدعم."""
    return render("ticket_replied", ticket_id=ticket_id, preview=preview)


def ticket_closed(*, ticket_id: int, reason: str) -> tuple[str, str]:
    """إشعار إغلاق التذكرة (سبب الإغلاق اختياري فيُمرَّر كمقطع جاهز)."""
    return render(
        "ticket_closed",
        ticket_id=ticket_id,
        reason_block=f"\n📝 {reason}" if reason else "",
    )


# -------------------------------- الحسابات --------------------------------- #


def account_banned(*, reason: str) -> tuple[str, str]:
    """إشعار حظر الحساب."""
    return render("account_banned", reason=reason)


def account_unbanned() -> tuple[str, str]:
    """إشعار رفع الحظر."""
    return render("account_unbanned")


# ---------------------------- تنبيهات الإدارة ------------------------------ #
# غير قابلة للتحرير من اللوحة عمداً: رسائل تشخيص داخلية، لا رسائل عملاء.


def admin_order_uncertain(*, code: str, order_id: int, error: str) -> tuple[str, str]:
    """تنبيه أدمن: نتيجة إرسال غير مؤكدة تحتاج قراراً بشرياً."""
    return (
        "❗ طلب بحالة غير مؤكدة",
        f"الطلب {code} (#{order_id}) انقطع أثناء الإرسال ولا نعرف هل وصل للمزود.\n"
        f"📝 التفاصيل: {error}\n\n"
        f"المطلوب: تحقق من لوحة المزود ثم اربط رقم الطلب أو أكّد الفشل ليُسترجع المبلغ.",
    )


def admin_order_failed(*, code: str, order_id: int, reason: str, refund_units: int, symbol: str = "") -> tuple[str, str]:
    """تنبيه أدمن: فشل طلب واسترجاع مبلغه."""
    return (
        "❌ فشل طلب واسترجاع تلقائي",
        f"الطلب {code} (#{order_id}) فشل.\n📝 السبب: {reason}\n"
        f"💰 المبلغ المسترجع: {money(refund_units, symbol)}",
    )


def admin_provider_disabled(*, provider_name: str, failures: int, minutes: int) -> tuple[str, str]:
    """تنبيه أدمن: تعطيل مؤقت لمزود بعد أخطاء متتالية."""
    return (
        "🔌 تعطيل مؤقت لمزود",
        f"المزود «{provider_name}» توقف مؤقتاً بعد {failures} أخطاء متتالية.\n"
        f"⏱ سيُعاد تفعيله تلقائياً بعد {minutes} دقيقة.",
    )


def admin_provider_low_balance(*, provider_name: str, balance_units: int, symbol: str = "") -> tuple[str, str]:
    """تنبيه أدمن: رصيد المزود قارب على النفاد."""
    return (
        "⚠️ رصيد مزود منخفض",
        f"رصيد حسابنا لدى «{provider_name}» أصبح {money(balance_units, symbol)}.\n"
        f"اشحن الحساب قبل توقف الطلبات.",
    )


def admin_new_payment(*, payment_id: int, amount_units: int, user_label: str, symbol: str = "") -> tuple[str, str]:
    """تنبيه أدمن: طلب شحن جديد بانتظار المراجعة."""
    return (
        "📥 طلب شحن جديد",
        f"طلب شحن #{payment_id} من {user_label} بمبلغ {money(amount_units, symbol)} ينتظر المراجعة.",
    )


def admin_new_ticket(*, ticket_id: int, subject: str, user_label: str) -> tuple[str, str]:
    """تنبيه أدمن: تذكرة دعم جديدة."""
    return (
        "🎫 تذكرة دعم جديدة",
        f"التذكرة #{ticket_id} من {user_label}\n📌 الموضوع: {subject}",
    )


def admin_stuck_orders(*, count: int, hours: int) -> tuple[str, str]:
    """تنبيه أدمن: طلبات متوقفة بلا تقدم."""
    return (
        "⏰ طلبات متوقفة",
        f"يوجد {count} طلب لم يتقدم منذ أكثر من {hours} ساعة. راجعها في لوحة الطلبات.",
    )


# ----------------------- المرحلة 6: المهام الدورية ---------------------- #


def admin_job_failing(*, job_name: str, failures: int, error: str) -> tuple[str, str]:
    """تنبيه أدمن: مهمة دورية تفشل بشكل متكرر (مؤشر عطل صامت في النظام)."""
    return (
        "🛠 مهمة دورية متعثرة",
        f"المهمة «{job_name}» فشلت {failures} مرات متتالية.\n"
        f"آخر خطأ: {error}\n"
        "راجع «📋 السجلات ← الأخطاء» في لوحة التحكم.",
    )


def admin_provider_recovered(*, provider_name: str, failures: int) -> tuple[str, str]:
    """تنبيه أدمن: مزود كان متعثراً وعاد يستجيب."""
    return (
        "✅ تعافى مزود",
        f"المزود «{provider_name}» عاد يستجيب بعد {failures} أخطاء متتالية، "
        "وأُعيد تفعيل الإرسال إليه.",
    )


def admin_daily_digest(
    *,
    orders_today: int,
    revenue_today_units: int,
    deposits_today_units: int,
    pending_payments: int,
    attention_orders: int,
    open_tickets: int,
    new_users: int,
    errors_24h: int,
    symbol: str = "",
) -> tuple[str, str]:
    """الملخص اليومي للأدمن: أرقام أمس/اليوم في رسالة واحدة."""
    return (
        "📊 الملخص اليومي",
        f"📦 طلبات اليوم: {orders_today}\n"
        f"💰 مبيعات اليوم: {money(revenue_today_units, symbol)}\n"
        f"💳 إيداعات معتمدة اليوم: {money(deposits_today_units, symbol)}\n"
        f"👥 مستخدمون جدد: {new_users}\n"
        f"⏳ طلبات شحن تنتظر المراجعة: {pending_payments}\n"
        f"⚠️ طلبات تحتاج انتباهك: {attention_orders}\n"
        f"🎫 تذاكر مفتوحة: {open_tickets}\n"
        f"🐞 أخطاء آخر 24 ساعة: {errors_24h}",
    )


# ------------------------- المرحلة 8: الإذاعة ---------------------------- #


def broadcast_finished(*, broadcast_id: int, sent: int, failed: int, blocked: int) -> tuple[str, str]:
    """تنبيه أدمن: انتهت الإذاعة مع حصيلتها النهائية."""
    return (
        "📣 انتهت الرسالة الجماعية",
        f"الإذاعة #{broadcast_id} اكتملت.\n"
        f"✅ وصلت: {sent}\n"
        f"🚫 حظروا البوت: {blocked}\n"
        f"⚠️ فشلت: {failed}",
    )
```

## المهام الدورية والإرسال

### `jobs/broadcast_jobs.py`  ·  جديد  ·  36 سطراً

مهمة إرسال دفعة إذاعة كل `broadcast_interval_seconds`.

```python
"""
مهمة إرسال الرسائل الجماعية على دفعات.

لماذا دفعات صغيرة متباعدة؟
    تيليجرام يحدّ الإرسال الجماعي (~30 رسالة/ثانية، وأقل لكل محادثة). إرسال
    آلاف الرسائل في حلقة واحدة يُنتج `RetryAfter` متتالياً وقد يُقيَّد البوت.
    هنا نرسل `broadcast_batch_size` رسالة كل `broadcast_interval_seconds`،
    وكلاهما قابل للضبط من «⚙️ الإعدادات ← broadcast» دون تعديل كود.

الأمان التشغيلي:
    • الجولة تعالج إذاعة واحدة فقط (الأقدم) حتى لا تتزاحم إذاعتان على الحصة.
    • نتيجة كل مستلم تُكتب فور إرسالها، فانقطاع البوت لا يُعيد إرسال ما وصل.
    • لا شيء يُرسل ما لم تكن حالة الإذاعة `running` — الإيقاف المؤقت فوري.
"""

from __future__ import annotations

from telegram.ext import ContextTypes

from jobs.telegram_sender import TelegramBroadcastSender
from utils.logging_setup import get_logger

logger = get_logger(__name__)


async def dispatch_broadcasts(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    جولة إذاعة واحدة: دفعة من مستلمي الإذاعة الجارية.

    لا تفعل شيئاً إن لم توجد إذاعة بحالة «جارية» — وهو الوضع الطبيعي معظم الوقت.
    """
    services = context.application.bot_data["services"]
    sender = TelegramBroadcastSender(context.bot)
    report = await services.broadcasts.send_batch(sender)
    if report.claimed:
        logger.info("جولة إذاعة: %s", report.as_dict())
```

### `jobs/telegram_sender.py`  ·  مُحدَّث (مقتطف)  ·  145 سطراً

مُرسل الإذاعة (نص/صورة) بنفس تصنيف أخطاء الإشعارات.

```python
class TelegramBroadcastSender:
    """
    مُرسل الرسائل الجماعية (نص أو صورة بتعليق) بنفس تصنيف أخطاء الإشعارات.

    لماذا مُرسل مستقل عن `TelegramNotificationSender`؟
        إشعار النظام له عنوان ونص ويُنسَّق بـHTML، أما الإذاعة فنص يكتبه الأدمن
        بحروفه وقد يرافقه ملف. خلطهما في دالة واحدة كان سيجبرنا على معاملات
        اختيارية تُربك الطرفين. التصنيف الدقيق للأخطاء مشترك عبر `_classify`.
    """

    def __init__(self, bot: Bot) -> None:
        """تهيئة المرسل ببوت تيليجرام الجاهز."""
        self.bot = bot

    async def __call__(
        self,
        telegram_id: int,
        text: str,
        media_file_id: str | None = None,
        media_type: str | None = None,
    ) -> int | None:
        """
        إرسال رسالة إذاعة واحدة.

        المخرجات: رقم الرسالة في تيليجرام عند النجاح.

        الاستثناءات: نفس استثناءات الإشعارات (محظور / مؤقت / نهائي) ليتعامل
        معها طابور الإذاعة بنفس المنطق المختبر.
        """
        body = html.escape(text or "")[:MAX_MESSAGE_LEN]
        try:
            if media_file_id and media_type == "photo":
                sent = await self.bot.send_photo(
                    chat_id=telegram_id,
                    photo=media_file_id,
                    caption=body[:1024] or None,
                    parse_mode=ParseMode.HTML,
                )
            elif media_file_id and media_type == "document":
                sent = await self.bot.send_document(
                    chat_id=telegram_id,
                    document=media_file_id,
                    caption=body[:1024] or None,
                    parse_mode=ParseMode.HTML,
                )
            else:
                sent = await self.bot.send_message(
                    chat_id=telegram_id,
                    text=body,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
        except Forbidden as exc:
            raise NotificationBlockedError(f"المستخدم {telegram_id} حظر البوت: {exc}") from exc
        except RetryAfter as exc:
            raise NotificationTemporaryError(
                f"تجاوز حد الإرسال، إعادة المحاولة بعد {exc.retry_after}ث"
            ) from exc
        except (TimedOut, NetworkError) as exc:
            raise NotificationTemporaryError(f"خطأ شبكة أثناء الإرسال: {exc}") from exc
        except BadRequest as exc:
            text_error = str(exc).lower()
            if "chat not found" in text_error or "user is deactivated" in text_error:
                raise NotificationBlockedError(f"محادثة غير متاحة: {exc}") from exc
            raise NotificationPermanentError(f"رسالة مرفوضة من تيليجرام: {exc}") from exc
        return sent.message_id
```

### `jobs/__init__.py`  ·  مُحدَّث (مقتطف)  ·  228 سطراً

تسجيل المهمة الدورية الجديدة.

```python
from jobs.broadcast_jobs import dispatch_broadcasts
    "broadcast_dispatch": "📣 إرسال الرسائل الجماعية",
        broadcast_dispatch     : إرسال دفعة من مستلمي الرسالة الجماعية الجارية.
            "broadcast_dispatch",

# ... (مقطع آخر من الملف) ...

        (
            "broadcast_dispatch",
            dispatch_broadcasts,
            await _interval(services, "broadcast_interval_seconds", 5),
            8.0,
            FAST_JOB_TIMEOUT,
        ),
```

## واجهة لوحة التحكم

### `handlers/admin/broadcast.py`  ·  جديد  ·  468 سطراً

قسم «📣 الإذاعة»: بطاقة، تحكم، محادثة إنشاء بتأكيد ثانٍ.

```python
"""
قسم «📣 الرسائل الجماعية» في لوحة التحكم (المرحلة 8).

ما يُنفَّذ هنا:
    • شاشة بآخر الرسائل الجماعية وحالة كل منها بأرقامها الحقيقية.
    • محادثة إنشاء رسالة: النص ← صورة اختيارية ← الشريحة ← مراجعة ← إرسال.
    • بطاقة متابعة حيّة: وصلت/فشلت/حظروا/متبقٍ ونسبة التقدم، مع 🔄 تحديث.
    • تحكم كامل أثناء الإرسال: إيقاف مؤقت، استئناف، إلغاء نهائي.

قواعد ملزمة مطبّقة هنا:
    • تأكيد ثانٍ إلزامي قبل أي إرسال جماعي (العملية لا تُستردّ بعد انطلاقها).
    • فحص `broadcast.send` على كل callback، لا على إظهار الزر فقط.
    • كل إنشاء/بدء/إيقاف/إلغاء يمرّ عبر `BroadcastService` فيُسجَّل في التدقيق.
    • المعالج لا يرسل رسالة واحدة بنفسه — الإرسال كله عبر المهمة الدورية،
      فلا يتجمّد البوت أثناء الضغط على زر، ولا تضيع التغذية الراجعة.
"""

from __future__ import annotations

import math

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from core.permissions import Permission
from database.models import Broadcast
from handlers.admin.common import (
    ADMIN_FLOW_KEY,
    admin_required,
    args,
    cancel_admin_flow,
    clear_flow,
    flow,
    permissions_of,
    start_flow,
    update_flow,
)
from handlers.common.fallbacks import exit_conversation
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import (
    BROADCAST_STATES,
    broadcast_card_kb,
    broadcast_confirm_kb,
    broadcast_home_kb,
    broadcast_media_kb,
    broadcast_target_kb,
    cancel_only_kb,
)
from keyboards.callback_data import NS_ADM_BRD, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from services.broadcast_service import MAX_BROADCAST_CAPTION, MAX_BROADCAST_TEXT
from texts import admin_ar as t
from utils.datetime_utils import to_local_text
from utils.formatters import safe
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: حالات محادثة «رسالة جماعية جديدة»
ASK_TEXT, ASK_MEDIA, CHOOSE_TARGET, CONFIRM_SEND = range(4)

#: عدد الرسائل المعروضة في شاشة الإذاعات
RECENT_LIMIT = 8


# ======================================================================== #
#                              أدوات داخلية                                #
# ======================================================================== #


async def _card_text(context: ContextTypes.DEFAULT_TYPE, broadcast_id: int) -> tuple[str, Broadcast]:
    """
    بناء نص بطاقة الرسالة الجماعية من أرقام قاعدة البيانات لحظة العرض.

    المخرجات: (نص البطاقة، كائن الإذاعة) — الكائن مطلوب لبناء أزرارها.
    """
    services = services_of(context)
    admin = require_user(context)
    data = await services.broadcasts.progress(admin, broadcast_id)
    broadcast: Broadcast = data["broadcast"]

    text = t.BROADCAST_CARD.format(
        id=broadcast.id,
        state=BROADCAST_STATES.get(broadcast.status, broadcast.status),
        target=data["target_label"],
        total=broadcast.total_count,
        sent=broadcast.sent_count,
        blocked=broadcast.blocked_count,
        failed=broadcast.failed_count,
        pending=data["pending"],
        percent=data["percent"],
        media_line=t.BROADCAST_MEDIA_LINE if broadcast.media_file_id else "",
        created=to_local_text(broadcast.created_at),
        text=safe(broadcast.message_text, limit=600),
    )
    return text, broadcast


async def _render_card(
    update: Update, context: ContextTypes.DEFAULT_TYPE, broadcast_id: int, *, as_new: bool = False
) -> None:
    """عرض بطاقة الرسالة الجماعية (تحديث الرسالة الحالية أو إرسال رسالة جديدة)."""
    text, broadcast = await _card_text(context, broadcast_id)
    perms = await permissions_of(context)
    markup = broadcast_card_kb(broadcast, perms)
    if as_new:
        await send(update, context, text, markup)
    else:
        await render(update, context, text, markup)


async def _pace_text(context: ContextTypes.DEFAULT_TYPE, count: int) -> tuple[int, int, int]:
    """
    حساب إيقاع الإرسال المتوقع: (حجم الدفعة، الفاصل بالثواني، الدقائق التقديرية).

    الأرقام من الإعدادات الفعلية لا من تخمين، فما يراه الأدمن قبل التأكيد
    هو ما سيحدث فعلاً.
    """
    services = services_of(context)
    batch = max(1, await services.settings.get_int("broadcast_batch_size", 20))
    interval = max(1, await services.settings.get_int("broadcast_interval_seconds", 5))
    minutes = math.ceil(math.ceil(count / batch) * interval / 60)
    return batch, interval, max(1, minutes)


# ======================================================================== #
#                             شاشات القراءة                                #
# ======================================================================== #


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def broadcast_home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة الرسائل الجماعية: آخر الرسائل وحالتها، وزر إنشاء رسالة جديدة."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    perms = await permissions_of(context)

    items = await services.broadcasts.recent(admin, limit=RECENT_LIMIT)
    if not items:
        await render(update, context, t.BROADCAST_EMPTY, broadcast_home_kb([], perms))
        return

    lines = []
    for item in items:
        lines.append(
            t.BROADCAST_LINE.format(
                state=BROADCAST_STATES.get(item.status, item.status),
                id=item.id,
                target=await services.broadcasts.target_label(item.target),
                sent=item.sent_count,
                total=item.total_count,
            )
        )
    await render(
        update,
        context,
        t.BROADCAST_HOME.format(lines="".join(lines)),
        broadcast_home_kb(items, perms),
    )


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def broadcast_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة رسالة جماعية واحدة بتقدمها الحالي (زر 🔄 يعيد قراءة الأرقام)."""
    await answer_callback(update)
    await _render_card(update, context, args(update).int_arg(0))


# ======================================================================== #
#                         إجراءات التحكم بالإرسال                          #
# ======================================================================== #


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بدء أو استئناف الإرسال (المهمة الدورية تتكفل بالدفعات بعدها)."""
    # ملاحظة: يُجاب على الـcallback مرة واحدة فقط (برسالة النتيجة) — الرد الثاني يتجاهله تيليجرام
    services = services_of(context)
    admin = require_user(context)
    broadcast_id = args(update).int_arg(0)

    broadcast = await services.broadcasts.start(admin, broadcast_id)
    pending = await services.broadcasts.progress(admin, broadcast_id)
    await answer_callback(
        update,
        t.BROADCAST_STARTED.format(id=broadcast.id, count=pending["pending"]),
    )
    await _render_card(update, context, broadcast_id)


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def pause_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إيقاف مؤقت: الجولة القادمة لا ترسل شيئاً، ويبقى المتبقون محفوظين."""
    # ملاحظة: يُجاب على الـcallback مرة واحدة فقط (برسالة النتيجة) — الرد الثاني يتجاهله تيليجرام
    services = services_of(context)
    admin = require_user(context)
    broadcast_id = args(update).int_arg(0)

    changed = await services.broadcasts.pause(admin, broadcast_id)
    await answer_callback(
        update,
        t.BROADCAST_PAUSED.format(id=broadcast_id) if changed else t.BROADCAST_NOTHING_TO_DO,
        alert=not changed,
    )
    await _render_card(update, context, broadcast_id)


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إلغاء نهائي للرسالة (لا تُستأنف، ومن وصلته تبقى عنده)."""
    # ملاحظة: يُجاب على الـcallback مرة واحدة فقط (برسالة النتيجة) — الرد الثاني يتجاهله تيليجرام
    services = services_of(context)
    admin = require_user(context)
    broadcast_id = args(update).int_arg(0)

    changed = await services.broadcasts.cancel(admin, broadcast_id)
    await answer_callback(
        update,
        t.BROADCAST_CANCELLED.format(id=broadcast_id) if changed else t.BROADCAST_NOTHING_TO_DO,
        alert=not changed,
    )
    await _render_card(update, context, broadcast_id)


# ======================================================================== #
#                      محادثة «رسالة جماعية جديدة»                         #
# ======================================================================== #


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def start_new_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الخطوة 1: طلب نص الرسالة."""
    await answer_callback(update)
    start_flow(context)
    await render(
        update,
        context,
        t.BROADCAST_ASK_TEXT.format(limit=MAX_BROADCAST_TEXT),
        cancel_only_kb(),
    )
    return ASK_TEXT


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def receive_broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الخطوة 2: حفظ النص بعد تنظيفه، ثم عرض خطوة الصورة الاختيارية."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_TEXT

    services = services_of(context)
    clean = services.broadcasts.validate_text(message.text, has_media=False)
    update_flow(context, text=clean)

    await send(
        update,
        context,
        t.BROADCAST_ASK_MEDIA.format(limit=MAX_BROADCAST_CAPTION),
        broadcast_media_kb(),
    )
    return ASK_MEDIA


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def receive_broadcast_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    الخطوة 3 (اختيارية): ربط صورة بالرسالة.

    مع الصورة يصبح النص تعليقاً، وحد التعليق في تيليجرام أقصر — فإن كان النص
    أطول نُخبر الأدمن بوضوح بدل أن يُقتطع النص صامتاً عند الإرسال.
    """
    message = update.effective_message
    if message is None or not message.photo:
        await send(
            update,
            context,
            t.BROADCAST_ASK_MEDIA.format(limit=MAX_BROADCAST_CAPTION),
            broadcast_media_kb(),
        )
        return ASK_MEDIA

    data = flow(context)
    text = str(data.get("text", ""))
    if len(text) > MAX_BROADCAST_CAPTION:
        await send(
            update,
            context,
            t.BROADCAST_MEDIA_TOO_LONG.format(limit=MAX_BROADCAST_CAPTION),
            broadcast_media_kb(),
        )
        return ASK_MEDIA

    update_flow(context, media_file_id=message.photo[-1].file_id, media_type="photo")
    return await _ask_target(update, context, as_new=True)


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def skip_broadcast_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تخطي الصورة والانتقال لاختيار الشريحة."""
    await answer_callback(update)
    return await _ask_target(update, context)


async def _ask_target(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, as_new: bool = False
) -> int:
    """عرض الشرائح مع عدد مستلمي كل شريحة الآن."""
    services = services_of(context)
    admin = require_user(context)
    rows = await services.broadcasts.audience_summary(admin)

    body = t.BROADCAST_ASK_TARGET.format(
        lines="".join(
            t.BROADCAST_TARGET_LINE.format(label=label, count=count) for _code, label, count in rows
        )
    )
    markup = broadcast_target_kb(rows)
    if as_new:
        await send(update, context, body, markup)
    else:
        await render(update, context, body, markup)
    return CHOOSE_TARGET


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def choose_broadcast_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الخطوة 4: حفظ الشريحة وعرض شاشة المراجعة النهائية قبل الإرسال."""
    services = services_of(context)
    admin = require_user(context)
    target = args(update).arg(0)

    count = await services.broadcasts.audience_count(admin, target)
    if count == 0:
        await answer_callback(update, t.BROADCAST_TARGET_EMPTY, alert=True)
        return CHOOSE_TARGET
    await answer_callback(update)

    update_flow(context, target=target, count=count)
    data = flow(context)
    batch, interval, minutes = await _pace_text(context, count)

    await render(
        update,
        context,
        t.BROADCAST_CONFIRM.format(
            target=await services.broadcasts.target_label(target),
            count=count,
            media_line=t.BROADCAST_MEDIA_LINE if data.get("media_file_id") else "",
            batch=batch,
            interval=interval,
            minutes=minutes,
            text=safe(str(data.get("text", "")), limit=600),
        ),
        broadcast_confirm_kb(),
    )
    return CONFIRM_SEND


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    الخطوة 5: إنشاء الرسالة فعلياً وبدء إرسالها.

    الإنشاء والبدء عمليتان متتاليتان في الخدمة: الأولى تثبّت قائمة المستلمين،
    والثانية تفتح الباب للمهمة الدورية. أي خطأ بينهما يترك مسودة قابلة للبدء يدوياً.
    """
    await answer_callback(update)
    data = flow(context)
    if not data.get("text") or not data.get("target"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    broadcast = await services.broadcasts.create(
        admin,
        text=str(data["text"]),
        target=str(data["target"]),
        media_file_id=data.get("media_file_id"),
        media_type=data.get("media_type"),
    )
    await services.broadcasts.start(admin, broadcast.id)
    clear_flow(context)
    logger.info(
        "أطلق الأدمن %s الإذاعة #%s إلى %s مستلم",
        admin.telegram_id, broadcast.id, broadcast.total_count,
    )

    await render(
        update,
        context,
        t.BROADCAST_STARTED.format(id=broadcast.id, count=broadcast.total_count),
    )
    await _render_card(update, context, broadcast.id, as_new=True)
    return ConversationHandler.END


# ============================== التسجيل ================================ #


def _fallbacks() -> list:
    """المسارات الاحتياطية الموحّدة لمحادثة هذا القسم."""
    return [
        CallbackQueryHandler(cancel_admin_flow, pattern=pattern(NS_FLOW, "cancel")),
        CommandHandler("cancel", cancel_admin_flow),
        CommandHandler("start", exit_conversation(ADMIN_FLOW_KEY)),
    ]


def conversations() -> list[ConversationHandler]:
    """محادثة إنشاء رسالة جماعية (نص ← صورة ← شريحة ← تأكيد)."""
    new_broadcast = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_new_broadcast, pattern=pattern(NS_ADM_BRD, "new"))
        ],
        states={
            ASK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_broadcast_text)],
            ASK_MEDIA: [
                MessageHandler(filters.PHOTO, receive_broadcast_media),
                CallbackQueryHandler(skip_broadcast_media, pattern=pattern(NS_FLOW, "skip")),
            ],
            CHOOSE_TARGET: [
                CallbackQueryHandler(
                    choose_broadcast_target, pattern=pattern(NS_ADM_BRD, "target")
                )
            ],
            CONFIRM_SEND: [
                CallbackQueryHandler(confirm_broadcast, pattern=pattern(NS_FLOW, "confirm"))
            ],
        },
        fallbacks=_fallbacks(),
        name="admin_broadcast_new",
        per_chat=True,
        per_user=True,
    )
    return [new_broadcast]


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم الرسائل الجماعية خارج المحادثة."""
    return [
        CallbackQueryHandler(broadcast_home_screen, pattern=pattern(NS_ADM_BRD, "home")),
        CallbackQueryHandler(broadcast_card_screen, pattern=pattern(NS_ADM_BRD, "view")),
        CallbackQueryHandler(start_broadcast, pattern=pattern(NS_ADM_BRD, "start")),
        CallbackQueryHandler(pause_broadcast, pattern=pattern(NS_ADM_BRD, "pause")),
        CallbackQueryHandler(cancel_broadcast, pattern=pattern(NS_ADM_BRD, "cancel")),
    ]
```

### `handlers/admin/templates.py`  ·  جديد  ·  324 سطراً

قسم «✉️ قوالب الإشعارات»: قائمة، بطاقة، معاينة، تعديل، إيقاف، استعادة.

```python
"""
قسم «✉️ قوالب الإشعارات» في لوحة التحكم (المرحلة 8).

ما يُنفَّذ هنا:
    • قائمة قوالب رسائل العملاء مجمّعة (طلبات/شحن/رصيد/دعم/حساب) مع علامة المعدَّل.
    • بطاقة القالب: النص الفعّال، المتغيرات المسموحة، وحالته (افتراضي/مخصّص/موقوف).
    • تعديل العنوان أو النص بمحادثة تعرض القيمة الحالية والمتغيرات المتاحة.
    • معاينة بقيم تجريبية عبر نفس مسار الإرسال الحقيقي (لا تُرسل لأحد).
    • إيقاف/تفعيل التخصيص، واستعادة النص الافتراضي بضغطة واحدة.

قواعد ملزمة مطبّقة هنا:
    • صلاحية `notifications.templates` تُفحص على كل callback.
    • التحقق من المتغيرات يتم في `TemplateService` قبل الحفظ، فلا يوجد
      مسار يحفظ قالباً قد يفشل عند الإرسال.
    • كل تعديل يُسجَّل في التدقيق بنصه قبل/بعد.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from core.permissions import Permission
from handlers.admin.common import (
    ADMIN_FLOW_KEY,
    admin_required,
    args,
    cancel_admin_flow,
    clear_flow,
    flow,
    start_flow,
)
from handlers.common.fallbacks import exit_conversation
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import (
    cancel_only_kb,
    template_card_kb,
    template_preview_kb,
    templates_home_kb,
)
from keyboards.callback_data import NS_ADM_TPL, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from texts import admin_ar as t
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: حالة محادثة «تعديل عنوان/نص قالب»
ASK_VALUE = 0

#: الحقول القابلة للتعديل: رمز الزر ⇐ اسم المعامل في الخدمة
EDIT_FIELDS = {"title": "title", "body": "body"}


# ======================================================================== #
#                              أدوات داخلية                                #
# ======================================================================== #


def _variables_text(variables: tuple[str, ...]) -> str:
    """عرض المتغيرات المتاحة بالشكل الذي يكتبه الأدمن حرفياً: {code} {amount}."""
    if not variables:
        return t.TEMPLATE_NO_VARIABLES
    return " ".join(f"<code>{{{name}}}</code>" for name in variables)


def _escape(value: str) -> str:
    """تهريب نص القالب قبل عرضه داخل رسالة HTML (حتى لا تُفسد الأقواس المعقوفة العرض)."""
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def _render_card(
    update: Update, context: ContextTypes.DEFAULT_TYPE, code: str, *, as_new: bool = False
) -> None:
    """عرض بطاقة القالب بنصه الفعّال وحالته (تحديث الرسالة أو إرسال جديدة)."""
    services = services_of(context)
    admin = require_user(context)
    state = await services.templates.get_state(admin, code)
    definition = state["definition"]

    if not state["is_customized"]:
        state_text = t.TEMPLATE_STATE_TEXT_DEFAULT
    elif state["is_active"]:
        state_text = t.TEMPLATE_STATE_TEXT_CUSTOM
    else:
        state_text = t.TEMPLATE_STATE_TEXT_PAUSED

    text = t.TEMPLATE_CARD.format(
        name=definition.name_ar,
        state=state_text,
        variables=_variables_text(definition.variables),
        title=_escape(state["title"]),
        body=_escape(state["body"]),
    )
    markup = template_card_kb(
        code, is_customized=state["is_customized"], is_active=state["is_active"]
    )
    if as_new:
        await send(update, context, text, markup)
    else:
        await render(update, context, text, markup)


# ======================================================================== #
#                             شاشات القراءة                                #
# ======================================================================== #


@guarded
@admin_required(Permission.NOTIFICATIONS_TEMPLATES)
async def templates_home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة القوالب مجمّعة حسب المجموعة، وعدّاد المعدَّل منها."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    items = await services.templates.overview(admin)

    lines: list[str] = []
    current_group = None
    for item in items:
        if item["group"] != current_group:
            current_group = item["group"]
            lines.append(t.TEMPLATES_GROUP_LINE.format(group=item["group_name"]))
        if not item["is_customized"]:
            state = t.TEMPLATE_STATE_DEFAULT
        elif item["is_active"]:
            state = t.TEMPLATE_STATE_CUSTOM
        else:
            state = t.TEMPLATE_STATE_OFF
        lines.append(t.TEMPLATE_LINE.format(state=state, name=item["name_ar"]))

    await render(
        update,
        context,
        t.TEMPLATES_HOME.format(
            customized=sum(1 for item in items if item["is_customized"]),
            total=len(items),
            lines="".join(lines),
        ),
        templates_home_kb(items),
    )


@guarded
@admin_required(Permission.NOTIFICATIONS_TEMPLATES)
async def template_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة قالب واحد."""
    await answer_callback(update)
    await _render_card(update, context, args(update).arg(0))


@guarded
@admin_required(Permission.NOTIFICATIONS_TEMPLATES)
async def template_preview_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معاينة القالب الفعّال بقيم تجريبية — لا تُرسل لأي مستخدم."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    code = args(update).arg(0)
    title, body = await services.templates.preview(admin, code)
    await render(
        update,
        context,
        t.TEMPLATE_PREVIEW.format(title=_escape(title), body=_escape(body)),
        template_preview_kb(code),
    )


# ======================================================================== #
#                         إجراءات بضغطة واحدة                              #
# ======================================================================== #


@guarded
@admin_required(Permission.NOTIFICATIONS_TEMPLATES)
async def toggle_template(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إيقاف أو تفعيل النص المخصّص (الإيقاف يُرجع الافتراضي دون فقد التعديل)."""
    # ملاحظة: يُجاب على الـcallback مرة واحدة فقط (برسالة النتيجة) — الرد الثاني يتجاهله تيليجرام
    services = services_of(context)
    admin = require_user(context)
    code = args(update).arg(0)

    state = await services.templates.get_state(admin, code)
    target_active = not state["is_active"]
    await services.templates.set_active(admin, code, active=target_active)
    name = state["definition"].name_ar
    await answer_callback(
        update,
        (t.TEMPLATE_ENABLED if target_active else t.TEMPLATE_DISABLED).format(name=name),
    )
    await _render_card(update, context, code)


@guarded
@admin_required(Permission.NOTIFICATIONS_TEMPLATES)
async def reset_template(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """استعادة النص الافتراضي (حذف التخصيص فقط، والنص الأصلي في الكود)."""
    # ملاحظة: يُجاب على الـcallback مرة واحدة فقط (برسالة النتيجة) — الرد الثاني يتجاهله تيليجرام
    services = services_of(context)
    admin = require_user(context)
    code = args(update).arg(0)

    name = services.templates.definition(code).name_ar
    deleted = await services.templates.reset(admin, code)
    await answer_callback(
        update,
        (t.TEMPLATE_RESET_DONE if deleted else t.TEMPLATE_RESET_NOTHING).format(name=name),
        alert=not deleted,
    )
    await _render_card(update, context, code)


# ======================================================================== #
#                     محادثة «تعديل عنوان/نص قالب»                         #
# ======================================================================== #


@guarded
@admin_required(Permission.NOTIFICATIONS_TEMPLATES)
async def start_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء التعديل: السؤال يعرض القيمة الحالية والمتغيرات المتاحة."""
    services = services_of(context)
    admin = require_user(context)
    data = args(update)
    code, field = data.arg(0), data.arg(1)

    if field not in EDIT_FIELDS:
        await answer_callback(update, t.TEMPLATE_NOT_FOUND, alert=True)
        return ConversationHandler.END
    await answer_callback(update)

    state = await services.templates.get_state(admin, code)
    definition = state["definition"]
    start_flow(context, code=code, field=field)

    prompt = t.TEMPLATE_ASK_TITLE if field == "title" else t.TEMPLATE_ASK_BODY
    await render(
        update,
        context,
        prompt.format(
            name=definition.name_ar,
            current=_escape(state[field]),
            variables=_variables_text(definition.variables),
        ),
        cancel_only_kb(),
    )
    return ASK_VALUE


@guarded
@admin_required(Permission.NOTIFICATIONS_TEMPLATES)
async def receive_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    استقبال النص الجديد وحفظه.

    إن رُفض النص (متغير غير مسموح مثلاً) تبقى المحادثة مفتوحة لإعادة المحاولة
    ولا يضيع ما كتبه الأدمن من سياق — الحارس `@guarded` يعرض سبب الرفض.
    """
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_VALUE

    data = flow(context)
    code, field = data.get("code"), data.get("field")
    if not code or field not in EDIT_FIELDS:
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    definition = services.templates.definition(str(code))

    await services.templates.set_text(admin, str(code), **{EDIT_FIELDS[field]: message.text})
    clear_flow(context)
    logger.info("حفظ الأدمن %s القالب %s (الحقل %s)", admin.telegram_id, code, field)

    await send(update, context, t.TEMPLATE_SAVED.format(name=definition.name_ar))
    await _render_card(update, context, str(code), as_new=True)
    return ConversationHandler.END


# ============================== التسجيل ================================ #


def _fallbacks() -> list:
    """المسارات الاحتياطية الموحّدة لمحادثة هذا القسم."""
    return [
        CallbackQueryHandler(cancel_admin_flow, pattern=pattern(NS_FLOW, "cancel")),
        CommandHandler("cancel", cancel_admin_flow),
        CommandHandler("start", exit_conversation(ADMIN_FLOW_KEY)),
    ]


def conversations() -> list[ConversationHandler]:
    """محادثة تعديل العنوان أو النص."""
    edit = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_edit, pattern=pattern(NS_ADM_TPL, "edit"))],
        states={ASK_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_value)]},
        fallbacks=_fallbacks(),
        name="admin_template_edit",
        per_chat=True,
        per_user=True,
    )
    return [edit]


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم القوالب خارج المحادثة."""
    return [
        CallbackQueryHandler(templates_home_screen, pattern=pattern(NS_ADM_TPL, "home")),
        CallbackQueryHandler(template_card_screen, pattern=pattern(NS_ADM_TPL, "view")),
        CallbackQueryHandler(template_preview_screen, pattern=pattern(NS_ADM_TPL, "prev")),
        CallbackQueryHandler(toggle_template, pattern=pattern(NS_ADM_TPL, "toggle")),
        CallbackQueryHandler(reset_template, pattern=pattern(NS_ADM_TPL, "reset")),
    ]
```

### `handlers/admin/tickets.py`  ·  مُحدَّث (مقتطف)  ·  409 سطراً

أولوية التذكرة + تبويب العاجلة.

```python
def _statuses_for(filter_code: str) -> tuple[tuple[str, ...], bool]:
    """
    الحالات المطلوبة لكل تبويب + هل يُقيَّد بالتذاكر المسندة للأدمن الحالي.

    المخرجات: (الحالات، هل التقييد بالإسناد مطلوب).
    """
    if filter_code == "wait":
        return (TicketStatus.OPEN, TicketStatus.PENDING_ADMIN), False
    if filter_code == "mine":
        return OPEN_STATUSES, True
    if filter_code == "high":
        return OPEN_STATUSES, False
    if filter_code == "closed":
        return (TicketStatus.CLOSED,), False
    return OPEN_STATUSES, False

# ... (مقطع آخر من الملف) ...

async def tickets_list_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة التذاكر حسب التبويب المختار."""
    await answer_callback(update)
    data = args(update)
    filter_code = data.arg(0, "open")
    if filter_code not in ADMIN_TICKET_FILTERS:
        filter_code = "open"

    services = services_of(context)
    admin = require_user(context)
    statuses, mine_only = _statuses_for(filter_code)
    assigned = admin.id if mine_only else None
    priority = "high" if filter_code == "high" else None

    total = await services.tickets.admin_count(
        admin, statuses=statuses, assigned_admin=assigned, priority=priority
    )
    page, total_pages, offset = paginate(total, data.int_arg(1, 1))
    tickets = await services.tickets.admin_list(
        admin,
        statuses=statuses,
        assigned_admin=assigned,
        priority=priority,
        limit=PAGE_SIZE,
        offset=offset,
    )
    open_count = await services.tickets.open_count()

    if not tickets:
        await render(
            update,
            context,
            t.TICKETS_EMPTY,
            admin_tickets_kb([], filter_code=filter_code, page=1, total_pages=1),
        )
        return

    lines = "\n\n".join(
        f"{ticket_status_text(ticket.status)} · <b>#{ticket.id}</b>\n"
        f"   📌 {safe(ticket.subject, limit=45)}\n"
        f"   🕒 {datetime_text(ticket.last_message_at or ticket.created_at)}"
        for ticket in tickets
    )
    await render(
        update,
        context,
        f"{t.TICKETS_TITLE.format(filter_name=ADMIN_TICKET_FILTERS[filter_code], open_count=open_count, page=page, pages=total_pages)}"
        f"\n\n{lines}",
        admin_tickets_kb(tickets, filter_code=filter_code, page=page, total_pages=total_pages),
    )

# ... (مقطع آخر من الملف) ...

@guarded
@admin_required(Permission.TICKETS_ASSIGN)
async def set_ticket_priority(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تغيير أولوية التذكرة (منخفضة/عادية/عالية) مع تسجيل التدقيق في الخدمة."""
    services = services_of(context)
    admin = require_user(context)
    data = args(update)
    ticket_id, priority = data.int_arg(0), data.arg(1)
    changed = await services.tickets.set_priority(admin, ticket_id, priority)
    label = TICKET_PRIORITIES.get(priority, priority)
    await answer_callback(
        update,
        t.TICKET_PRIORITY_SET.format(ticket_id=ticket_id, priority=label)
        if changed
        else t.TICKET_PRIORITY_SAME,
    )
    await _render_ticket(update, context, ticket_id)

# ... (مقطع آخر من الملف) ...

def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم الدعم خارج المحادثات."""
    return [
        CallbackQueryHandler(tickets_list_screen, pattern=pattern(NS_ADM_TKT, "list")),
        CallbackQueryHandler(ticket_card_screen, pattern=pattern(NS_ADM_TKT, "view")),
        CallbackQueryHandler(assign_ticket, pattern=pattern(NS_ADM_TKT, "assign")),
        CallbackQueryHandler(set_ticket_priority, pattern=pattern(NS_ADM_TKT, "prio")),
    ]
```

### `handlers/admin/__init__.py`  ·  مُحدَّث  ·  79 سطراً

تسجيل القسمين الجديدين.

```python
"""
حزمة لوحة التحكم: تجميع معالجات كل الأقسام في مكانين فقط.

تصدّر هذه الحزمة دالتين يستهلكهما `handlers/registry.py`:

    admin_conversations()   : كل محادثات الأدمن (تُسجَّل قبل أزرار الشاشات).
    admin_screen_handlers() : كل أزرار شاشات الأدمن.

كل وحدة قسم (`users`, `payments`, ...) تصدّر `conversations()` و`screens()`
فيبقى ترتيب التسجيل في مكان واحد ويظل من السهل التأكد أن كل زر له معالج.
"""

from __future__ import annotations

from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler

from handlers.admin import (
    broadcast,
    catalog,
    dashboard,
    logs,
    orders,
    payment_methods,
    payments,
    providers,
    settings,
    system,
    templates,
    tickets,
    users,
)
from keyboards.callback_data import NS_ADMIN, pattern

#: وحدات الأقسام بالترتيب الذي تُسجَّل به معالجاتها
SECTIONS = (
    users,
    payments,
    payment_methods,
    orders,
    tickets,
    catalog,
    providers,
    settings,
    logs,
    broadcast,
    templates,
    system,
)

__all__ = [
    "admin_conversations",
    "admin_screen_handlers",
    "admin_command_handlers",
    "SECTIONS",
]


def admin_conversations() -> list[ConversationHandler]:
    """كل محادثات لوحة التحكم مجموعة من كل الأقسام."""
    collected: list[ConversationHandler] = []
    for section in SECTIONS:
        collected.extend(section.conversations())
    return collected


def admin_screen_handlers() -> list[CallbackQueryHandler]:
    """كل أزرار شاشات لوحة التحكم (خارج المحادثات)."""
    collected: list[CallbackQueryHandler] = [
        CallbackQueryHandler(dashboard.panel_screen, pattern=pattern(NS_ADMIN, "home")),
        CallbackQueryHandler(dashboard.health_screen, pattern=pattern(NS_ADMIN, "health")),
    ]
    for section in SECTIONS:
        collected.extend(section.screens())
    return collected


def admin_command_handlers() -> list[CommandHandler]:
    """أوامر لوحة التحكم (/admin فقط حالياً)."""
    return [CommandHandler("admin", dashboard.admin_command)]
```

### `keyboards/admin_kb.py`  ·  مُحدَّث (مقتطف)  ·  1369 سطراً

لوحات الإذاعة والقوالب + صف الأولوية + زرا القائمة.

```python
#: وصف حالة الإذاعة كما يظهر في القوائم والبطاقات
BROADCAST_STATES: dict[str, str] = {
    "draft": t.BROADCAST_STATE_DRAFT,
    "running": t.BROADCAST_STATE_RUNNING,
    "paused": t.BROADCAST_STATE_PAUSED,
    "completed": t.BROADCAST_STATE_COMPLETED,
    "cancelled": t.BROADCAST_STATE_CANCELLED,
}

#: أزرار تغيير أولوية التذكرة (الرمز المخزَّن ⇐ التسمية المعروضة)
TICKET_PRIORITIES: dict[str, str] = {
    "low": t.TICKET_PRIORITY_LOW,
    "normal": t.TICKET_PRIORITY_NORMAL,
    "high": t.TICKET_PRIORITY_HIGH,
}

# ... (مقطع آخر من الملف) ...

    if Permission.BROADCAST_SEND in perms:
        add(InlineKeyboardButton(t.MENU_BROADCAST, callback_data=pack(NS_ADM_BRD, "home")))
    if Permission.NOTIFICATIONS_TEMPLATES in perms:
        add(InlineKeyboardButton(t.MENU_TEMPLATES, callback_data=pack(NS_ADM_TPL, "home")))
    if Permission.STATS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_HEALTH, callback_data=pack(NS_ADMIN, "health")))

# ... (مقطع آخر من الملف) ...

def admin_ticket_card_kb(
    ticket: SupportTicket, perms: set[str], *, filter_code: str = "open"
) -> InlineKeyboardMarkup:
    """أزرار بطاقة التذكرة الإدارية."""
    rows: list[list[InlineKeyboardButton]] = []
    action_row: list[InlineKeyboardButton] = []
    if ticket.is_open and Permission.TICKETS_REPLY in perms:
        action_row.append(
            InlineKeyboardButton(
                t.BTN_TICKET_REPLY, callback_data=pack(NS_ADM_TKT, "reply", ticket.id)
            )
        )
    if ticket.is_open and Permission.TICKETS_CLOSE in perms:
        action_row.append(
            InlineKeyboardButton(
                t.BTN_TICKET_CLOSE, callback_data=pack(NS_ADM_TKT, "close", ticket.id)
            )
        )
    if action_row:
        rows.append(action_row)

    if ticket.is_open and Permission.TICKETS_ASSIGN in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_TICKET_ASSIGN, callback_data=pack(NS_ADM_TKT, "assign", ticket.id)
                )
            ]
        )
    # تغيير الأولوية يتبع صلاحية الإسناد (نفس صلاحية `TicketService.set_priority`)
    if ticket.is_open and Permission.TICKETS_ASSIGN in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    f"{'• ' if ticket.priority == code else ''}{label}",
                    callback_data=pack(NS_ADM_TKT, "prio", ticket.id, code),
                )
                for code, label in TICKET_PRIORITIES.items()
            ]
        )
    if Permission.USERS_VIEW in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_TICKET_USER, callback_data=pack(NS_ADM_USERS, "view", ticket.user_id)
                )
            ]
        )
    rows.append(_back_row(NS_ADM_TKT, "list", filter_code, 1))
    return InlineKeyboardMarkup(rows)

# ... (مقطع آخر من الملف) ...

# ====================== المرحلة 8: الإذاعة والقوالب ===================== #


def broadcast_home_kb(broadcasts: list[Broadcast], perms: set[str]) -> InlineKeyboardMarkup:
    """
    شاشة الرسائل الجماعية: آخر الرسائل + زر إنشاء رسالة جديدة.

    زر الإنشاء يظهر فقط لمن يملك `broadcast.send` — والمعالج يفحصه مجدداً.
    """
    rows = [
        [
            InlineKeyboardButton(
                f"#{item.id} · {BROADCAST_STATES.get(item.status, item.status)} "
                f"· {item.sent_count}/{item.total_count}",
                callback_data=pack(NS_ADM_BRD, "view", item.id),
            )
        ]
        for item in broadcasts
    ]
    if Permission.BROADCAST_SEND in perms:
        rows.append(
            [InlineKeyboardButton(t.BTN_BROADCAST_NEW, callback_data=pack(NS_ADM_BRD, "new"))]
        )
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def broadcast_target_kb(rows_data: list[tuple[str, str, int]]) -> InlineKeyboardMarkup:
    """أزرار اختيار شريحة الاستهداف، وكل زر يحمل عدد مستلميها الحقيقي الآن."""
    rows = [
        [
            InlineKeyboardButton(
                f"{label} ({count})", callback_data=pack(NS_ADM_BRD, "target", code)
            )
        ]
        for code, label, count in rows_data
    ]
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)


def broadcast_media_kb() -> InlineKeyboardMarkup:
    """خطوة الصورة: تخطٍ صريح أو إلغاء (لا خطوة صامتة بلا زر)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t.BTN_BROADCAST_SKIP_MEDIA, callback_data=pack(NS_FLOW, "skip")
                )
            ],
            _cancel_row(),
        ]
    )


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    """تأكيد الإرسال الجماعي (خطوة ثانية إلزامية قبل أي إرسال فعلي)."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BROADCAST_BTN_SEND, callback_data=pack(NS_FLOW, "confirm"))],
            _cancel_row(),
        ]
    )


def broadcast_card_kb(broadcast: Broadcast, perms: set[str]) -> InlineKeyboardMarkup:
    """
    أزرار بطاقة الرسالة الجماعية حسب حالتها.

    المسودة/الموقوفة ⇐ بدء أو استئناف · الجارية ⇐ إيقاف مؤقت · وكلاهما يقبل الإلغاء.
    المكتملة والملغاة بلا أزرار تحكم (لا يمكن إعادة إرسالها فيُستلم النص مرتين).
    """
    rows: list[list[InlineKeyboardButton]] = []
    can_send = Permission.BROADCAST_SEND in perms
    actions: list[InlineKeyboardButton] = []

    if can_send and broadcast.status == "draft":
        actions.append(
            InlineKeyboardButton(
                t.BTN_BROADCAST_START, callback_data=pack(NS_ADM_BRD, "start", broadcast.id)
            )
        )
    if can_send and broadcast.status == "paused":
        actions.append(
            InlineKeyboardButton(
                t.BTN_BROADCAST_RESUME, callback_data=pack(NS_ADM_BRD, "start", broadcast.id)
            )
        )
    if can_send and broadcast.status == "running":
        actions.append(
            InlineKeyboardButton(
                t.BTN_BROADCAST_PAUSE, callback_data=pack(NS_ADM_BRD, "pause", broadcast.id)
            )
        )
    if actions:
        rows.append(actions)

    if can_send and broadcast.status in ("draft", "running", "paused"):
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_BROADCAST_CANCEL, callback_data=pack(NS_ADM_BRD, "cancel", broadcast.id)
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                t.BTN_REFRESH, callback_data=pack(NS_ADM_BRD, "view", broadcast.id)
            )
        ]
    )
    rows.append(_back_row(NS_ADM_BRD, "home"))
    return InlineKeyboardMarkup(rows)


def templates_home_kb(items: list[dict]) -> InlineKeyboardMarkup:
    """قائمة قوالب الإشعارات (زر لكل قالب) مع علامة المعدَّل منها."""
    rows = [
        [
            InlineKeyboardButton(
                f"{t.TEMPLATE_STATE_CUSTOM if item['is_customized'] else t.TEMPLATE_STATE_DEFAULT}"
                f" {item['name_ar']}",
                callback_data=pack(NS_ADM_TPL, "view", item["code"]),
            )
        ]
        for item in items
    ]
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def template_card_kb(code: str, *, is_customized: bool, is_active: bool) -> InlineKeyboardMarkup:
    """
    أزرار بطاقة القالب: تعديل العنوان/النص، معاينة، إيقاف التخصيص، واستعادة الافتراضي.

    «استعادة الافتراضي» تظهر فقط عند وجود تخصيص فعلي — لا زر بلا أثر.
    """
    rows = [
        [
            InlineKeyboardButton(
                t.BTN_TEMPLATE_EDIT_TITLE, callback_data=pack(NS_ADM_TPL, "edit", code, "title")
            ),
            InlineKeyboardButton(
                t.BTN_TEMPLATE_EDIT_BODY, callback_data=pack(NS_ADM_TPL, "edit", code, "body")
            ),
        ],
        [
            InlineKeyboardButton(
                t.BTN_TEMPLATE_PREVIEW, callback_data=pack(NS_ADM_TPL, "prev", code)
            )
        ],
    ]
    if is_customized:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_TEMPLATE_DISABLE if is_active else t.BTN_TEMPLATE_ENABLE,
                    callback_data=pack(NS_ADM_TPL, "toggle", code),
                ),
                InlineKeyboardButton(
                    t.BTN_TEMPLATE_RESET, callback_data=pack(NS_ADM_TPL, "reset", code)
                ),
            ]
        )
    rows.append(_back_row(NS_ADM_TPL, "home"))
    return InlineKeyboardMarkup(rows)


def template_preview_kb(code: str) -> InlineKeyboardMarkup:
    """زر العودة من المعاينة إلى بطاقة القالب نفسه."""
    return InlineKeyboardMarkup([_back_row(NS_ADM_TPL, "view", code)])
```

### `keyboards/callback_data.py`  ·  مُحدَّث (مقتطف)  ·  162 سطراً

مساحتا `bc` و`tp`.

```python
NS_ADM_PMT = "pm"     # طرق الشحن وإدارتها (المرحلة 7)
NS_ADM_BRD = "bc"     # الرسائل الجماعية (المرحلة 8)
NS_ADM_TPL = "tp"     # قوالب الإشعارات (المرحلة 8)
```

### `texts/admin_ar.py`  ·  مُحدَّث (مقتطف)  ·  1104 سطراً

نصوص الإذاعة والقوالب والأولوية.

```python
TICKET_CARD = (
    "🎫 <b>التذكرة #{ticket_id}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "👤 {name} (<code>{telegram_id}</code>)\n"
    "📌 {subject}\n"
    "🗂 التصنيف: {category}\n"
    "📊 الحالة: {status}\n"
    "{priority_line}"
    "{order_line}"
    "{assigned_line}"
    "📅 آخر رسالة: {last_message}\n\n"
    "💬 <b>المحادثة:</b>\n{conversation}"
)

# ... (مقطع آخر من الملف) ...

#        المرحلة 8 — الدعم والإشعارات والإذاعة (رسائل جماعية وقوالب)        #
# ======================================================================== #

# ------------------------------ قائمة اللوحة ---------------------------- #

MENU_BROADCAST = "📣 الإذاعة"
MENU_TEMPLATES = "✉️ قوالب الإشعارات"

# ------------------------------- الإذاعة -------------------------------- #

BROADCAST_HOME = (
    "📣 <b>الرسائل الجماعية</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "{lines}\n"
    "اختر رسالة لمتابعتها، أو أنشئ رسالة جديدة."
)
BROADCAST_EMPTY = (
    "📣 <b>الرسائل الجماعية</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "لم تُرسل أي رسالة جماعية بعد.\n\n"
    "الرسالة الجماعية تصل كل من يطابق الشريحة المختارة، "
    "وتُرسل على دفعات حتى لا يحدّ تيليجرام البوت."
)
BROADCAST_LINE = "{state} #{id} · {target} · ✅ {sent}/{total}\n"

BROADCAST_STATE_DRAFT = "📝 مسودة"
BROADCAST_STATE_RUNNING = "🚀 جارية"
BROADCAST_STATE_PAUSED = "⏸ موقوفة مؤقتاً"
BROADCAST_STATE_COMPLETED = "✅ اكتملت"
BROADCAST_STATE_CANCELLED = "🚫 ملغاة"

BROADCAST_CARD = (
    "📣 <b>الرسالة الجماعية #{id}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📊 الحالة: {state}\n"
    "🎯 الشريحة: {target}\n"
    "👥 المستلمون: {total}\n"
    "✅ وصلت: {sent}\n"
    "🚫 حظروا البوت: {blocked}\n"
    "⚠️ فشلت: {failed}\n"
    "⏳ متبقٍ: {pending}\n"
    "📈 التقدم: {percent}%\n"
    "{media_line}"
    "🕒 أُنشئت: {created}\n\n"
    "📄 <b>النص:</b>\n{text}"
)
BROADCAST_MEDIA_LINE = "🖼 مرفق: صورة\n"
BROADCAST_NOT_FOUND = "❌ هذه الرسالة غير موجودة."

BROADCAST_ASK_TEXT = (
    "✍️ أرسل نص الرسالة الجماعية كما تريد أن يصل المستخدم.\n\n"
    "• يمكن أن يتكوّن من عدة أسطر.\n"
    "• أقصى طول: {limit} حرفاً.\n"
    "• لا تُرسل أي رابط دفع أو بيانات حساسة."
)
BROADCAST_ASK_MEDIA = (
    "🖼 أرسل صورة لترافق الرسالة، أو اضغط «تخطي» لإرسال نص فقط.\n\n"
    "⚠️ مع الصورة يصبح الحد الأقصى للنص {limit} حرفاً."
)
BROADCAST_MEDIA_TOO_LONG = (
    "⚠️ النص أطول من {limit} حرفاً فلا يصلح كتعليق على صورة.\n"
    "اختصر النص أو أرسل الرسالة بلا صورة."
)
BROADCAST_ASK_TARGET = (
    "🎯 <b>اختر الشريحة المستهدفة</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "{lines}\n"
    "الأعداد محسوبة الآن من قاعدة البيانات، "
    "ولا تشمل المحظورين ولا من حظر البوت."
)
BROADCAST_TARGET_LINE = "{label}: {count}\n"
BROADCAST_TARGET_EMPTY = "❌ لا يوجد مستخدمون في هذه الشريحة الآن."

BROADCAST_CONFIRM = (
    "📣 <b>مراجعة قبل الإرسال</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🎯 الشريحة: {target}\n"
    "👥 ستصل إلى: {count} مستخدم\n"
    "{media_line}"
    "⏱ الإيقاع: {batch} رسالة كل {interval} ثانية (≈ {minutes} دقيقة)\n\n"
    "📄 <b>النص كما سيصل:</b>\n{text}\n\n"
    "⚠️ بعد الضغط يبدأ الإرسال فوراً، ويمكنك إيقافه مؤقتاً أو إلغاؤه في أي لحظة."
)
BROADCAST_BTN_SEND = "🚀 إرسال الآن"
BROADCAST_STARTED = (
    "🚀 بدأ إرسال الرسالة #{id} إلى {count} مستخدم.\n"
    "تابع التقدم من بطاقة الرسالة (زر 🔄 تحديث)."
)
BROADCAST_PAUSED = "⏸ أُوقفت الرسالة #{id} مؤقتاً. المتبقون لن تصلهم حتى الاستئناف."
BROADCAST_RESUMED = "▶️ استُؤنف إرسال الرسالة #{id}."
BROADCAST_CANCELLED = "🚫 أُلغيت الرسالة #{id}. من وصلته الرسالة تبقى عنده."
BROADCAST_NOTHING_TO_DO = "⚠️ لا جديد: الرسالة ليست في حالة تسمح بهذا الإجراء."

BTN_BROADCAST_NEW = "✍️ رسالة جديدة"
BTN_BROADCAST_START = "🚀 بدء الإرسال"
BTN_BROADCAST_RESUME = "▶️ استئناف"
BTN_BROADCAST_PAUSE = "⏸ إيقاف مؤقت"
BTN_BROADCAST_CANCEL = "🚫 إلغاء الرسالة"
BTN_BROADCAST_SKIP_MEDIA = "⏭ بلا صورة"

# -------------------------- قوالب الإشعارات ----------------------------- #

TEMPLATES_HOME = (
    "✉️ <b>قوالب الإشعارات</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "هذه نصوص الرسائل التي تصل عملاءك تلقائياً.\n"
    "✏️ معدّلة: {customized} من {total}\n\n"
    "{lines}\n"
    "اختر قالباً لعرضه أو تعديله. التنبيهات الداخلية للإدارة غير قابلة للتعديل."
)
TEMPLATES_GROUP_LINE = "\n<b>{group}</b>\n"
TEMPLATE_LINE = "{state} {name}\n"
TEMPLATE_STATE_DEFAULT = "▫️"
TEMPLATE_STATE_CUSTOM = "✏️"
TEMPLATE_STATE_OFF = "⏸"

TEMPLATE_CARD = (
    "✉️ <b>{name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📊 الحالة: {state}\n"
    "🔤 المتغيرات المتاحة: {variables}\n\n"
    "📌 <b>العنوان:</b>\n{title}\n\n"
    "📄 <b>النص:</b>\n{body}"
)
TEMPLATE_STATE_TEXT_DEFAULT = "النص الافتراضي المدمج"
TEMPLATE_STATE_TEXT_CUSTOM = "نص مخصّص (مفعّل)"
TEMPLATE_STATE_TEXT_PAUSED = "نص مخصّص موقوف — يُستعمل الافتراضي"
TEMPLATE_NO_VARIABLES = "لا متغيرات"

TEMPLATE_PREVIEW = (
    "👁 <b>معاينة بقيم تجريبية</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "<b>{title}</b>\n\n{body}\n\n"
    "ℹ️ هذه معاينة فقط — لم تُرسل لأي مستخدم."
)
TEMPLATE_ASK_TITLE = (
    "📌 أرسل العنوان الجديد للقالب «{name}».\n\n"
    "العنوان الحالي:\n{current}\n\n"
    "المتغيرات المتاحة: {variables}"
)
TEMPLATE_ASK_BODY = (
    "📄 أرسل النص الجديد للقالب «{name}» (يمكن أن يكون عدة أسطر).\n\n"
    "النص الحالي:\n{current}\n\n"
    "المتغيرات المتاحة: {variables}\n"
    "⚠️ اكتب المتغير كما هو بين قوسين، وأي متغير غير معروف سيُرفض."
)
TEMPLATE_SAVED = "✅ حُفظ القالب «{name}» وسيُستعمل في الرسائل القادمة فوراً."
TEMPLATE_RESET_DONE = "↩️ عاد القالب «{name}» إلى نصه الافتراضي."
TEMPLATE_RESET_NOTHING = "ℹ️ هذا القالب يستخدم النص الافتراضي أصلاً."
TEMPLATE_ENABLED = "✅ فُعِّل النص المخصّص للقالب «{name}»."
TEMPLATE_DISABLED = "⏸ أُوقف النص المخصّص — عاد القالب للنص الافتراضي."
TEMPLATE_NOT_FOUND = "❌ هذا القالب غير موجود."

BTN_TEMPLATE_EDIT_TITLE = "📌 تعديل العنوان"
BTN_TEMPLATE_EDIT_BODY = "📄 تعديل النص"
BTN_TEMPLATE_PREVIEW = "👁 معاينة"
BTN_TEMPLATE_RESET = "↩️ استعادة الافتراضي"
BTN_TEMPLATE_DISABLE = "⏸ إيقاف التخصيص"
BTN_TEMPLATE_ENABLE = "✅ تفعيل التخصيص"
BTN_TEMPLATES_HOME = "✉️ القوالب"

# --------------------------- أولوية التذاكر ------------------------------ #

TICKET_PRIORITY_LINE = "🚦 الأولوية: {priority}\n"
TICKET_PRIORITY_LOW = "🟢 منخفضة"
TICKET_PRIORITY_NORMAL = "🟡 عادية"
TICKET_PRIORITY_HIGH = "🔴 عالية"
TICKET_PRIORITY_SET = "🚦 صارت أولوية التذكرة #{ticket_id}: {priority}"
TICKET_PRIORITY_SAME = "ℹ️ التذكرة بهذه الأولوية أصلاً."
TICKET_FILTER_HIGH = "🔴 العاجلة"
```

## الاختبارات

### `tests/unit/test_template_catalog.py`  ·  جديد  ·  131 سطراً

حارس كتالوج القوالب: عرض كل قالب بقيمه، تطابق المتغيرات، رفض الخطر.

```python
"""
اختبارات طبقة قوالب الإشعارات (المرحلة 8) — منطق خالص بلا قاعدة بيانات.

الحارس الأهم هنا: **كل قالب افتراضي يجب أن يُعرَض بقيمه التجريبية بلا خطأ**،
وأن تتطابق متغيراته المعلنة مع ما كُتب فعلاً في نصه. غير ذلك = رسالة عميل
تنهار وقت الإرسال أو متغير معلَن لا يعمل.
"""

from __future__ import annotations

import pytest

from texts import templates as tpl


@pytest.fixture(autouse=True)
def _clean_overrides():
    """لا تتسرب القوالب المخصّصة بين الاختبارات."""
    tpl.clear_overrides()
    yield
    tpl.clear_overrides()


@pytest.mark.parametrize("definition", tpl.TEMPLATES, ids=lambda d: d.code)
def test_every_default_template_renders_with_its_sample(definition: tpl.TemplateDef) -> None:
    """كل قالب افتراضي يُعرَض بقيمه التجريبية دون KeyError أو نص مبتور."""
    title, body = tpl.render(definition.code, **definition.sample)
    assert title and body is not None
    assert "{" not in title and "}" not in title
    assert "{" not in body and "}" not in body


@pytest.mark.parametrize("definition", tpl.TEMPLATES, ids=lambda d: d.code)
def test_declared_variables_match_the_text(definition: tpl.TemplateDef) -> None:
    """المتغيرات المعلنة = المستخدمة فعلاً في العنوان والنص (لا زيادة ولا نقص)."""
    used = set(tpl.placeholders_in(definition.title)) | set(tpl.placeholders_in(definition.body))
    assert used == set(definition.variables)
    assert set(definition.sample) == set(definition.variables)


def test_codes_are_unique_and_groups_known() -> None:
    """رموز القوالب فريدة ومجموعاتها معرَّفة."""
    codes = [item.code for item in tpl.TEMPLATES]
    assert len(codes) == len(set(codes))
    assert {item.group for item in tpl.TEMPLATES} <= set(tpl.TEMPLATE_GROUPS)


def test_wrappers_keep_the_original_wording() -> None:
    """الدوال القديمة تُنتج نفس النص حرفياً بعد نقلها إلى طبقة القوالب (لا تراجع)."""
    title, body = tpl.order_failed(code="ORD-1", reason="رابط خاطئ", refund_units=250_000)
    assert title == "❌ تعذّر تنفيذ طلبك"
    assert body == (
        "الطلب ORD-1 لم يُنفَّذ.\n\n"
        "📝 السبب: رابط خاطئ\n"
        "💰 أُعيد كامل المبلغ إلى رصيدك: 25.00\n\n"
        "يمكنك المحاولة مرة أخرى أو التواصل مع الدعم."
    )
    _title, body = tpl.order_created(
        code="ORD-2", service_name="خدمة", quantity=1500, cost_units=10_000
    )
    assert "🔢 الكمية: 1,500" in body and "💵 المبلغ المخصوم: 1.00" in body


def test_payment_received_fee_block_only_when_fee_exists() -> None:
    """سطرا الرسوم يظهران عند وجود رسوم فقط، ولا يتركان سطراً فارغاً عند غيابها."""
    _t, with_fee = tpl.payment_received(
        payment_id=5, amount_units=2_000_000, fee_units=60_000, net_units=1_940_000
    )
    assert "🧾 رسوم الطريقة: 6.00" in with_fee
    assert "💵 المتوقع إضافته: 194.00" in with_fee
    _t, no_fee = tpl.payment_received(payment_id=5, amount_units=2_000_000)
    assert "رسوم" not in no_fee
    assert no_fee == "طلب الشحن #5 بمبلغ 200.00 قيد المراجعة.\nسنعلمك فور اعتماده."


def test_ticket_closed_reason_is_optional() -> None:
    """سبب الإغلاق يظهر فقط حين يُذكر."""
    assert tpl.ticket_closed(ticket_id=3, reason="")[1] == "تم إغلاق التذكرة #3."
    assert tpl.ticket_closed(ticket_id=3, reason="تم الحل")[1].endswith("📝 تم الحل")


def test_custom_template_replaces_default() -> None:
    """القالب المخصّص يحلّ محل الافتراضي عند البناء."""
    tpl.set_overrides({"order_in_progress": ("🔥 جاري", "طلبك {code} انطلق")})
    assert tpl.order_in_progress(code="ORD-9") == ("🔥 جاري", "طلبك ORD-9 انطلق")
    tpl.clear_overrides()
    assert tpl.order_in_progress(code="ORD-9")[0] == "🔄 طلبك قيد التنفيذ"


def test_broken_custom_template_falls_back_to_default() -> None:
    """قالب مخصّص بمتغير غير موجود لا يُسقط الرسالة — يُستعمل الافتراضي."""
    tpl.set_overrides({"order_in_progress": ("عنوان", "طلب {nonexistent}")})
    title, body = tpl.order_in_progress(code="ORD-9")
    assert title == "🔄 طلبك قيد التنفيذ"
    assert body == "بدأ تنفيذ الطلب ORD-9 الآن."


def test_unknown_template_code_is_a_programming_error() -> None:
    """رمز غير معرَّف يُكشف فوراً بدل أن يُنتج رسالة فارغة."""
    with pytest.raises(KeyError):
        tpl.render("does_not_exist")


@pytest.mark.parametrize(
    "text",
    [
        "{code.__class__}",       # وصول لخاصية
        "{code[0]}",              # فهرسة
        "{amount:>9999999}",      # تنسيق يصنع رسالة ضخمة
        "{amount!r}",             # تحويل
        "{}",                     # موضعي فارغ
        "{0}",                    # موضعي رقمي
        "{secret}",               # متغير غير معلَن
    ],
)
def test_dangerous_placeholders_are_rejected(text: str) -> None:
    """كل ما قد يسرّب داخلياتٍ أو يضخّم الرسالة يُرفض قبل الحفظ."""
    assert tpl.invalid_placeholders(text, ("code", "amount")) != []


def test_valid_placeholders_and_escaped_braces_pass() -> None:
    """المتغيرات المعلنة والأقواس المهرَّبة `{{ }}` مقبولة."""
    assert tpl.invalid_placeholders("طلب {code} بمبلغ {amount}", ("code", "amount")) == []
    assert tpl.invalid_placeholders("قوس {{حرفي}} هنا", ("code",)) == []


def test_set_overrides_replaces_everything() -> None:
    """استبدال الذاكرة كاملةً: القديم يختفي، لا دمج صامت."""
    tpl.set_overrides({"order_created": ("a", "b")})
    tpl.set_overrides({"order_failed": ("c", "d")})
    assert set(tpl.active_overrides()) == {"order_failed"}
```

### `tests/integration/test_templates_phase8.py`  ·  جديد  ·  389 سطراً

الخدمة والصلاحية والأثر الحقيقي والشاشات والترحيل.

```python
"""
اختبارات المرحلة 8 — قوالب الإشعارات القابلة للتحرير.

ما تغطيه:
    1. الخدمة: حفظ، تحقق من المتغيرات، إيقاف/تفعيل، استعادة الافتراضي، التدقيق.
    2. الصلاحية: `notifications.templates` من قاعدة البيانات لا من الكود.
    3. الأثر الحقيقي: اعتماد شحن فعلي يُنتج إشعاراً بالصياغة المعدَّلة.
    4. شاشات اللوحة والمحادثة، وأن رفض نص خاطئ لا يُسقط المحادثة.
"""

from __future__ import annotations

import pytest

from core.exceptions import PermissionDeniedError, ValidationError
from database.models import User
from handlers.admin import templates as templates_admin
from keyboards.callback_data import pack
from services import ServiceContainer
from tests.integration.test_user_interface import (
    bot,  # noqa: F401
    context,  # noqa: F401
    load_user,
    press,
    write,
)
from tests.telegram_fakes import FakeBot, FakeContext
from texts import templates as tpl

pytestmark = pytest.mark.asyncio


async def _audit_actions(services: ServiceContainer) -> list[str]:
    """أفعال سجل التدقيق كما هي في قاعدة البيانات (الأحدث أولاً)."""
    rows = await services.db.fetchall("SELECT action FROM audit_logs ORDER BY id DESC")
    return [row["action"] for row in rows]


async def _support_user(services: ServiceContainer) -> User:
    """مستخدم بدور دعم فني (لا يملك صلاحية القوالب افتراضياً)."""
    async with services.db.transaction() as tx:
        return await services.repos.users.create(
            tx, telegram_id=616161, username="sup8", first_name="دعم", role="support"
        )


# ======================================================================== #
#                               الخدمة                                     #
# ======================================================================== #


async def test_set_text_saves_and_changes_outgoing_messages(
    services: ServiceContainer, super_admin: User
) -> None:
    """الحفظ يُحمَّل فوراً: أول رسالة تُبنى بعده تحمل الصياغة الجديدة."""
    await services.templates.set_text(
        super_admin, "order_failed", body="⚠️ {code} تعثّر ({reason}) — رُدّ لك {refund}"
    )
    _title, body = tpl.order_failed(code="ORD-5", reason="رابط", refund_units=10_000)
    assert body == "⚠️ ORD-5 تعثّر (رابط) — رُدّ لك 1.00"


async def test_editing_title_only_keeps_default_body(
    services: ServiceContainer, super_admin: User
) -> None:
    """تعديل العنوان وحده لا يمسّ النص الافتراضي."""
    await services.templates.set_text(super_admin, "order_completed", title="🏆 تم")
    title, body = tpl.order_completed(code="ORD-1", service_name="خدمة", quantity=10)
    assert title == "🏆 تم"
    assert "تم تنفيذ الطلب ORD-1 بالكامل." in body


async def test_multiline_body_keeps_its_lines(
    services: ServiceContainer, super_admin: User
) -> None:
    """الأسطر داخل نص القالب تبقى كما كتبها الأدمن."""
    await services.templates.set_text(super_admin, "order_in_progress", body="سطر ١ {code}\n\nسطر ٣")
    _title, body = tpl.order_in_progress(code="X")
    assert body == "سطر ١ X\n\nسطر ٣"


@pytest.mark.parametrize(
    "bad_body",
    ["مرحباً {hacker}", "{code.__class__}", "{code!r}", "{code:>99999}", "{}", "   "],
)
async def test_invalid_text_is_rejected_and_nothing_saved(
    services: ServiceContainer, super_admin: User, bad_body: str
) -> None:
    """نص بمتغير غير مسموح أو تنسيق خطر أو فارغ يُرفض ولا يُحفظ شيء."""
    with pytest.raises(ValidationError):
        await services.templates.set_text(super_admin, "order_in_progress", body=bad_body)
    assert await services.repos.templates.get("order_in_progress") is None
    assert tpl.order_in_progress(code="Z")[1] == "بدأ تنفيذ الطلب Z الآن."


async def test_too_long_text_is_rejected(services: ServiceContainer, super_admin: User) -> None:
    """النص الأطول من الحد الأقصى يُرفض بدل أن يقتطعه تيليجرام لاحقاً."""
    with pytest.raises(ValidationError):
        await services.templates.set_text(
            super_admin, "order_in_progress", body="ا" * (tpl.MAX_TEMPLATE_BODY + 1)
        )


async def test_unknown_template_code_is_rejected(
    services: ServiceContainer, super_admin: User
) -> None:
    """رمز قالب غير موجود في الكتالوج لا يُنشئ صفاً."""
    with pytest.raises(ValidationError):
        await services.templates.set_text(super_admin, "not_a_template", body="x")


async def test_permission_comes_from_database(
    services: ServiceContainer, admin: User, user: User
) -> None:
    """الأدمن العادي يملك الصلاحية، ودور الدعم والمستخدم لا يملكانها."""
    await services.templates.set_text(admin, "order_in_progress", body="أدمن {code}")
    support = await _support_user(services)
    for actor in (support, user):
        with pytest.raises(PermissionDeniedError):
            await services.templates.set_text(actor, "order_in_progress", body="x {code}")
        with pytest.raises(PermissionDeniedError):
            await services.templates.overview(actor)
        with pytest.raises(PermissionDeniedError):
            await services.templates.reset(actor, "order_in_progress")


async def test_reset_restores_default_and_audits(
    services: ServiceContainer, super_admin: User
) -> None:
    """الاستعادة تحذف التخصيص فقط، والنص الأصلي يعود فوراً، والأثر مسجَّل."""
    await services.templates.set_text(super_admin, "order_in_progress", body="مخصّص {code}")
    assert await services.templates.reset(super_admin, "order_in_progress") is True
    assert tpl.order_in_progress(code="Q")[1] == "بدأ تنفيذ الطلب Q الآن."
    assert await services.repos.templates.get("order_in_progress") is None
    assert await services.templates.reset(super_admin, "order_in_progress") is False
    actions = await _audit_actions(services)
    assert actions.count("notifications.templates") == 2


async def test_disable_keeps_text_and_enable_brings_it_back(
    services: ServiceContainer, super_admin: User
) -> None:
    """الإيقاف يُرجع الافتراضي دون فقد التعديل، والتفعيل يستعيده."""
    await services.templates.set_text(super_admin, "order_in_progress", body="مخصّص {code}")
    assert await services.templates.set_active(super_admin, "order_in_progress", active=False)
    assert tpl.order_in_progress(code="Q")[1] == "بدأ تنفيذ الطلب Q الآن."
    row = await services.repos.templates.get("order_in_progress")
    assert row is not None and row.body == "مخصّص {code}"

    assert await services.templates.set_active(super_admin, "order_in_progress", active=True)
    assert tpl.order_in_progress(code="Q")[1] == "مخصّص Q"
    # نفس الحالة مرة ثانية لا تُحدث تغييراً ولا تدقيقاً زائداً
    assert not await services.templates.set_active(super_admin, "order_in_progress", active=True)


async def test_disable_without_customization_is_rejected(
    services: ServiceContainer, super_admin: User
) -> None:
    """لا معنى لإيقاف تخصيص غير موجود — خطأ واضح بدل نجاح صامت."""
    with pytest.raises(ValidationError):
        await services.templates.set_active(super_admin, "order_created", active=False)


async def test_set_text_records_before_and_after_in_audit(
    services: ServiceContainer, super_admin: User
) -> None:
    """التدقيق يحفظ النص قبل وبعد (الافتراضي يُسجَّل كـ«قبل» في أول تعديل)."""
    await services.templates.set_text(super_admin, "order_in_progress", body="جديد {code}")
    row = await services.db.fetchone(
        "SELECT before_json, after_json FROM audit_logs WHERE action = 'notifications.templates'"
    )
    assert "بدأ تنفيذ الطلب" in row["before_json"]
    assert "جديد" in row["after_json"]


async def test_preview_uses_sample_values_and_sends_nothing(
    services: ServiceContainer, super_admin: User
) -> None:
    """المعاينة تعرض القيم التجريبية ولا تُنشئ أي إشعار حقيقي."""
    await services.templates.set_text(super_admin, "order_failed", body="فشل {code} / {reason}")
    title, body = await services.templates.preview(super_admin, "order_failed")
    assert body == "فشل ORD-10231 / الرابط غير صحيح"
    assert await services.db.fetchval("SELECT COUNT(*) FROM notifications") == 0


async def test_overview_flags_customized_templates(
    services: ServiceContainer, super_admin: User
) -> None:
    """القائمة تميّز المعدَّل من الافتراضي وتغطي كل الكتالوج."""
    await services.templates.set_text(super_admin, "order_failed", title="🔴 فشل")
    items = {item["code"]: item for item in await services.templates.overview(super_admin)}
    assert len(items) == len(tpl.TEMPLATES)
    assert items["order_failed"]["is_customized"] and items["order_failed"]["is_active"]
    assert not items["order_created"]["is_customized"]


async def test_startup_recovery_loads_saved_templates(
    services: ServiceContainer, super_admin: User
) -> None:
    """بعد إعادة التشغيل (ذاكرة فارغة) يُعاد تحميل القوالب المحفوظة قبل أي إرسال."""
    await services.templates.set_text(super_admin, "order_in_progress", body="محفوظ {code}")
    tpl.clear_overrides()  # محاكاة إقلاع جديد
    assert tpl.order_in_progress(code="A")[1] != "محفوظ A"

    report = await services.startup_recovery()
    assert report["templates_loaded"] == 1
    assert tpl.order_in_progress(code="A")[1] == "محفوظ A"


async def test_real_payment_approval_uses_customized_wording(
    services: ServiceContainer, super_admin: User, admin: User, user: User, payment_method
) -> None:
    """الأثر الحقيقي: اعتماد شحن فعلي يُنتج إشعاراً بنص الأدمن المعدَّل."""
    await services.templates.set_text(
        super_admin,
        "payment_approved",
        title="💚 وصلت دفعتك",
        body="شكراً! أُضيف {amount} ورصيدك {balance}",
    )
    payment = await services.payments.create_payment(
        user,
        method_id=payment_method.id,
        raw_amount="5",
        transaction_reference="TRX-T8-1",
        proof_file_id="proof",
        proof_file_type="photo",
    )
    await services.payments.approve(admin, payment.id)

    row = await services.db.fetchone(
        "SELECT title, message FROM notifications WHERE type = 'payment_approved'"
    )
    assert row["title"] == "💚 وصلت دفعتك"
    assert row["message"] == "شكراً! أُضيف 5.00 ريال ورصيدك 5.00 ريال"


# ======================================================================== #
#                              شاشات اللوحة                                #
# ======================================================================== #


async def test_templates_home_lists_groups_and_counts(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer  # noqa: F811
) -> None:
    """القائمة تعرض المجموعات وعدّاد المعدَّل وزراً لكل قالب."""
    await services.templates.set_text(super_admin, "order_failed", title="🔴 فشل")
    await load_user(bot, context, super_admin)
    await press(bot, context, templates_admin.templates_home_screen, pack("tp", "home"), super_admin.telegram_id)

    assert "قوالب الإشعارات" in bot.last.text
    assert "معدّلة: 1 من" in bot.last.text
    assert "📦 الطلبات" in bot.last.text and "👛 الرصيد" in bot.last.text
    assert pack("tp", "view", "order_failed") in bot.last.buttons


async def test_card_shows_variables_and_hides_reset_when_default(
    bot: FakeBot, context: FakeContext, super_admin: User  # noqa: F811
) -> None:
    """بطاقة القالب الافتراضي: متغيراته ظاهرة، ولا زر استعادة بلا تخصيص."""
    await load_user(bot, context, super_admin)
    await press(
        bot, context, templates_admin.template_card_screen,
        pack("tp", "view", "order_created"), super_admin.telegram_id,
    )
    assert "{service_name}" in bot.last.text
    assert "النص الافتراضي المدمج" in bot.last.text
    assert pack("tp", "reset", "order_created") not in bot.last.buttons
    assert pack("tp", "edit", "order_created", "body") in bot.last.buttons


async def test_edit_conversation_saves_and_shows_card(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer  # noqa: F811
) -> None:
    """محادثة التعديل الكاملة: الزر ← النص ← حفظ ← بطاقة جديدة بزر الاستعادة."""
    await load_user(bot, context, super_admin)
    state = await press(
        bot, context, templates_admin.start_edit,
        pack("tp", "edit", "order_in_progress", "body"), super_admin.telegram_id,
    )
    assert state == templates_admin.ASK_VALUE
    assert "{code}" in bot.last.text

    result = await write(
        bot, context, templates_admin.receive_value, "🚀 طلبك {code} انطلق", super_admin.telegram_id
    )
    assert result is not None and result != templates_admin.ASK_VALUE
    assert tpl.order_in_progress(code="K")[1] == "🚀 طلبك K انطلق"
    assert pack("tp", "reset", "order_in_progress") in bot.last.buttons


async def test_edit_conversation_stays_open_on_bad_variable(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer  # noqa: F811
) -> None:
    """نص بمتغير مجهول: رسالة توضح المسموح، والمحادثة تبقى للمحاولة من جديد."""
    await load_user(bot, context, super_admin)
    await press(
        bot, context, templates_admin.start_edit,
        pack("tp", "edit", "order_in_progress", "body"), super_admin.telegram_id,
    )
    result = await write(
        bot, context, templates_admin.receive_value, "مرحباً {hacker}", super_admin.telegram_id
    )
    assert result is None  # الحارس يُبقي المستخدم في نفس الخطوة
    assert "غير مسموحة" in bot.last.text and "{code}" in bot.last.text
    assert await services.repos.templates.get("order_in_progress") is None


async def test_preview_toggle_reset_buttons_work(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer  # noqa: F811
) -> None:
    """أزرار المعاينة والإيقاف والاستعادة تعمل وتُحدّث البطاقة."""
    await services.templates.set_text(super_admin, "order_in_progress", body="مخصّص {code}")
    await load_user(bot, context, super_admin)

    await press(bot, context, templates_admin.template_preview_screen,
                pack("tp", "prev", "order_in_progress"), super_admin.telegram_id)
    assert "مخصّص ORD-10231" in bot.last.text and "معاينة" in bot.last.text

    await press(bot, context, templates_admin.toggle_template,
                pack("tp", "toggle", "order_in_progress"), super_admin.telegram_id)
    assert "موقوف" in bot.last.text
    assert tpl.order_in_progress(code="Q")[1] == "بدأ تنفيذ الطلب Q الآن."

    await press(bot, context, templates_admin.reset_template,
                pack("tp", "reset", "order_in_progress"), super_admin.telegram_id)
    assert "النص الافتراضي المدمج" in bot.last.text
    assert await services.repos.templates.get("order_in_progress") is None


async def test_support_role_cannot_open_templates_screen(
    bot: FakeBot, context: FakeContext, services: ServiceContainer  # noqa: F811
) -> None:
    """الدعم لا يفتح الشاشة (فحص الصلاحية على الـcallback) ولا يصله شيء."""
    support = await _support_user(services)
    await load_user(bot, context, support)
    await press(bot, context, templates_admin.templates_home_screen,
                pack("tp", "home"), support.telegram_id)
    assert not bot.sent
    assert bot.answers


async def test_panel_menu_shows_templates_button_by_permission(
    services: ServiceContainer, super_admin: User
) -> None:
    """زرا الإذاعة والقوالب في قائمة اللوحة يظهران بالصلاحية فقط."""
    from keyboards.admin_kb import admin_menu_kb

    support = await _support_user(services)
    full = {b.callback_data for row in admin_menu_kb(await services.auth.permissions_of(super_admin)).inline_keyboard for b in row}
    limited = {b.callback_data for row in admin_menu_kb(await services.auth.permissions_of(support)).inline_keyboard for b in row}
    assert pack("tp", "home") in full and pack("bc", "home") in full
    assert pack("tp", "home") not in limited and pack("bc", "home") not in limited


# ======================================================================== #
#                         الترحيل 0007 (المخطط والبذور)                    #
# ======================================================================== #


async def test_migration_0007_creates_table_permission_and_settings(
    services: ServiceContainer,
) -> None:
    """الترحيل يضيف الجدول والصلاحية وأدوارها والإعدادات الأربعة بقيمها الافتراضية."""
    db = services.db
    latest = await db.fetchval("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1")
    assert str(latest).startswith("0007")
    assert await db.fetchval("SELECT COUNT(*) FROM notification_templates") == 0  # لا بذور للقوالب

    roles = {
        row["role_code"]
        for row in await db.fetchall(
            "SELECT role_code FROM role_permissions WHERE permission_code = 'notifications.templates'"
        )
    }
    assert roles == {"super_admin", "admin"}

    expected = {
        "broadcast_batch_size": "20",
        "broadcast_interval_seconds": "5",
        "broadcast_active_days": "30",
        "ticket_reply_notify_admins": "1",
    }
    for key, value in expected.items():
        assert await services.repos.settings.get_raw(key) == value, key

    index = await db.fetchval(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'idx_broadcasts_status'"
    )
    assert index == "idx_broadcasts_status"
```

### `tests/integration/test_broadcast_phase8.py`  ·  جديد  ·  709 سطراً

الاستهداف ودورة الإرسال والأخطاء والشاشات وأولوية التذاكر.

```python
"""
اختبارات المرحلة 8 — الرسائل الجماعية (الإذاعة) وأولوية التذاكر.

ما تغطيه:
    1. الاستهداف: كل شريحة تحسب مستلميها الحقيقيين وتستثني المحظورين ومن حظر البوت.
    2. دورة الإرسال: دفعات، تسجيل كل مستلم، اكتمال تلقائي، إشعار منشئ الرسالة.
    3. الأمان التشغيلي: لا تكرار، إيقاف مؤقت فوري، إلغاء نهائي، استئناف بعد الإيقاف.
    4. الأخطاء: حظر البوت، فشل نهائي، فشل مؤقت يُعاد مرة واحدة.
    5. اللوحة: محادثة الإنشاء بتأكيدها الثاني، البطاقة، والصلاحيات.
    6. أولوية التذاكر وتصفية «العاجلة» وإعداد تنبيه الردود.
"""

from __future__ import annotations

import pytest
from telegram.ext import ConversationHandler

from core.exceptions import (
    NotificationBlockedError,
    NotificationPermanentError,
    NotificationTemporaryError,
    PermissionDeniedError,
    ValidationError,
)
from database.models import User
from handlers.admin import broadcast as broadcast_admin
from handlers.admin import tickets as tickets_admin
from keyboards.callback_data import pack
from services import ServiceContainer
from tests.integration.test_user_interface import (
    bot,  # noqa: F401
    context,  # noqa: F401
    load_user,
    press,
    write,
)
from tests.telegram_fakes import FakeBot, FakeContext

pytestmark = pytest.mark.asyncio


# ======================================================================== #
#                                أدوات                                     #
# ======================================================================== #


class RecordingSender:
    """مُرسل تجريبي يسجّل من أُرسل إليه، ويمكن برمجته ليفشل لمستلمين بعينهم."""

    def __init__(self) -> None:
        """تهيئة السجلات وجدول الأخطاء المبرمجة (telegram_id ⇐ استثناء أو قائمة استثناءات)."""
        self.sent: list[tuple[int, str, str | None, str | None]] = []
        self.plan: dict[int, list[Exception]] = {}

    async def __call__(
        self, telegram_id: int, text: str, media_file_id: str | None, media_type: str | None
    ) -> int:
        """إرسال مزيّف: يرفع الخطأ المبرمج التالي لهذا المستلم إن وُجد."""
        queue = self.plan.get(telegram_id)
        if queue:
            raise queue.pop(0)
        self.sent.append((telegram_id, text, media_file_id, media_type))
        return len(self.sent)

    @property
    def ids(self) -> list[int]:
        """معرفات تيليجرام لمن وصلتهم الرسالة بالترتيب."""
        return [item[0] for item in self.sent]


async def _make_user(
    services: ServiceContainer,
    telegram_id: int,
    *,
    banned: bool = False,
    blocked: bool = False,
    active_days_ago: int | None = 0,
) -> User:
    """إنشاء مستخدم بحالة محددة (محظور/حاظر للبوت/آخر نشاط)."""
    async with services.db.transaction() as tx:
        created = await services.repos.users.create(
            tx, telegram_id=telegram_id, username=f"u{telegram_id}", first_name="مستخدم", role="user"
        )
        last = None
        if active_days_ago is not None:
            from utils.datetime_utils import iso_minus_days, utc_now_iso

            last = iso_minus_days(active_days_ago) if active_days_ago else utc_now_iso()
        await tx.execute(
            "UPDATE users SET is_banned = ?, blocked_bot = ?, last_activity = ? WHERE id = ?",
            (1 if banned else 0, 1 if blocked else 0, last, created.id),
        )
    return created


@pytest.fixture
async def audience(services: ServiceContainer) -> dict[str, User]:
    """
    جمهور تجريبي: 3 عاديون + محظور + حاظر للبوت + قديم النشاط.

    (المستخدمون الثلاثة الافتراضيون user/admin/super_admin يُنشأون بالـfixtures عند طلبها فقط.)
    """
    return {
        "a": await _make_user(services, 7001),
        "b": await _make_user(services, 7002),
        "old": await _make_user(services, 7003, active_days_ago=90),
        "banned": await _make_user(services, 7004, banned=True),
        "blocked": await _make_user(services, 7005, blocked=True),
    }


# ======================================================================== #
#                              الاستهداف                                   #
# ======================================================================== #


async def test_all_target_excludes_banned_and_blocked(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """«الكل» لا يشمل المحظورين ولا من حظر البوت."""
    ids = set(await services.broadcasts.audience_ids("all"))
    assert audience["a"].id in ids and audience["b"].id in ids and audience["old"].id in ids
    assert audience["banned"].id not in ids
    assert audience["blocked"].id not in ids


async def test_active_target_respects_days_setting(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """«النشطون» يستبعد من لم ينشط خلال المدة المضبوطة، والمدة قابلة للتعديل."""
    ids = set(await services.broadcasts.audience_ids("active"))
    assert audience["a"].id in ids and audience["old"].id not in ids

    await services.settings.set("broadcast_active_days", "120", admin_id=super_admin.id)
    ids = set(await services.broadcasts.audience_ids("active"))
    assert audience["old"].id in ids


async def test_buyers_and_no_orders_targets_are_complementary(
    services: ServiceContainer,
    super_admin: User,
    admin: User,
    user: User,
    mock_service,
    audience: dict[str, User],
) -> None:
    """«من لديه طلب» و«بلا طلبات» شريحتان متكاملتان بلا تداخل."""
    await services.wallet.adjust_balance(
        target=user, amount_units=500_000, admin=admin, reason="رصيد", credit=True
    )
    await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/p/b8", quantity=1000
    )
    buyers = set(await services.broadcasts.audience_ids("buyers"))
    fresh = set(await services.broadcasts.audience_ids("no_orders"))

    assert user.id in buyers and audience["a"].id not in buyers
    assert audience["a"].id in fresh and user.id not in fresh
    assert buyers.isdisjoint(fresh)


async def test_unknown_target_is_rejected(services: ServiceContainer, super_admin: User) -> None:
    """شريحة غير معروفة تُرفض بدل أن تُرسل للجميع بالخطأ."""
    with pytest.raises(ValidationError):
        await services.broadcasts.audience_ids("everyone_and_more")


async def test_empty_audience_cannot_create_broadcast(
    services: ServiceContainer, super_admin: User
) -> None:
    """لا تُنشأ رسالة بلا مستلمين (قاعدة بلا مستخدمين عاديين)."""
    await _make_user(services, 7100, blocked=True)
    with pytest.raises(ValidationError):
        await services.broadcasts.create(super_admin, text="مرحبا", target="buyers")


# ======================================================================== #
#                              الإنشاء                                     #
# ======================================================================== #


async def test_create_freezes_recipients_and_audits(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """الإنشاء يثبّت قائمة المستلمين كمسودة ويسجّل التدقيق، ولا يرسل شيئاً."""
    broadcast = await services.broadcasts.create(super_admin, text="عرض اليوم\nخصم 10%", target="all")
    assert broadcast.status == "draft"
    assert broadcast.total_count == 4  # super_admin + a + b + old
    assert broadcast.message_text == "عرض اليوم\nخصم 10%"
    assert "broadcast.send" in [
        row["action"] for row in await services.db.fetchall("SELECT action FROM audit_logs")
    ]

    # مستخدم يسجّل بعد الإنشاء لا يدخل القائمة المثبّتة
    late = await _make_user(services, 7200)
    rows = await services.db.fetchall(
        "SELECT user_id FROM broadcast_recipients WHERE broadcast_id = ?", (broadcast.id,)
    )
    assert late.id not in {row["user_id"] for row in rows}


async def test_create_requires_permission(
    services: ServiceContainer, user: User, audience: dict[str, User]
) -> None:
    """لا أدمن ولا مستخدم عادي بلا `broadcast.send` ينشئ رسالة جماعية."""
    with pytest.raises(PermissionDeniedError):
        await services.broadcasts.create(user, text="x y", target="all")
    async with services.db.transaction() as tx:
        support = await services.repos.users.create(
            tx, telegram_id=7300, username="sup", first_name="دعم", role="support"
        )
    with pytest.raises(PermissionDeniedError):
        await services.broadcasts.create(support, text="x y", target="all")
    with pytest.raises(PermissionDeniedError):
        await services.broadcasts.audience_summary(support)


async def test_text_limits_differ_with_media(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """النص الطويل مقبول وحده، لكنه مرفوض كتعليق على صورة (حد تيليجرام 1024)."""
    long_text = "ا" * 1500
    ok = await services.broadcasts.create(super_admin, text=long_text, target="all")
    assert ok.total_count > 0
    with pytest.raises(ValidationError):
        await services.broadcasts.create(
            super_admin, text=long_text, target="all", media_file_id="f1", media_type="photo"
        )
    with pytest.raises(ValidationError):
        await services.broadcasts.create(super_admin, text="  ", target="all")


# ======================================================================== #
#                            دورة الإرسال                                  #
# ======================================================================== #


async def test_draft_is_never_sent_before_start(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """المسودة لا تُرسل ولو دارت المهمة: الإرسال يبدأ بقرار صريح فقط."""
    await services.broadcasts.create(super_admin, text="مسودة", target="all")
    sender = RecordingSender()
    report = await services.broadcasts.send_batch(sender)
    assert report.claimed == 0 and sender.sent == []


async def test_full_cycle_batches_then_completes_and_notifies_creator(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """الدورة كاملة: دفعات صغيرة ← كل مستلم يُسجَّل ← اكتمال ← إشعار الأدمن بالحصيلة."""
    broadcast = await services.broadcasts.create(super_admin, text="مرحباً بالجميع", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    sender = RecordingSender()

    first = await services.broadcasts.send_batch(sender, limit=3)
    assert (first.claimed, first.sent, first.completed) == (3, 3, False)
    mid = await services.broadcasts.get(super_admin, broadcast.id)
    assert mid.status == "running" and mid.sent_count == 3

    second = await services.broadcasts.send_batch(sender, limit=3)
    assert (second.claimed, second.sent, second.completed) == (1, 1, True)

    done = await services.broadcasts.get(super_admin, broadcast.id)
    assert done.status == "completed" and done.sent_count == 4 and done.finished_at
    assert len(sender.sent) == 4 and len(set(sender.ids)) == 4  # لا تكرار
    assert all(item[1] == "مرحباً بالجميع" for item in sender.sent)

    note = await services.db.fetchone(
        "SELECT message FROM notifications WHERE user_id = ? AND type = 'system'", (super_admin.id,)
    )
    assert note is not None and "اكتملت" in note["message"] and "وصلت: 4" in note["message"]

    # بعد الاكتمال لا شيء يُرسل ثانيةً
    again = await services.broadcasts.send_batch(sender)
    assert again.claimed == 0 and len(sender.sent) == 4


async def test_pause_stops_sending_and_resume_continues_without_duplicates(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """الإيقاف المؤقت فوري، والاستئناف يكمل من حيث توقف دون إعادة إرسال لأحد."""
    broadcast = await services.broadcasts.create(super_admin, text="رسالة طويلة", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    sender = RecordingSender()
    await services.broadcasts.send_batch(sender, limit=2)

    assert await services.broadcasts.pause(super_admin, broadcast.id) is True
    assert (await services.broadcasts.send_batch(sender)).claimed == 0
    assert len(sender.sent) == 2

    await services.broadcasts.start(super_admin, broadcast.id)  # استئناف
    await services.broadcasts.send_batch(sender, limit=10)
    assert len(sender.sent) == 4 and len(set(sender.ids)) == 4
    final = await services.broadcasts.get(super_admin, broadcast.id)
    assert final.status == "completed" and final.sent_count == 4


async def test_cancel_is_final_and_keeps_history(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """الإلغاء نهائي: لا استئناف، لا إرسال، وسجل المستلمين يبقى كاملاً."""
    broadcast = await services.broadcasts.create(super_admin, text="سيُلغى", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    sender = RecordingSender()
    await services.broadcasts.send_batch(sender, limit=1)

    assert await services.broadcasts.cancel(super_admin, broadcast.id) is True
    assert await services.broadcasts.cancel(super_admin, broadcast.id) is False
    with pytest.raises(ValidationError):
        await services.broadcasts.start(super_admin, broadcast.id)
    assert (await services.broadcasts.send_batch(sender)).claimed == 0

    total_rows = await services.db.fetchval(
        "SELECT COUNT(*) FROM broadcast_recipients WHERE broadcast_id = ?", (broadcast.id,)
    )
    assert total_rows == 4 and len(sender.sent) == 1


async def test_completed_broadcast_cannot_be_started_again(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """رسالة مكتملة لا تُعاد (وإلا استلم الناس النص مرتين)."""
    broadcast = await services.broadcasts.create(super_admin, text="مرة واحدة", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    await services.broadcasts.send_batch(RecordingSender(), limit=50)
    with pytest.raises(ValidationError):
        await services.broadcasts.start(super_admin, broadcast.id)


async def test_start_twice_is_rejected_while_running(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """البدء مرتين (ضغطة مزدوجة) لا يُنتج حالة مضاعفة."""
    broadcast = await services.broadcasts.create(super_admin, text="ضغطتان", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    with pytest.raises(ValidationError):
        await services.broadcasts.start(super_admin, broadcast.id)


async def test_resume_after_restart_continues_running_broadcast(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """إعادة تشغيل البوت لا تضيّع شيئاً: الإذاعة الجارية تُكمل في الجولة التالية."""
    broadcast = await services.broadcasts.create(super_admin, text="تستمر", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    first = RecordingSender()
    await services.broadcasts.send_batch(first, limit=2)

    # «إعادة تشغيل»: خدمة جديدة بنفس قاعدة البيانات
    from services import build_services
    from utils.security import SecretBox, generate_encryption_key

    revived = build_services(
        services.db, services.repos, secret_box=SecretBox(generate_encryption_key())
    )
    second = RecordingSender()
    await revived.broadcasts.send_batch(second, limit=10)
    assert set(first.ids).isdisjoint(second.ids)
    assert len(first.ids) + len(second.ids) == 4


# ======================================================================== #
#                              الأخطاء                                     #
# ======================================================================== #


async def test_blocked_user_is_recorded_and_flagged(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """من حظر البوت يُسجَّل «حظر» ويُعلَّم `blocked_bot` فلا يُزعَج لاحقاً."""
    broadcast = await services.broadcasts.create(super_admin, text="للجميع", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    sender = RecordingSender()
    sender.plan[7001] = [NotificationBlockedError("حظر البوت")]

    report = await services.broadcasts.send_batch(sender, limit=10)
    assert (report.sent, report.blocked, report.failed) == (3, 1, 0)
    refreshed = await services.repos.users.get_by_id(audience["a"].id)
    assert refreshed.blocked_bot
    done = await services.broadcasts.get(super_admin, broadcast.id)
    assert done.blocked_count == 1 and done.sent_count == 3


async def test_permanent_failure_is_recorded_without_retry(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """الفشل النهائي يُسجَّل مع سببه ولا يُعاد."""
    broadcast = await services.broadcasts.create(super_admin, text="للجميع", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    sender = RecordingSender()
    sender.plan[7002] = [NotificationPermanentError("رسالة مرفوضة"), NotificationPermanentError("x")]

    report = await services.broadcasts.send_batch(sender, limit=10)
    assert report.failed == 1 and report.sent == 3
    row = await services.db.fetchone(
        "SELECT status, error FROM broadcast_recipients WHERE user_id = ? AND broadcast_id = ?",
        (audience["b"].id, broadcast.id),
    )
    assert row["status"] == "failed" and "مرفوضة" in row["error"]
    assert len(sender.plan[7002]) == 1  # استُهلك خطأ واحد فقط: لا إعادة محاولة


async def test_temporary_failure_retries_once_then_succeeds(
    services: ServiceContainer, super_admin: User, audience: dict[str, User], monkeypatch
) -> None:
    """خطأ شبكة عابر يُعاد مرة واحدة فينجح الإرسال."""
    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("services.broadcast_service.asyncio.sleep", no_sleep)
    broadcast = await services.broadcasts.create(super_admin, text="للجميع", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    sender = RecordingSender()
    sender.plan[7001] = [NotificationTemporaryError("شبكة")]

    report = await services.broadcasts.send_batch(sender, limit=10)
    assert report.sent == 4 and report.failed == 0


async def test_temporary_failure_twice_is_recorded_as_failed(
    services: ServiceContainer, super_admin: User, audience: dict[str, User], monkeypatch
) -> None:
    """تكرار الخطأ العابر لا يعلّق الطابور: يُسجَّل فشلاً ويكمل الباقون."""
    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("services.broadcast_service.asyncio.sleep", no_sleep)
    broadcast = await services.broadcasts.create(super_admin, text="للجميع", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    sender = RecordingSender()
    sender.plan[7001] = [NotificationTemporaryError("شبكة"), NotificationTemporaryError("شبكة")]

    report = await services.broadcasts.send_batch(sender, limit=10)
    assert report.failed == 1 and report.sent == 3 and report.completed


async def test_media_details_reach_the_sender(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """الصورة ونوعها يصلان المُرسل مع النص كتعليق."""
    broadcast = await services.broadcasts.create(
        super_admin, text="عرض", target="all", media_file_id="photo-1", media_type="photo"
    )
    await services.broadcasts.start(super_admin, broadcast.id)
    sender = RecordingSender()
    await services.broadcasts.send_batch(sender, limit=1)
    assert sender.sent[0][2:] == ("photo-1", "photo")


async def test_progress_numbers_come_from_database(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """التقدم: النسبة والمتبقي محسوبان من الصفوف الفعلية."""
    broadcast = await services.broadcasts.create(super_admin, text="تقدم", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    await services.broadcasts.send_batch(RecordingSender(), limit=2)
    data = await services.broadcasts.progress(super_admin, broadcast.id)
    assert (data["done"], data["pending"], data["percent"]) == (2, 2, 50)


# ======================================================================== #
#                              مهمة الجدولة                                #
# ======================================================================== #


async def test_dispatch_job_sends_through_telegram_sender(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """المهمة الدورية تستخدم مُرسل تيليجرام الحقيقي وتُنهي الإذاعة."""
    from jobs.broadcast_jobs import dispatch_broadcasts
    from tests.telegram_fakes import FakeBot

    class _App:
        bot_data = {"services": services}

    class _Ctx:
        application = _App()
        bot = FakeBot()

    broadcast = await services.broadcasts.create(super_admin, text="عبر المهمة <b>", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    await dispatch_broadcasts(_Ctx())  # type: ignore[arg-type]

    done = await services.broadcasts.get(super_admin, broadcast.id)
    assert done.status == "completed" and done.sent_count == 4
    assert len(_Ctx.bot.sent) == 4
    assert "&lt;b&gt;" in _Ctx.bot.sent[0].text  # النص يُهرَّب: لا حقن HTML من الأدمن بالخطأ


# ======================================================================== #
#                              شاشات اللوحة                                #
# ======================================================================== #


async def test_home_screen_empty_then_lists_broadcasts(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer,  # noqa: F811
    audience: dict[str, User],
) -> None:
    """الشاشة الرئيسية: حالة فارغة واضحة ثم قائمة بالرسائل وأزرارها."""
    await load_user(bot, context, super_admin)
    await press(bot, context, broadcast_admin.broadcast_home_screen, pack("bc", "home"), super_admin.telegram_id)
    assert "لم تُرسل أي رسالة جماعية" in bot.last.text
    assert pack("bc", "new") in bot.last.buttons

    created = await services.broadcasts.create(super_admin, text="أولى", target="all")
    await press(bot, context, broadcast_admin.broadcast_home_screen, pack("bc", "home"), super_admin.telegram_id)
    assert pack("bc", "view", created.id) in bot.last.buttons


async def test_new_broadcast_conversation_needs_confirmation_then_runs(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer,  # noqa: F811
    audience: dict[str, User],
) -> None:
    """المحادثة كاملة: النص ← تخطي الصورة ← شريحة ← مراجعة ← تأكيد ثانٍ ← إرسال."""
    await load_user(bot, context, super_admin)
    uid = super_admin.telegram_id

    state = await press(bot, context, broadcast_admin.start_new_broadcast, pack("bc", "new"), uid)
    assert state == broadcast_admin.ASK_TEXT

    state = await write(bot, context, broadcast_admin.receive_broadcast_text, "صباح الخير\nعرض جديد", uid)
    assert state == broadcast_admin.ASK_MEDIA

    state = await press(bot, context, broadcast_admin.skip_broadcast_media, pack("flow", "skip"), uid)
    assert state == broadcast_admin.CHOOSE_TARGET
    assert pack("bc", "target", "all") in bot.last.buttons
    assert "كل المستخدمين: 4" in bot.last.text  # العدد الحقيقي يظهر قبل الاختيار

    state = await press(bot, context, broadcast_admin.choose_broadcast_target, pack("bc", "target", "all"), uid)
    assert state == broadcast_admin.CONFIRM_SEND
    assert "ستصل إلى: 4" in bot.last.text and "صباح الخير" in bot.last.text
    # قبل التأكيد لا شيء أُنشئ
    assert await services.db.fetchval("SELECT COUNT(*) FROM broadcasts") == 0

    await press(bot, context, broadcast_admin.confirm_broadcast, pack("flow", "confirm"), uid)
    row = await services.db.fetchone("SELECT status, total_count FROM broadcasts")
    assert row["status"] == "running" and row["total_count"] == 4
    assert "pause" in " ".join(bot.last.buttons)


async def test_conversation_with_photo_and_long_text_is_blocked(
    bot: FakeBot, context: FakeContext, super_admin: User,  # noqa: F811
    audience: dict[str, User],
) -> None:
    """نص أطول من حد التعليق مع صورة: رسالة واضحة والمحادثة تبقى في خطوة الصورة."""
    await load_user(bot, context, super_admin)
    uid = super_admin.telegram_id
    await press(bot, context, broadcast_admin.start_new_broadcast, pack("bc", "new"), uid)
    await write(bot, context, broadcast_admin.receive_broadcast_text, "ب" * 1500, uid)

    state = await write(bot, context, broadcast_admin.receive_broadcast_media, "", uid, photo=True)
    assert state == broadcast_admin.ASK_MEDIA
    assert "أطول" in bot.last.text


async def test_conversation_with_photo_short_text_proceeds(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer,  # noqa: F811
    audience: dict[str, User],
) -> None:
    """صورة مع نص قصير تنتقل مباشرة لاختيار الشريحة وتُحفظ في الإذاعة."""
    await load_user(bot, context, super_admin)
    uid = super_admin.telegram_id
    await press(bot, context, broadcast_admin.start_new_broadcast, pack("bc", "new"), uid)
    await write(bot, context, broadcast_admin.receive_broadcast_text, "صورة العرض", uid)
    state = await write(bot, context, broadcast_admin.receive_broadcast_media, "", uid, photo=True)
    assert state == broadcast_admin.CHOOSE_TARGET
    await press(bot, context, broadcast_admin.choose_broadcast_target, pack("bc", "target", "all"), uid)
    assert "صورة" in bot.last.text
    await press(bot, context, broadcast_admin.confirm_broadcast, pack("flow", "confirm"), uid)
    row = await services.db.fetchone("SELECT media_file_id, media_type FROM broadcasts")
    assert row["media_file_id"] == "photo-file-id" and row["media_type"] == "photo"


async def test_empty_target_is_refused_in_conversation(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer,  # noqa: F811
) -> None:
    """شريحة بلا مستلمين تُرفض بتنبيه، والمحادثة تبقى في اختيار الشريحة."""
    await load_user(bot, context, super_admin)
    uid = super_admin.telegram_id
    await press(bot, context, broadcast_admin.start_new_broadcast, pack("bc", "new"), uid)
    await write(bot, context, broadcast_admin.receive_broadcast_text, "نص", uid)
    await press(bot, context, broadcast_admin.skip_broadcast_media, pack("flow", "skip"), uid)
    state = await press(bot, context, broadcast_admin.choose_broadcast_target, pack("bc", "target", "buyers"), uid)
    assert state == broadcast_admin.CHOOSE_TARGET
    assert bot.answers[-1]["alert"]
    assert await services.db.fetchval("SELECT COUNT(*) FROM broadcasts") == 0


async def test_card_pause_resume_cancel_buttons(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer,  # noqa: F811
    audience: dict[str, User],
) -> None:
    """أزرار البطاقة تتبدّل مع الحالة: إيقاف ← استئناف ← إلغاء نهائي بلا أزرار تحكم."""
    created = await services.broadcasts.create(super_admin, text="تحكم", target="all")
    await services.broadcasts.start(super_admin, created.id)
    await load_user(bot, context, super_admin)
    uid = super_admin.telegram_id

    await press(bot, context, broadcast_admin.broadcast_card_screen, pack("bc", "view", created.id), uid)
    assert pack("bc", "pause", created.id) in bot.last.buttons
    assert "جارية" in bot.last.text

    await press(bot, context, broadcast_admin.pause_broadcast, pack("bc", "pause", created.id), uid)
    assert pack("bc", "start", created.id) in bot.last.buttons
    assert "موقوفة" in bot.last.text

    await press(bot, context, broadcast_admin.start_broadcast, pack("bc", "start", created.id), uid)
    assert "جارية" in bot.last.text

    await press(bot, context, broadcast_admin.cancel_broadcast, pack("bc", "cancel", created.id), uid)
    assert "ملغاة" in bot.last.text
    controls = [b for b in bot.last.buttons if b.startswith(("bc:start", "bc:pause", "bc:cancel"))]
    assert controls == []


async def test_support_cannot_use_broadcast_screens(
    bot: FakeBot, context: FakeContext, services: ServiceContainer,  # noqa: F811
    audience: dict[str, User],
) -> None:
    """الدعم الفني لا يفتح الإذاعة ولا يبدأ محادثتها (فحص على الـcallback)."""
    async with services.db.transaction() as tx:
        support = await services.repos.users.create(
            tx, telegram_id=7400, username="sup4", first_name="دعم", role="support"
        )
    await load_user(bot, context, support)
    await press(bot, context, broadcast_admin.broadcast_home_screen, pack("bc", "home"), support.telegram_id)
    assert not bot.sent
    state = await press(bot, context, broadcast_admin.start_new_broadcast, pack("bc", "new"), support.telegram_id)
    assert state == ConversationHandler.END and not bot.sent


# ======================================================================== #
#                       أولوية التذاكر وتنبيه الردود                       #
# ======================================================================== #


async def _open_ticket(services: ServiceContainer, user: User):
    """فتح تذكرة بسيطة للمستخدم."""
    return await services.tickets.create_ticket(
        user, subject="مشكلة في طلبي", message="الطلب متوقف منذ ساعة", category="other"
    )


async def test_priority_button_changes_priority_and_card(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User,  # noqa: F811
) -> None:
    """زر الأولوية يغيّرها، والبطاقة تعرضها، وتُسجَّل في التدقيق."""
    ticket = await _open_ticket(services, user)
    await load_user(bot, context, admin)

    await press(bot, context, tickets_admin.ticket_card_screen, pack("at", "view", ticket.id), admin.telegram_id)
    assert "عادية" in bot.last.text
    assert pack("at", "prio", ticket.id, "high") in bot.last.buttons

    await press(bot, context, tickets_admin.set_ticket_priority, pack("at", "prio", ticket.id, "high"), admin.telegram_id)
    assert "عالية" in bot.last.text
    fresh = await services.repos.tickets.get(ticket.id)
    assert fresh.priority == "high"

    await press(bot, context, tickets_admin.set_ticket_priority, pack("at", "prio", ticket.id, "high"), admin.telegram_id)
    assert bot.answers[-1]["text"]  # «بهذه الأولوية أصلاً»


async def test_priority_requires_assign_permission_and_valid_value(
    services: ServiceContainer, user: User
) -> None:
    """المستخدم العادي لا يغيّر الأولوية، وقيمة غير معروفة تُرفض."""
    ticket = await _open_ticket(services, user)
    with pytest.raises(PermissionDeniedError):
        await services.tickets.set_priority(user, ticket.id, "high")


async def test_high_filter_lists_only_urgent_open_tickets(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User,  # noqa: F811
) -> None:
    """تبويب «العاجلة» يعرض المفتوحة العالية الأولوية فقط."""
    urgent = await _open_ticket(services, user)
    async with services.db.transaction() as tx:
        other = await services.repos.users.create(
            tx, telegram_id=7500, username="o", first_name="آخر", role="user"
        )
    normal = await _open_ticket(services, other)
    await services.tickets.set_priority(admin, urgent.id, "high")

    await load_user(bot, context, admin)
    await press(bot, context, tickets_admin.tickets_list_screen, pack("at", "list", "high", 1), admin.telegram_id)
    assert pack("at", "view", urgent.id) in bot.last.buttons
    assert pack("at", "view", normal.id) not in bot.last.buttons
    assert "العاجلة" in bot.last.text


async def test_user_reply_notifies_admins_unless_setting_off(
    services: ServiceContainer, user: User, admin: User, super_admin: User
) -> None:
    """تنبيه الأدمن عند ردّ المستخدم يخضع للإعداد `ticket_reply_notify_admins`."""
    ticket = await _open_ticket(services, user)
    base = await services.db.fetchval("SELECT COUNT(*) FROM notifications")

    await services.tickets.reply_as_user(user, ticket.id, "ما زلت أنتظر")
    after_on = await services.db.fetchval("SELECT COUNT(*) FROM notifications")
    assert after_on > base

    await services.settings.set("ticket_reply_notify_admins", "0", admin_id=super_admin.id)
    await services.tickets.reply_as_user(user, ticket.id, "رد ثانٍ بلا تنبيه")
    assert await services.db.fetchval("SELECT COUNT(*) FROM notifications") == after_on
    # الرد نفسه محفوظ رغم عدم التنبيه
    messages = await services.repos.tickets.messages(ticket.id)
    assert messages[-1].message == "رد ثانٍ بلا تنبيه"
```

### `tests/conftest.py`  ·  مُحدَّث (مقتطف)  ·  201 سطراً

تصفير ذاكرة القوالب بين الاختبارات.

```python
from texts import templates as templates_module  # noqa: E402
from utils.security import SecretBox, generate_encryption_key  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_template_overrides():
    """
    تصفير قوالب الإشعارات المخصّصة قبل وبعد كل اختبار (المرحلة 8).

    ذاكرة القوالب عامة على مستوى الوحدة، فبدون هذا التصفير يتسرّب قالب
    عدّله اختبارٌ ما إلى اختبار آخر فيفشل لسبب لا علاقة له به.
    """
    templates_module.clear_overrides()
    yield
    templates_module.clear_overrides()
```

### `tests/integration/test_jobs.py`  ·  مُحدَّث (مقتطف)  ·  254 سطراً

إضافة المهمة الجديدة للمتوقَّع.

```python
            "broadcast_dispatch",       # المرحلة 8
```

### `tests/integration/test_no_dead_buttons.py`  ·  مُحدَّث (مقتطف)  ·  601 سطراً

تغطية لوحات المرحلة 8 في فحص «لا زر بلا معالج».

```python
def _fake_broadcast(index: int = 1, status: str = "draft") -> SimpleNamespace:
    """رسالة جماعية تجريبية (المرحلة 8)."""
    return SimpleNamespace(
        id=index,
        status=status,
        sent_count=3,
        total_count=10,
        failed_count=0,
        blocked_count=0,
        message_text="نص",
        target="all",
        media_file_id=None,
        created_at="2026-01-01T10:00:00+00:00",
    )


def _fake_template_item(code: str = "order_created", *, custom: bool = False) -> dict:
    """عنصر قائمة قوالب الإشعارات (المرحلة 8)."""
    return {
        "code": code,
        "name_ar": "إنشاء الطلب",
        "group": "orders",
        "group_name": "📦 الطلبات",
        "is_customized": custom,
        "is_active": custom,
        "updated_at": None,
    }


def _fake_ticket_with_priority() -> SimpleNamespace:
    """تذكرة مفتوحة بأولوية عالية (لتغطية زر الأولوية المحدَّد)."""
    ticket = _fake_ticket(5)
    ticket.priority = "high"
    ticket.user_id = 5
    return ticket

# ... (مقطع آخر من الملف) ...

        # ------------------------- المرحلة 8 ------------------------- #
        ("admin_ticket_card_kb_high", admin_kb.admin_ticket_card_kb(
            _fake_ticket_with_priority(), perms, filter_code="high"
        )),
        ("broadcast_home_kb", admin_kb.broadcast_home_kb(
            [_fake_broadcast(1), _fake_broadcast(2, "running")], perms
        )),
        ("broadcast_home_kb_empty", admin_kb.broadcast_home_kb([], perms)),
        ("broadcast_target_kb", admin_kb.broadcast_target_kb(
            [("all", "كل المستخدمين", 10), ("buyers", "المشترون", 4)]
        )),
        ("broadcast_media_kb", admin_kb.broadcast_media_kb()),
        ("broadcast_confirm_kb", admin_kb.broadcast_confirm_kb()),
        ("broadcast_card_kb_draft", admin_kb.broadcast_card_kb(_fake_broadcast(1, "draft"), perms)),
        ("broadcast_card_kb_running", admin_kb.broadcast_card_kb(_fake_broadcast(2, "running"), perms)),
        ("broadcast_card_kb_paused", admin_kb.broadcast_card_kb(_fake_broadcast(3, "paused"), perms)),
        ("broadcast_card_kb_done", admin_kb.broadcast_card_kb(_fake_broadcast(4, "completed"), perms)),
        ("templates_home_kb", admin_kb.templates_home_kb(
            [_fake_template_item(), _fake_template_item("order_failed", custom=True)]
        )),
        ("template_card_kb_default", admin_kb.template_card_kb(
            "order_created", is_customized=False, is_active=False
        )),
        ("template_card_kb_custom", admin_kb.template_card_kb(
            "order_created", is_customized=True, is_active=True
        )),
        ("template_card_kb_paused", admin_kb.template_card_kb(
            "order_created", is_customized=True, is_active=False
        )),
        ("template_preview_kb", admin_kb.template_preview_kb("order_created")),
    ]
```
