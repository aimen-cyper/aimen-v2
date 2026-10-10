# الكود الكامل — المرحلة 7 (نظام الدفع والشحن المتقدم)

كل ما في هذا الملف منسوخ آلياً من ملفات المشروع الفعلية وقت كتابة التقرير.

> الملفات الضخمة التي تغيّر منها قسم محدود تُعرض كمقتطف موسوم بوضوح؛ وما عداها كامل.

> الملفات غير المذكورة هنا لم تتغيّر عن المراحل 1–6.

## الفهرس

**قاعدة البيانات والمال**

- `database/migrations/0006_phase7_payments.sql` — 40 سطراً (جديد)
- `core/money.py` — 209 سطراً (مُحدَّث (مقتطف))
- `database/models.py` — 457 سطراً (مُحدَّث (مقتطف))
- `database/repositories/payments.py` — 365 سطراً (مُحدَّث)

**الخدمة المركزية للشحن**

- `services/payment_service.py` — 1048 سطراً (مُحدَّث)

**واجهة لوحة التحكم**

- `handlers/admin/payment_methods.py` — 628 سطراً (جديد)
- `handlers/admin/payments.py` — 558 سطراً (مُحدَّث)
- `keyboards/admin_kb.py` — 1159 سطراً (مُحدَّث (مقتطف))
- `handlers/admin/__init__.py` — 75 سطراً (مُحدَّث)
- `keyboards/callback_data.py` — 160 سطراً (مُحدَّث (مقتطف))

**واجهة المستخدم والنصوص**

- `handlers/user/deposit.py` — 326 سطراً (مُحدَّث (مقتطف))
- `texts/admin_ar.py` — 930 سطراً (مُحدَّث (مقتطف))
- `texts/ar.py` — 344 سطراً (مُحدَّث (مقتطف))
- `texts/templates.py` — 321 سطراً (مُحدَّث (مقتطف))
- `scripts/boot_check.py` — 198 سطراً (مُحدَّث (مقتطف))

**الاختبارات**

- `tests/unit/test_deposit_fees.py` — 85 سطراً (جديد)
- `tests/integration/test_payments_phase7.py` — 611 سطراً (جديد)

---

## قاعدة البيانات والمال

### `database/migrations/0006_phase7_payments.sql`  ·  جديد  ·  40 سطراً

رسوم لكل طريقة + لقطة الرسوم على كل طلب + فهرسا التصفية والبحث + إعدادان جديدان.

```sql
-- =====================================================================
-- الترحيل 0006 — المرحلة 7 (نظام الدفع والشحن المتقدم)
--
-- لماذا هذا الترحيل؟
--   1) كل طريقة تحويل لها كلفتها الحقيقية: محفظة إلكترونية تقتطع نسبة،
--      وحوالة بنكية تقتطع مبلغاً ثابتاً. بدون تسجيل هذه الرسوم كان الأدمن
--      يصحّح المبلغ يدوياً عند كل اعتماد — عمل متكرر ومصدر أخطاء.
--   2) الرسوم تتغيّر مع الزمن، والطلب القديم يجب أن يبقى محسوباً برسوم
--      يوم إرساله؛ لذلك تُخزَّن قيمة الرسوم داخل صف الطلب نفسه (لقطة).
--
-- ملاحظات تقنية:
--   • SQLite لا يسمح بإضافة CHECK مع ALTER TABLE ADD COLUMN، لذلك حدود
--     القيم مفروضة في طبقة الخدمة (`PaymentService`) وفي المستودع.
--   • لا حذف ولا إعادة بناء لأي جدول — إضافة أعمدة وفهارس فقط،
--     والطلبات القديمة تبقى برسوم = 0 وهو سلوكها الفعلي قبل هذه المرحلة.
-- =====================================================================

-- --------------------- رسوم طرق الشحن (نسبة + ثابت) -------------------- --
-- نقطة الأساس (basis point) = 1/100 من 1% ⇒ 250 تعني 2.5%.
-- اخترنا نقاط الأساس بدل الكسور العشرية لأن المال كله أعداد صحيحة في النظام.
ALTER TABLE payment_methods ADD COLUMN fee_percent_bp INTEGER NOT NULL DEFAULT 0;
ALTER TABLE payment_methods ADD COLUMN fee_fixed_units INTEGER NOT NULL DEFAULT 0;

-- ------------------- لقطة الرسوم المحسوبة على كل طلب ------------------- --
-- المبلغ المضاف للمستخدم عند الاعتماد = amount_units - fee_units.
ALTER TABLE payments ADD COLUMN fee_units INTEGER NOT NULL DEFAULT 0;

-- ------------------------- فهارس البحث والتصفية ------------------------ --
-- شاشة «طلبات الشحن» صارت تُصفّى بالحالة وتُبحث برقم العملية،
-- وتقرير الطرق يجمع حسب طريقة الدفع.
CREATE INDEX IF NOT EXISTS idx_payments_method    ON payments(method_id, status);
CREATE INDEX IF NOT EXISTS idx_payments_reference ON payments(transaction_reference);

-- ----------------------------- إعدادات جديدة --------------------------- --
INSERT OR IGNORE INTO settings (key, value, value_type, group_code, name_ar, description_ar, is_editable, updated_at) VALUES
    ('deposit_fee_visible', '1', 'bool', 'payments', 'إظهار رسوم طريقة الشحن للمستخدم',
     'عند التفعيل يرى المستخدم الرسوم والمبلغ الصافي قبل تأكيد طلب الشحن', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('payment_search_limit', '10', 'int', 'payments', 'عدد نتائج البحث في طلبات الشحن',
     'أقصى عدد طلبات تظهر عند البحث برقم العملية أو رقم الطلب', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
```

### `core/money.py`  ·  مُحدَّث (مقتطف)  ·  209 سطراً (المعروض: 47 سطراً)

`deposit_fee_units` و`net_after_fee`: حساب الرسوم بأعداد صحيحة ونقاط أساس، بلا أي float.

```python
def deposit_fee_units(amount_units: int, *, percent_bp: int = 0, fixed_units: int = 0) -> int:
    """
    حساب رسوم طريقة الشحن على مبلغ حوالة واحدة (أعداد صحيحة فقط).

    لماذا نقاط الأساس (bp)؟
        1 bp = 1/100 من 1%، فـ250 تعني 2.5%. هذا يسمح بكسور النِسب
        (مثل 1.75%) بلا أي استخدام لـfloat.

    المعادلة: الرسوم = (المبلغ × bp + 5000) ÷ 10000  +  الرسوم الثابتة
              (تقريب نصفي لأعلى بأعداد صحيحة)

    المدخلات:
        amount_units : مبلغ الحوالة بالنقاط.
        percent_bp   : النسبة بنقاط الأساس (0..10000).
        fixed_units  : رسوم ثابتة بالنقاط.

    المخرجات: الرسوم بالنقاط (لا تتجاوز أبداً مبلغ الحوالة نفسه).

    الاستثناءات:
        InvalidAmountError : مبلغ سالب أو نسبة/رسوم خارج المدى المسموح.
    """
    amount = int(amount_units)
    percent = int(percent_bp)
    fixed = int(fixed_units)
    if amount < 0:
        raise InvalidAmountError("مبلغ الحوالة لا يمكن أن يكون سالباً.")
    if not 0 <= percent <= MAX_FEE_PERCENT_BP:
        raise InvalidAmountError("نسبة الرسوم يجب أن تكون بين 0% و100%.")
    if fixed < 0:
        raise InvalidAmountError("الرسوم الثابتة لا يمكن أن تكون سالبة.")

    percent_part = (amount * percent + FEE_SCALE // 2) // FEE_SCALE  # تقريب نصفي لأعلى
    fee = percent_part + fixed
    return min(fee, amount)  # الرسوم لا تتجاوز الحوالة مهما كانت الإعدادات


def net_after_fee(amount_units: int, *, percent_bp: int = 0, fixed_units: int = 0) -> tuple[int, int]:
    """
    حساب (الرسوم، الصافي) لمبلغ حوالة بطريقة شحن محددة.

    المخرجات: tuple من (الرسوم بالنقاط، المبلغ الصافي الذي يستحقه المستخدم).

    ملاحظة: الصافي قد يكون صفراً إذا ابتلعت الرسوم المبلغ كله —
            وهي حالة يرفضها `PaymentService` قبل إنشاء الطلب.
    """
    fee = deposit_fee_units(amount_units, percent_bp=percent_bp, fixed_units=fixed_units)
    return fee, max(0, int(amount_units) - fee)
```

### `database/models.py`  ·  مُحدَّث (مقتطف)  ·  457 سطراً (المعروض: 56 سطراً)

`PaymentMethod.fee_*` و`has_fees` · `Payment.fee_units` و`net_units`.

```python
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
    fee_percent_bp: int = 0      # رسوم نسبية بنقاط الأساس (250 = 2.5%)
    fee_fixed_units: int = 0     # رسوم ثابتة بالنقاط تُخصم من كل حوالة

    @property
    def has_fees(self) -> bool:
        """هل لهذه الطريقة رسوم تُخصم من مبلغ الحوالة؟"""
        return self.fee_percent_bp > 0 or self.fee_fixed_units > 0


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
    fee_units: int = 0           # لقطة رسوم الطريقة وقت الإرسال (لا تتغير لاحقاً)

    @property
    def net_units(self) -> int:
        """
        المبلغ الصافي المتوقع إضافته للرصيد = المبلغ المحوَّل − الرسوم.

        يُستخدم كقيمة افتراضية في شاشة الاعتماد، ويبقى للأدمن حق تعديله.
        """
        return max(0, int(self.amount_units) - int(self.fee_units or 0))
```

### `database/repositories/payments.py`  ·  مُحدَّث  ·  365 سطراً

كتابة الرسوم، تصفية بالحالة، بحث، ترتيب الطرق، وتقرير أغنى.

```python
"""
مستودع المدفوعات — طلبات شحن الرصيد وطرق الدفع.

الحماية الأساسية هنا: تغيير حالة الدفعة مشروط بحالتها السابقة،
فلا يمكن اعتماد نفس الدفعة مرتين حتى لو ضغط الأدمن الزر مرتين.
"""

from __future__ import annotations

from typing import Any, Sequence

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
    "fee_percent_bp",
    "fee_fixed_units",
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
        fee_percent_bp: int = 0,
        fee_fixed_units: int = 0,
    ) -> PaymentMethod:
        """إضافة طريقة دفع جديدة (مع رسومها إن وُجدت)."""
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO payment_methods (code, name_ar, type, instructions_ar, account_details,
                                         min_amount_units, max_amount_units, requires_proof,
                                         sort_order, fee_percent_bp, fee_fixed_units,
                                         created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code, name_ar, type, instructions_ar, account_details, min_amount_units,
                max_amount_units, 1 if requires_proof else 0, sort_order,
                fee_percent_bp, fee_fixed_units, now, now,
            ),
        )
        row = await tx.fetchone("SELECT * FROM payment_methods WHERE id = ?", (result.lastrowid,))
        method = PaymentMethod.from_row(row)
        assert method is not None
        return method

    async def update_fields(self, tx: Tx, method_id: int, **fields: Any) -> bool:
        """تعديل بيانات طريقة دفع."""
        return await self._update_by_id(tx, "payment_methods", method_id, fields, _METHOD_FIELDS)

    async def next_sort_order(self) -> int:
        """ترتيب العرض التالي (تُضاف الطريقة الجديدة في آخر القائمة)."""
        value = await self.db.fetchval(
            "SELECT COALESCE(MAX(sort_order), 0) FROM payment_methods", default=0
        )
        return int(value) + 10

    async def neighbour(self, method: PaymentMethod, *, up: bool) -> PaymentMethod | None:
        """
        الطريقة المجاورة في ترتيب العرض (الأعلى أو الأدنى مباشرة).

        تُستخدم لتبديل الترتيب من اللوحة بزرَّي ▲/▼ بلا إدخال أرقام يدوية.
        """
        if up:
            sql = """
                SELECT * FROM payment_methods
                 WHERE (sort_order < ?) OR (sort_order = ? AND id < ?)
                 ORDER BY sort_order DESC, id DESC LIMIT 1
            """
        else:
            sql = """
                SELECT * FROM payment_methods
                 WHERE (sort_order > ?) OR (sort_order = ? AND id > ?)
                 ORDER BY sort_order, id LIMIT 1
            """
        row = await self.db.fetchone(sql, (method.sort_order, method.sort_order, method.id))
        return PaymentMethod.from_row(row)


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

    async def count_pending_by_user(self, user_id: int) -> int:
        """عدد طلبات الشحن المعلّقة لمستخدم واحد (لمنع تكديس الطلبات)."""
        return await self.count("payments", "user_id = ? AND status = 'pending'", (user_id,))

    async def usage_by_method(self) -> list[Any]:
        """
        إحصاء استخدام طرق الشحن لكل طريقة على حدة.

        المخرجات: صفوف فيها method_id و name_ar و is_active و approved_count و
                  pending_count و total_units (المضاف فعلاً) و fee_units (الرسوم المحصّلة).

        ملاحظة: `LEFT JOIN` مقصود — الطريقة التي لم تُستخدم بعد تظهر بأصفار
        لا أن تختفي، وإلا ظن الأدمن أنها غير موجودة.
        """
        return await self.db.fetchall(
            """
            SELECT m.id        AS method_id,
                   m.name_ar   AS name_ar,
                   m.is_active AS is_active,
                   COUNT(ap.id) AS approved_count,
                   COALESCE(SUM(COALESCE(ap.credited_units, ap.amount_units)), 0) AS total_units,
                   COALESCE(SUM(ap.fee_units), 0) AS fee_units,
                   (SELECT COUNT(*) FROM payments pp
                     WHERE pp.method_id = m.id AND pp.status = 'pending') AS pending_count
              FROM payment_methods m
              LEFT JOIN payments ap ON ap.method_id = m.id AND ap.status = 'approved'
             GROUP BY m.id
             ORDER BY total_units DESC, m.sort_order
            """
        )

    async def list_filtered(
        self, *, statuses: Sequence[str] | None = None, limit: int = 10, offset: int = 0
    ) -> list[Payment]:
        """
        قائمة طلبات الشحن حسب الحالة (أو كلها عند عدم تمرير حالات).

        الترتيب: المعلّق الأقدم أولاً (طابور مراجعة عادل)، وبقية الحالات
        الأحدث أولاً (آخر ما عولج يهم أكثر).
        """
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            order = "id" if list(statuses) == ["pending"] else "id DESC"
            rows = await self.db.fetchall(
                f"SELECT * FROM payments WHERE status IN ({placeholders}) "
                f"ORDER BY {order} LIMIT ? OFFSET ?",
                (*statuses, limit, offset),
            )
        else:
            rows = await self.db.fetchall(
                "SELECT * FROM payments ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
            )
        return Payment.from_rows(rows)

    async def count_filtered(self, *, statuses: Sequence[str] | None = None) -> int:
        """عدد طلبات الشحن ضمن حالات محددة (لحساب صفحات القائمة)."""
        if not statuses:
            return await self.count("payments")
        placeholders = ", ".join("?" for _ in statuses)
        return await self.count("payments", f"status IN ({placeholders})", tuple(statuses))

    async def search(self, term: str, *, limit: int = 10) -> list[Payment]:
        """
        بحث الأدمن عن طلب شحن برقم العملية (كلياً أو جزئياً) أو برقم الطلب.

        المدخلات: term نص البحث كما كتبه الأدمن (نُظّف قبل الوصول هنا).
        المخرجات: أحدث الطلبات المطابقة (محدودة بـlimit).
        """
        like = f"%{term}%"
        payment_id = int(term) if term.isdigit() else -1
        rows = await self.db.fetchall(
            """
            SELECT * FROM payments
             WHERE (transaction_reference IS NOT NULL AND transaction_reference LIKE ?)
                OR id = ?
             ORDER BY id DESC LIMIT ?
            """,
            (like, payment_id, limit),
        )
        return Payment.from_rows(rows)

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
        fee_units: int = 0,
    ) -> Payment:
        """إنشاء طلب شحن جديد بحالة pending (مع لقطة الرسوم وقت الإرسال)."""
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO payments (user_id, method_id, amount_units, transaction_reference,
                                  proof_file_id, proof_file_type, user_note, expires_at,
                                  fee_units, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, method_id, amount_units, transaction_reference, proof_file_id,
                proof_file_type, user_note, expires_at, max(0, int(fee_units)), now, now,
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

---

## الخدمة المركزية للشحن

### `services/payment_service.py`  ·  مُحدَّث  ·  1048 سطراً

قلب المرحلة: حساب الرسوم وتخزينها، اعتماد الصافي، إدارة الطرق بتحقق كامل، الترتيب، التصفية، البحث، التقرير.

```python
"""
خدمة الشحن (الإيداع) — من إرسال إثبات التحويل حتى إضافة الرصيد.

المسؤوليات:
    • عرض طرق الشحن المفعّلة وحدودها.
    • إنشاء طلب شحن بعد تحقق كامل (مبلغ، رقم حوالة، إثبات، حدود، تكرار).
    • اعتماد/رفض الطلب من الأدمن مع إضافة الرصيد عبر المحفظة المركزية فقط.
    • انتهاء صلاحية الطلبات القديمة تلقائياً.
    • إدارة طرق الدفع من لوحة الأدمن.

قواعد لا تُكسر:
    • الاعتماد يغيّر الحالة بشكل مشروط (`expected_status='pending'`) قبل إضافة أي رصيد،
      فلو ضغط أدمنان الزر في نفس اللحظة يُضاف الرصيد مرة واحدة فقط.
    • إضافة الرصيد تتم حصراً عبر `WalletService.credit_from_payment` بمرجع فريد.
    • رقم الحوالة لا يُقبل مرتين (كشف إعادة استخدام إثبات الدفع).
    • كل إجراء أدمن يُسجَّل في سجل التدقيق داخل نفس المعاملة.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from core.enums import NotificationType, PaymentStatus
from core.money import MAX_FEE_PERCENT_BP, format_units, net_after_fee
from core.payment_state import assert_transition, is_final
from core.permissions import Permission
from database.database import Database
from database.models import Payment, PaymentMethod, Transaction, User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.notification_service import NotificationService
from services.settings_service import SettingsService
from services.wallet_service import WalletService
from texts import templates
from core.exceptions import (
    DuplicateOperationError,
    PaymentError,
    ValidationError,
)
from utils.datetime_utils import iso_plus_seconds, utc_now_iso
from utils.logging_setup import get_logger
from utils.security import sanitize
from utils.validators import (
    clean_text,
    parse_amount_units,
    validate_amount_range,
    validate_transaction_reference,
)

logger = get_logger(__name__)

#: أقصى طول لملاحظة المستخدم على طلب الشحن
MAX_USER_NOTE = 300

#: أقصى طول لتعليمات طريقة الشحن كما تُعرض للمستخدم
MAX_METHOD_INSTRUCTIONS = 600

#: أقصى طول لبيانات الحساب (رقم محفظة/حساب بنكي/عنوان محفظة رقمية)
MAX_METHOD_ACCOUNT = 300

#: أنواع طرق الشحن المدعومة في المخطط (قيد CHECK في جدول payment_methods)
METHOD_TYPES: tuple[str, ...] = ("manual", "crypto", "gateway")

#: الحقول التي يسمح هذا المستوى بتعديلها على طريقة الشحن
#: (الكود لا يُعدَّل أبداً: معرّف داخلي تُشير إليه السجلات التاريخية)
EDITABLE_METHOD_FIELDS: frozenset[str] = frozenset(
    {
        "name_ar",
        "instructions_ar",
        "account_details",
        "type",
        "min_amount_units",
        "max_amount_units",
        "requires_proof",
        "sort_order",
        "fee_percent_bp",
        "fee_fixed_units",
    }
)


class PaymentService:
    """دورة حياة طلب الشحن كاملة."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        wallet: WalletService,
        notifications: NotificationService,
        audit: AuditService,
        auth: AuthService,
    ) -> None:
        """تهيئة الخدمة بالاعتماديات المطلوبة."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.wallet = wallet
        self.notifications = notifications
        self.audit = audit
        self.auth = auth

    # ===================================================================== #
    #                              طرق الشحن                                #
    # ===================================================================== #

    async def active_methods(self) -> list[PaymentMethod]:
        """طرق الشحن المفعّلة كما تُعرض للمستخدم."""
        return await self.repos.payment_methods.list_all(active_only=True)

    async def all_methods(self, actor: User) -> list[PaymentMethod]:
        """كل طرق الشحن (للوحة الأدمن) — تتطلب صلاحية إدارة طرق الدفع."""
        await self.auth.require_permission(actor, Permission.PAYMENTS_METHODS)
        return await self.repos.payment_methods.list_all()

    async def get_method(self, method_id: int, *, require_active: bool = True) -> PaymentMethod:
        """
        جلب طريقة شحن بالمعرف.

        الاستثناءات:
            ValidationError : الطريقة غير موجودة أو متوقفة.
        """
        method = await self.repos.payment_methods.get(method_id)
        if method is None:
            raise ValidationError(
                f"طريقة الدفع {method_id} غير موجودة",
                user_message="❌ طريقة الشحن غير متاحة.",
            )
        if require_active and not method.is_active:
            raise ValidationError(
                f"طريقة الدفع {method_id} متوقفة",
                user_message="⚠️ طريقة الشحن هذه متوقفة حالياً، اختر طريقة أخرى.",
            )
        return method

    async def method_limits(self, method: PaymentMethod) -> tuple[int, int]:
        """
        الحدان الأدنى والأقصى الفعليان للشحن بهذه الطريقة.

        القاعدة: حد الطريقة إن وُجد، وإلا الحد العام من الإعدادات.
        """
        min_global = await self.settings.get_money_units("min_deposit_units", 0)
        max_global = await self.settings.get_money_units("max_deposit_units", 0)
        min_units = method.min_amount_units or min_global
        max_units = method.max_amount_units or max_global
        return min_units, max_units

    async def limits_text(self, method: PaymentMethod) -> str:
        """نص جاهز يوضّح حدود الشحن للمستخدم."""
        min_units, max_units = await self.method_limits(method)
        symbol = await self.settings.money_symbol()
        parts = []
        if min_units:
            parts.append(f"الحد الأدنى: {format_units(min_units, symbol=symbol)}")
        if max_units:
            parts.append(f"الحد الأقصى: {format_units(max_units, symbol=symbol)}")
        return " • ".join(parts) if parts else "لا توجد حدود محددة"

    # --------------------------- رسوم طرق الشحن -------------------------- #

    def fee_for(self, method: PaymentMethod, amount_units: int) -> tuple[int, int]:
        """
        حساب رسوم طريقة الشحن على مبلغ معيّن.

        المدخلات:
            method       : طريقة الشحن بقيم رسومها الحالية.
            amount_units : المبلغ الذي حوّله المستخدم فعلاً (بالنقاط).

        المخرجات: (الرسوم بالنقاط، الصافي الذي يستحقه المستخدم).

        ملاحظة مهمة: القيمة تُحسب وقت إنشاء الطلب وتُخزَّن داخل الطلب،
        فتغيير رسوم الطريقة لاحقاً لا يمس أي طلب قديم.
        """
        return net_after_fee(
            amount_units,
            percent_bp=int(method.fee_percent_bp or 0),
            fixed_units=int(method.fee_fixed_units or 0),
        )

    async def fee_text(self, method: PaymentMethod) -> str:
        """
        وصف رسوم الطريقة بالعربية للعرض في الواجهتين (أو نص «بلا رسوم»).

        المخرجات: مثل «رسوم التحويل: 2.50% + 100.00 ﷼» أو «بلا رسوم».
        """
        if not method.has_fees:
            return "بلا رسوم"
        symbol = await self.settings.money_symbol()
        parts: list[str] = []
        if method.fee_percent_bp:
            percent = Decimal(int(method.fee_percent_bp)) / Decimal(100)
            parts.append(f"{percent.normalize():f}%")
        if method.fee_fixed_units:
            parts.append(format_units(int(method.fee_fixed_units), symbol=symbol))
        return " + ".join(parts)

    async def fee_visible_to_user(self) -> bool:
        """هل تُعرض الرسوم والمبلغ الصافي للمستخدم؟ (إعداد قابل للتحكم)."""
        return await self.settings.get_bool("deposit_fee_visible", True)

    # ===================================================================== #
    #                           إنشاء طلب الشحن                             #
    # ===================================================================== #

    async def create_payment(
        self,
        user: User,
        *,
        method_id: int,
        raw_amount: str | int,
        transaction_reference: str | None = None,
        proof_file_id: str | None = None,
        proof_file_type: str | None = None,
        user_note: str | None = None,
    ) -> Payment:
        """
        إنشاء طلب شحن جديد بحالة «بانتظار المراجعة».

        المخرجات: طلب الشحن بعد إنشائه.

        الاستثناءات:
            UserBannedError · MaintenanceModeError : الحساب محظور أو النظام في صيانة.
            ValidationError                        : طريقة متوقفة · إثبات ناقص · تجاوز عدد الطلبات المعلّقة.
            InvalidAmountError                     : مبلغ غير صالح أو خارج الحدود.
            DuplicateOperationError                : رقم الحوالة مستخدم في طلب سابق.
        """
        await self.auth.guard(user)
        method = await self.get_method(method_id)

        amount_units = parse_amount_units(raw_amount)
        min_units, max_units = await self.method_limits(method)
        validate_amount_range(
            amount_units, min_units=min_units, max_units=max_units, label="مبلغ الشحن"
        )

        reference = validate_transaction_reference(
            transaction_reference, required=bool(method.requires_proof)
        )
        if method.requires_proof and not proof_file_id and not reference:
            raise ValidationError(
                "إثبات الدفع مطلوب",
                user_message="❌ أرسل صورة إيصال التحويل أو رقم العملية.",
            )

        if reference:
            duplicate = await self.repos.payments.find_duplicate_reference(reference)
            if duplicate is not None:
                raise DuplicateOperationError(
                    f"رقم الحوالة {reference} مستخدم في الطلب {duplicate.id}",
                    user_message=(
                        "⚠️ رقم العملية هذا مُستخدم في طلب شحن سابق. "
                        "تواصل مع الدعم إن كان هناك خطأ."
                    ),
                )

        await self._check_pending_limit(user)

        # رسوم الطريقة تُحسب الآن وتُخزَّن كلقطة داخل الطلب (لا تتأثر بتغيّرها لاحقاً)
        fee_units, net_units = self.fee_for(method, amount_units)
        if net_units <= 0:
            raise ValidationError(
                f"رسوم الطريقة {method.code} تبتلع كامل المبلغ {amount_units}",
                user_message=(
                    "❌ المبلغ أصغر من رسوم هذه الطريقة ولن يُضاف لك أي رصيد. "
                    "ارفع المبلغ أو اختر طريقة أخرى."
                ),
            )

        note = (
            clean_text(user_note, field="الملاحظة", max_length=MAX_USER_NOTE, min_length=0)
            if user_note
            else None
        )
        expiry_hours = await self.settings.get_int("payment_expiry_hours", 48)
        symbol = await self.settings.money_symbol()

        async with self.db.transaction() as tx:
            payment = await self.repos.payments.create(
                tx,
                user_id=user.id,
                method_id=method.id,
                amount_units=amount_units,
                transaction_reference=reference,
                proof_file_id=proof_file_id,
                proof_file_type=proof_file_type,
                user_note=note,
                expires_at=iso_plus_seconds(expiry_hours * 3600) if expiry_hours > 0 else None,
                fee_units=fee_units,
            )

            title, message = templates.payment_received(
                payment_id=payment.id,
                amount_units=amount_units,
                symbol=symbol,
                fee_units=fee_units,
                net_units=net_units,
            )
            await self.notifications.notify_payment(
                tx,
                user_id=user.id,
                payment_id=payment.id,
                event=NotificationType.PAYMENT_RECEIVED,
                title=title,
                message=message,
            )

            admin_title, admin_message = templates.admin_new_payment(
                payment_id=payment.id,
                amount_units=amount_units,
                user_label=user.display_name,
                symbol=symbol,
            )
            await self.notifications.notify_admins(
                tx,
                permission=Permission.PAYMENTS_APPROVE,
                token=f"payment:{payment.id}:new",
                title=admin_title,
                message=admin_message,
            )

        logger.info(
            "طلب شحن جديد #%s من المستخدم %s بمبلغ %s عبر %s",
            payment.id, user.id, amount_units, method.code,
        )
        return payment

    async def _check_pending_limit(self, user: User) -> None:
        """
        منع تكديس طلبات شحن معلّقة من نفس المستخدم.

        الاستثناءات: ValidationError عند تجاوز العدد المسموح.
        """
        max_pending = await self.settings.get_int("max_pending_payments_per_user", 3)
        if max_pending <= 0:
            return
        pending = await self.repos.payments.count_pending_by_user(user.id)
        if pending >= max_pending:
            raise ValidationError(
                f"المستخدم {user.id} لديه {pending} طلب شحن معلّق",
                user_message=(
                    f"⏳ لديك {pending} طلب شحن بانتظار المراجعة. "
                    "انتظر مراجعتها قبل إرسال طلب جديد."
                ),
            )

    # ===================================================================== #
    #                          القراءة والعرض                               #
    # ===================================================================== #

    async def get_for_user(self, user: User, payment_id: int) -> Payment:
        """
        جلب طلب شحن يخص المستخدم نفسه.

        الاستثناءات: PaymentError إذا لم يوجد أو كان لمستخدم آخر.
        """
        payment = await self.repos.payments.get(payment_id)
        if payment is None or payment.user_id != user.id:
            raise PaymentError(
                f"طلب الشحن {payment_id} غير متاح للمستخدم {user.id}",
                user_message="❌ لم يتم العثور على طلب الشحن.",
            )
        return payment

    async def list_for_user(self, user: User, *, limit: int = 10, offset: int = 0) -> list[Payment]:
        """آخر طلبات الشحن للمستخدم."""
        return await self.repos.payments.list_by_user(user.id, limit=limit, offset=offset)

    async def admin_get(self, actor: User, payment_id: int) -> Payment:
        """
        جلب طلب شحن من لوحة الأدمن.

        الاستثناءات: PermissionDeniedError · PaymentError
        """
        await self.auth.require_permission(actor, Permission.PAYMENTS_VIEW)
        payment = await self.repos.payments.get(payment_id)
        if payment is None:
            raise PaymentError(
                f"طلب الشحن {payment_id} غير موجود", user_message="❌ طلب الشحن غير موجود."
            )
        return payment

    async def pending(self, actor: User, *, limit: int = 10, offset: int = 0) -> list[Payment]:
        """قائمة طلبات الشحن بانتظار المراجعة."""
        await self.auth.require_permission(actor, Permission.PAYMENTS_VIEW)
        return await self.repos.payments.list_pending(limit=limit, offset=offset)

    async def pending_count(self) -> int:
        """عدد طلبات الشحن المعلّقة (لشارة لوحة الأدمن)."""
        return await self.repos.payments.count_pending()

    async def admin_list(
        self,
        actor: User,
        *,
        statuses: Sequence[str] | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[Payment]:
        """
        قائمة طلبات الشحن للوحة الأدمن مُصفّاة بالحالة.

        المدخلات:
            statuses : الحالات المطلوبة (None أو فارغة = كل الحالات).

        الاستثناءات: PermissionDeniedError إن لم يملك `payments.view`.
        """
        await self.auth.require_permission(actor, Permission.PAYMENTS_VIEW)
        return await self.repos.payments.list_filtered(
            statuses=statuses, limit=limit, offset=offset
        )

    async def admin_count(self, actor: User, *, statuses: Sequence[str] | None = None) -> int:
        """عدد طلبات الشحن ضمن الحالات المحددة (لحساب الصفحات)."""
        await self.auth.require_permission(actor, Permission.PAYMENTS_VIEW)
        return await self.repos.payments.count_filtered(statuses=statuses)

    async def admin_search(self, actor: User, term: str) -> list[Payment]:
        """
        البحث عن طلب شحن برقم العملية أو برقم الطلب.

        لماذا؟ أكثر سؤال يصل الدعم: «حوّلت ولم يصلني الرصيد، رقم العملية كذا».
        البحث يختصر الوصول للطلب بدل التنقل بين الصفحات.

        الاستثناءات:
            PermissionDeniedError : لا يملك `payments.view`.
            ValidationError       : نص بحث قصير جداً.
        """
        await self.auth.require_permission(actor, Permission.PAYMENTS_VIEW)
        clean_term = clean_text(term, field="نص البحث", max_length=64, min_length=2)
        limit = await self.settings.get_int("payment_search_limit", 10)
        return await self.repos.payments.search(clean_term, limit=max(1, min(50, limit)))

    async def approved_total_units(self, start_iso: str, end_iso: str) -> int:
        """مجموع المبالغ المعتمدة بين تاريخين (للإحصائيات)."""
        return await self.repos.payments.sum_approved_between(start_iso, end_iso)

    # ===================================================================== #
    #                        الاعتماد والرفض والإلغاء                       #
    # ===================================================================== #

    async def approve(
        self,
        actor: User,
        payment_id: int,
        *,
        credited_units: int | None = None,
        admin_note: str | None = None,
    ) -> Transaction:
        """
        اعتماد طلب شحن وإضافة الرصيد للمستخدم.

        المدخلات:
            credited_units : المبلغ المعتمد فعلياً إن اختلف عن الافتراضي (تحويل ناقص مثلاً).
                             الافتراضي = المبلغ المحوَّل − رسوم الطريقة المسجّلة على الطلب.

        المخرجات: الحركة المالية التي أُنشئت.

        الاستثناءات:
            PermissionDeniedError       : لا يملك صلاحية `payments.approve`.
            PaymentError                : الطلب غير موجود.
            InvalidStateTransitionError : الطلب ليس بانتظار المراجعة.
            DuplicateOperationError     : عالجه أدمن آخر قبل لحظات.
            InvalidAmountError          : مبلغ اعتماد غير صالح.
        """
        await self.auth.require_permission(
            actor, Permission.PAYMENTS_APPROVE, context=f"payment:{payment_id}"
        )
        payment = await self._load_pending(payment_id, PaymentStatus.APPROVED)

        # الافتراضي هو الصافي بعد رسوم الطريقة المحفوظة على الطلب نفسه
        default_units = payment.net_units
        amount_units = int(credited_units) if credited_units is not None else default_units
        if amount_units <= 0:
            raise ValidationError(
                f"مبلغ اعتماد غير صالح: {amount_units}",
                user_message="❌ المبلغ المعتمد يجب أن يكون أكبر من صفر.",
            )
        note = sanitize(admin_note)[:300] if admin_note else None
        if payment.fee_units:
            fee_note = f"رسوم الطريقة {payment.fee_units} على مبلغ {payment.amount_units}"
            note = f"{note} | {fee_note}" if note else fee_note
        if amount_units != default_units:
            diff_note = f"اعتُمد {amount_units} بدل {default_units}"
            note = f"{note} | {diff_note}" if note else diff_note

        symbol = await self.settings.money_symbol()
        async with self.db.transaction() as tx:
            changed = await self.repos.payments.set_status(
                tx,
                payment_id,
                new_status=PaymentStatus.APPROVED,
                expected_status=PaymentStatus.PENDING,
                admin_id=actor.id,
                credited_units=amount_units,
                admin_note=note,
            )
            if not changed:
                raise DuplicateOperationError(
                    f"طلب الشحن {payment_id} عولج مسبقاً",
                    user_message="⚠️ هذا الطلب تمت معالجته بالفعل (ربما من أدمن آخر).",
                )

            transaction = await self.wallet.credit_from_payment(
                tx,
                user_id=payment.user_id,
                payment_id=payment.id,
                amount_units=amount_units,
                actor_id=actor.id,
            )

            await self.audit.log(
                tx,
                action="payments.approve",
                admin_id=actor.id,
                target_type="payment",
                target_id=payment_id,
                before={
                    "status": payment.status,
                    "amount_units": payment.amount_units,
                    "fee_units": payment.fee_units,
                },
                after={"status": PaymentStatus.APPROVED, "credited_units": amount_units},
                details={"note": note},
            )

            title, message = templates.payment_approved(
                payment_id=payment.id,
                credited_units=amount_units,
                new_balance_units=transaction.balance_after_units,
                symbol=symbol,
            )
            await self.notifications.notify_payment(
                tx,
                user_id=payment.user_id,
                payment_id=payment.id,
                event=NotificationType.PAYMENT_APPROVED,
                title=title,
                message=message,
            )

        logger.info(
            "اعتمد الأدمن %s طلب الشحن #%s للمستخدم %s بمبلغ %s",
            actor.id, payment_id, payment.user_id, amount_units,
        )
        return transaction

    async def reject(self, actor: User, payment_id: int, reason: str) -> bool:
        """
        رفض طلب شحن مع سبب إجباري يصل للمستخدم.

        المخرجات: True عند الرفض الفعلي.

        الاستثناءات:
            PermissionDeniedError · PaymentError · InvalidStateTransitionError
            ValidationError         : السبب قصير جداً.
            DuplicateOperationError : عولج الطلب مسبقاً.
        """
        await self.auth.require_permission(
            actor, Permission.PAYMENTS_REJECT, context=f"payment:{payment_id}"
        )
        clean_reason = (reason or "").strip()
        if len(clean_reason) < 3:
            raise ValidationError(
                "سبب الرفض مطلوب", user_message="❌ اكتب سبب الرفض ليظهر للمستخدم."
            )
        clean_reason = sanitize(clean_reason)[:300]
        payment = await self._load_pending(payment_id, PaymentStatus.REJECTED)

        async with self.db.transaction() as tx:
            changed = await self.repos.payments.set_status(
                tx,
                payment_id,
                new_status=PaymentStatus.REJECTED,
                expected_status=PaymentStatus.PENDING,
                admin_id=actor.id,
                reject_reason=clean_reason,
            )
            if not changed:
                raise DuplicateOperationError(
                    f"طلب الشحن {payment_id} عولج مسبقاً",
                    user_message="⚠️ هذا الطلب تمت معالجته بالفعل.",
                )

            await self.audit.log(
                tx,
                action="payments.reject",
                admin_id=actor.id,
                target_type="payment",
                target_id=payment_id,
                before={"status": payment.status},
                after={"status": PaymentStatus.REJECTED, "reason": clean_reason},
            )

            title, message = templates.payment_rejected(
                payment_id=payment.id, reason=clean_reason
            )
            await self.notifications.notify_payment(
                tx,
                user_id=payment.user_id,
                payment_id=payment.id,
                event=NotificationType.PAYMENT_REJECTED,
                title=title,
                message=message,
            )

        logger.info("رفض الأدمن %s طلب الشحن #%s: %s", actor.id, payment_id, clean_reason)
        return True

    async def cancel_by_user(self, user: User, payment_id: int) -> bool:
        """
        إلغاء المستخدم لطلب شحن أرسله بالخطأ (ما دام لم يُراجَع بعد).

        المخرجات: True عند الإلغاء الفعلي.

        الاستثناءات:
            PaymentError · InvalidStateTransitionError
        """
        payment = await self.get_for_user(user, payment_id)
        assert_transition(payment.status, PaymentStatus.CANCELLED, payment_id=payment_id)

        async with self.db.transaction() as tx:
            changed = await self.repos.payments.set_status(
                tx,
                payment_id,
                new_status=PaymentStatus.CANCELLED,
                expected_status=PaymentStatus.PENDING,
                admin_note="ألغاه المستخدم",
            )
        if changed:
            logger.info("ألغى المستخدم %s طلب الشحن #%s", user.id, payment_id)
        return changed

    async def _load_pending(self, payment_id: int, target_status: str) -> Payment:
        """
        جلب طلب شحن والتأكد من صلاحية الانتقال إلى الحالة المطلوبة.

        الاستثناءات:
            PaymentError                : الطلب غير موجود.
            InvalidStateTransitionError : الحالة الحالية لا تسمح بالإجراء.
        """
        payment = await self.repos.payments.get(payment_id)
        if payment is None:
            raise PaymentError(
                f"طلب الشحن {payment_id} غير موجود", user_message="❌ طلب الشحن غير موجود."
            )
        assert_transition(payment.status, target_status, payment_id=payment_id)
        return payment

    # ===================================================================== #
    #                          انتهاء الصلاحية                              #
    # ===================================================================== #

    async def expire_due(self, *, limit: int = 50) -> int:
        """
        تعليم طلبات الشحن المنتهية صلاحيتها (job دوري) وإشعار أصحابها.

        المخرجات: عدد الطلبات التي انتهت صلاحيتها.
        """
        expired = await self.repos.payments.list_expired_pending(limit=limit)
        if not expired:
            return 0

        count = 0
        for payment in expired:
            if is_final(payment.status):
                continue
            async with self.db.transaction() as tx:
                changed = await self.repos.payments.set_status(
                    tx,
                    payment.id,
                    new_status=PaymentStatus.EXPIRED,
                    expected_status=PaymentStatus.PENDING,
                    admin_note="انتهت صلاحية الطلب تلقائياً",
                )
                if not changed:
                    continue
                title, message = templates.payment_expired(payment_id=payment.id)
                await self.notifications.notify_payment(
                    tx,
                    user_id=payment.user_id,
                    payment_id=payment.id,
                    event=NotificationType.SYSTEM,
                    title=title,
                    message=message,
                )
            count += 1

        if count:
            logger.info("انتهت صلاحية %s طلب شحن", count)
        return count

    # ===================================================================== #
    #                        إدارة طرق الدفع (أدمن)                         #
    # ===================================================================== #

    async def suggest_method_code(self, name_ar: str) -> str:
        """
        اقتراح كود إنجليزي فريد لطريقة شحن انطلاقاً من اسمها العربي.

        لماذا؟ الكود معرّف داخلي تُشير إليه السجلات، ولا قيمة في إجبار الأدمن
        على اختراعه. نشتق ما أمكن من الاسم، وإلا نستخدم ترقيماً تسلسلياً،
        ثم نضمن عدم التكرار بإضافة لاحقة رقمية.
        """
        ascii_part = "".join(
            char if char.isascii() and char.isalnum() else "_" for char in name_ar.lower()
        ).strip("_")
        base = "_".join(filter(None, ascii_part.split("_")))[:24]
        if not base:
            existing = len(await self.repos.payment_methods.list_all())
            base = f"method_{existing + 1}"

        candidate = base
        suffix = 2
        while await self.repos.payment_methods.get_by_code(candidate) is not None:
            candidate = f"{base}_{suffix}"[:32]
            suffix += 1
        return candidate

    @staticmethod
    def _clean_multiline(value: str | None, *, field: str, max_length: int) -> str:
        """
        تنظيف نص متعدد الأسطر مع الحفاظ على الأسطر.

        لماذا لا نستخدم `clean_text`؟ لأنها تدمج كل شيء في سطر واحد، وتعليمات
        التحويل تفقد معناها بلا أسطر («1- حوّل … 2- أرسل الإيصال»).

        الاستثناءات: ValidationError إذا تجاوز النص الطول المسموح.
        """
        kept: list[str] = []
        for raw_line in (value or "").splitlines():
            line = " ".join(raw_line.split())
            if not line and (not kept or not kept[-1]):
                continue  # لا نسمح بأكثر من سطر فارغ متتالٍ
            kept.append(line)
        text = "\n".join(kept).strip()
        if len(text) > max_length:
            raise ValidationError(
                f"حقل {field} أطول من {max_length}",
                user_message=f"❌ {field} طويل جداً (الحد الأقصى {max_length} حرفاً).",
            )
        return text

    def _validated_method_fields(self, fields: dict[str, Any]) -> dict[str, Any]:
        """
        تنقية وتحقق قيم حقول طريقة الشحن قبل كتابتها في قاعدة البيانات.

        لماذا هنا؟ المخطط في SQLite لا يستطيع فرض CHECK على الأعمدة المضافة
        لاحقاً (رسوم المرحلة 7)، فالخدمة هي الحارس الوحيد لهذه القيم.

        الاستثناءات:
            ValidationError : حقل غير مسموح بتعديله أو قيمة خارج المدى.
        """
        clean: dict[str, Any] = {}
        for key, value in fields.items():
            if key not in EDITABLE_METHOD_FIELDS:
                raise ValidationError(
                    f"حقل غير قابل للتعديل في طريقة الدفع: {key}",
                    user_message="❌ لا يمكن تعديل هذا الحقل.",
                )
            if key == "name_ar":
                clean[key] = clean_text(value, field="اسم الطريقة", max_length=64)
            elif key == "instructions_ar":
                clean[key] = self._clean_multiline(
                    value, field="التعليمات", max_length=MAX_METHOD_INSTRUCTIONS
                )
            elif key == "account_details":
                clean[key] = self._clean_multiline(
                    value, field="بيانات الحساب", max_length=MAX_METHOD_ACCOUNT
                )
            elif key == "type":
                if value not in METHOD_TYPES:
                    raise ValidationError(
                        f"نوع طريقة دفع غير مدعوم: {value}",
                        user_message="❌ نوع الطريقة غير مدعوم.",
                    )
                clean[key] = value
            elif key == "fee_percent_bp":
                number = int(value)
                if not 0 <= number <= MAX_FEE_PERCENT_BP:
                    raise ValidationError(
                        f"نسبة رسوم خارج المدى: {number}",
                        user_message="❌ نسبة الرسوم يجب أن تكون بين 0% و100%.",
                    )
                clean[key] = number
            elif key in {"fee_fixed_units", "min_amount_units"}:
                number = int(value)
                if number < 0:
                    raise ValidationError(
                        f"قيمة سالبة في الحقل {key}",
                        user_message="❌ القيمة لا يمكن أن تكون سالبة.",
                    )
                clean[key] = number
            elif key == "max_amount_units":
                clean[key] = None if value in (None, 0, "0") else int(value)
                if clean[key] is not None and clean[key] <= 0:
                    raise ValidationError(
                        "حد أقصى غير صالح", user_message="❌ الحد الأقصى يجب أن يكون أكبر من صفر."
                    )
            elif key == "requires_proof":
                clean[key] = 1 if value else 0
            elif key == "sort_order":
                clean[key] = max(0, int(value))
        return clean

    async def create_method(
        self,
        actor: User,
        *,
        code: str | None = None,
        name_ar: str,
        instructions_ar: str = "",
        account_details: str = "",
        type: str = "manual",
        min_amount_units: int = 0,
        max_amount_units: int | None = None,
        requires_proof: bool = True,
        sort_order: int | None = None,
        fee_percent_bp: int = 0,
        fee_fixed_units: int = 0,
    ) -> PaymentMethod:
        """
        إضافة طريقة شحن جديدة (صلاحية `payments.methods`).

        المدخلات:
            code           : كود داخلي؛ يُشتق تلقائياً من الاسم إن لم يُمرَّر.
            sort_order     : ترتيب العرض؛ الافتراضي آخر القائمة.
            fee_percent_bp : رسوم نسبية بنقاط الأساس (250 = 2.5%).

        الاستثناءات:
            PermissionDeniedError · ValidationError (كود مكرر أو بيانات غير صالحة)
        """
        await self.auth.require_permission(actor, Permission.PAYMENTS_METHODS)
        clean_name = clean_text(name_ar, field="اسم الطريقة", max_length=64)
        if code:
            clean_code = (
                clean_text(code, field="كود الطريقة", max_length=32).lower().replace(" ", "_")
            )
        else:
            clean_code = await self.suggest_method_code(clean_name)

        if await self.repos.payment_methods.get_by_code(clean_code) is not None:
            raise ValidationError(
                f"كود طريقة الدفع {clean_code} مستخدم",
                user_message="❌ يوجد طريقة شحن بنفس الكود.",
            )

        values = self._validated_method_fields(
            {
                "instructions_ar": instructions_ar,
                "account_details": account_details,
                "type": type,
                "min_amount_units": min_amount_units,
                "max_amount_units": max_amount_units,
                "fee_percent_bp": fee_percent_bp,
                "fee_fixed_units": fee_fixed_units,
            }
        )
        order = (
            int(sort_order)
            if sort_order is not None
            else await self.repos.payment_methods.next_sort_order()
        )

        async with self.db.transaction() as tx:
            method = await self.repos.payment_methods.create(
                tx,
                code=clean_code,
                name_ar=clean_name,
                instructions_ar=values["instructions_ar"],
                account_details=values["account_details"],
                type=values["type"],
                min_amount_units=values["min_amount_units"],
                max_amount_units=values["max_amount_units"],
                requires_proof=requires_proof,
                sort_order=order,
                fee_percent_bp=values["fee_percent_bp"],
                fee_fixed_units=values["fee_fixed_units"],
            )
            await self.audit.log(
                tx,
                action="payments.methods",
                admin_id=actor.id,
                target_type="payment_method",
                target_id=method.id,
                after={"code": clean_code, "name_ar": clean_name, "action": "create"},
            )
        logger.info("أضاف الأدمن %s طريقة شحن %s", actor.id, clean_code)
        return method

    async def update_method(self, actor: User, method_id: int, **fields) -> bool:
        """
        تعديل بيانات طريقة شحن (الاسم، التعليمات، الحدود، الرسوم، الترتيب...).

        المخرجات: True عند حدوث تعديل فعلي.

        الاستثناءات:
            PermissionDeniedError · ValidationError (حقل غير مسموح أو قيمة غير صالحة)
        """
        await self.auth.require_permission(actor, Permission.PAYMENTS_METHODS)
        method = await self.get_method(method_id, require_active=False)
        if not fields:
            return False

        values = self._validated_method_fields(dict(fields))
        if not values:
            return False
        self._assert_limits_consistent(method, values)
        before = {key: getattr(method, key, None) for key in values}

        async with self.db.transaction() as tx:
            changed = await self.repos.payment_methods.update_fields(tx, method_id, **values)
            if changed:
                await self.audit.log(
                    tx,
                    action="payments.methods",
                    admin_id=actor.id,
                    target_type="payment_method",
                    target_id=method_id,
                    before={"code": method.code, **before},
                    after={"action": "update", **values},
                )
        if changed:
            logger.info(
                "عدّل الأدمن %s طريقة الشحن %s: %s",
                actor.id, method.code, ", ".join(sorted(values)),
            )
        return changed

    def _assert_limits_consistent(self, method: PaymentMethod, values: dict[str, Any]) -> None:
        """
        التأكد أن الحد الأدنى لا يتجاوز الحد الأقصى بعد التعديل.

        القيم المدمجة = القيم الجديدة فوق القيم الحالية، لأن الأدمن يعدّل
        حقلاً واحداً في كل مرة من الشاشة.

        الاستثناءات: ValidationError عند تعارض الحدين.
        """
        minimum = int(values.get("min_amount_units", method.min_amount_units) or 0)
        maximum = values.get("max_amount_units", method.max_amount_units)
        if maximum is not None and minimum and int(maximum) < minimum:
            raise ValidationError(
                f"حدود متعارضة للطريقة {method.code}: {minimum} > {maximum}",
                user_message="❌ الحد الأدنى أكبر من الحد الأقصى — صحّح أحدهما.",
            )

    async def move_method(self, actor: User, method_id: int, *, up: bool) -> bool:
        """
        تحريك طريقة الشحن في ترتيب العرض للمستخدم (تبديل مع جارتها).

        المخرجات: True عند حدوث تبديل فعلي، False إن كانت في الطرف أصلاً.

        ملاحظة: التبديل كله داخل معاملة واحدة حتى لا يبقى ترتيبان متساويان
        إذا انقطع التنفيذ في المنتصف.
        """
        await self.auth.require_permission(actor, Permission.PAYMENTS_METHODS)
        method = await self.get_method(method_id, require_active=False)
        neighbour = await self.repos.payment_methods.neighbour(method, up=up)
        if neighbour is None:
            return False

        # لو تساوى الترتيبان (بيانات قديمة) نفرّقهما بخطوة واحدة بدل التبديل العقيم
        my_order, other_order = method.sort_order, neighbour.sort_order
        if my_order == other_order:
            my_order, other_order = (other_order - 1, other_order) if up else (other_order + 1, other_order)

        async with self.db.transaction() as tx:
            await self.repos.payment_methods.update_fields(tx, method.id, sort_order=other_order)
            await self.repos.payment_methods.update_fields(tx, neighbour.id, sort_order=my_order)
            await self.audit.log(
                tx,
                action="payments.methods",
                admin_id=actor.id,
                target_type="payment_method",
                target_id=method.id,
                before={"sort_order": method.sort_order},
                after={"action": "move", "sort_order": other_order, "swapped_with": neighbour.id},
            )
        logger.info(
            "نقل الأدمن %s طريقة الشحن %s %s", actor.id, method.code, "لأعلى" if up else "لأسفل"
        )
        return True

    async def set_method_active(self, actor: User, method_id: int, active: bool) -> bool:
        """تفعيل أو إيقاف طريقة شحن دون حذفها (حفاظاً على الطلبات التاريخية)."""
        await self.auth.require_permission(actor, Permission.PAYMENTS_METHODS)
        method = await self.get_method(method_id, require_active=False)

        async with self.db.transaction() as tx:
            changed = await self.repos.payment_methods.update_fields(
                tx, method_id, is_active=1 if active else 0
            )
            if changed:
                await self.audit.log(
                    tx,
                    action="payments.methods",
                    admin_id=actor.id,
                    target_type="payment_method",
                    target_id=method_id,
                    before={"is_active": method.is_active},
                    after={"is_active": 1 if active else 0},
                )
        if changed:
            logger.info(
                "%s الأدمن %s طريقة الشحن %s",
                "فعّل" if active else "أوقف", actor.id, method.code,
            )
        return changed

    async def method_usage_report(self, actor: User) -> list[tuple[str, int, int]]:
        """
        تقرير مختصر: (اسم الطريقة، عدد الطلبات المعتمدة، إجمالي المبالغ).

        يساعد الأدمن على معرفة الطريقة الأكثر استخداماً فعلياً.
        """
        rows = await self.methods_report(actor)
        return [(row["name_ar"], row["approved_count"], row["total_units"]) for row in rows]

    async def methods_report(self, actor: User) -> list[dict[str, Any]]:
        """
        تقرير مفصّل لطرق الشحن كما تعرضه شاشة «📊 تقرير الطرق».

        لكل طريقة: المعتمد والمعلّق وإجمالي ما أُضيف فعلاً والرسوم المحصّلة.
        الأرقام كلها من قاعدة البيانات مباشرة — لا تقديرات ولا قيم ثابتة.

        الاستثناءات: PermissionDeniedError إن لم يملك `payments.view`.
        """
        await self.auth.require_permission(actor, Permission.PAYMENTS_VIEW)
        rows = await self.repos.payments.usage_by_method()
        return [
            {
                "method_id": int(row["method_id"]),
                "name_ar": row["name_ar"],
                "is_active": bool(row["is_active"]),
                "approved_count": int(row["approved_count"] or 0),
                "pending_count": int(row["pending_count"] or 0),
                "total_units": int(row["total_units"] or 0),
                "fee_units": int(row["fee_units"] or 0),
            }
            for row in rows
        ]

    async def mark_reviewed_now(self, payment_id: int) -> str:
        """وقت المراجعة الحالي بصيغة ISO (يُستخدم في العرض بعد الاعتماد مباشرة)."""
        payment = await self.repos.payments.get(payment_id)
        return payment.reviewed_at if payment and payment.reviewed_at else utc_now_iso()
```

---

## واجهة لوحة التحكم

### `handlers/admin/payment_methods.py`  ·  جديد  ·  628 سطراً

قسم «🏦 طرق الشحن» كاملاً: القائمة، البطاقة، الإضافة، تعديل كل حقل، الإثبات، الترتيب، التفعيل، التقرير.

```python
"""
قسم «🏦 طرق الشحن» في لوحة التحكم (المرحلة 7).

لماذا ملف مستقل عن `handlers/admin/payments.py`؟
    لأن القسمين يعالجان شيئين مختلفين تماماً: `payments.py` يراجع **حوالات
    العملاء** (اعتماد/رفض/بحث)، وهذا الملف يُدير **قنوات الاستلام نفسها**
    (أين يحوّل العميل، بأي حدود، وبأي رسوم). فصلهما يبقي كل ملف قابلاً
    للقراءة، ويطابق القاعدة المتبعة في المشروع: وحدة لكل قسم من اللوحة.

ما يُنفَّذ هنا:
    • قائمة طرق الشحن وبطاقة كل طريقة بأرقام استخدامها الحقيقية.
    • إضافة طريقة جديدة: الاسم ← التعليمات ← بيانات الحساب ← النوع ← تأكيد.
    • تعديل أي حقل لاحقاً: الاسم، التعليمات، بيانات الحساب، الحدّان، الرسوم.
    • تفعيل/إيقاف، جعل الإثبات إجبارياً أو اختيارياً، وترتيب العرض للمستخدم.
    • تقرير استخدام الطرق (معتمد/معلّق/المضاف فعلاً/الرسوم المحصّلة).

قواعد ملزمة مطبّقة في هذا الملف:
    • كل إجراء يفحص صلاحيته على الـcallback نفسه (`payments.methods`)،
      ولا يكفي إخفاء الزر في اللوحة.
    • **لا حذف لطريقة شحن** — الإيقاف فقط، حفاظاً على ارتباط الطلبات التاريخية.
    • كل تعديل يمر عبر `PaymentService` ليُسجَّل في سجل التدقيق بقيمه قبل/بعد.
    • الرسوم والحدود تُقرأ وتُكتب بأعداد صحيحة فقط (لا float).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from core.exceptions import InvalidAmountError, ValidationError
from core.money import FEE_SCALE, MAX_FEE_PERCENT_BP
from core.permissions import Permission
from database.models import PaymentMethod
from handlers.admin.common import (
    ADMIN_FLOW_KEY,
    admin_required,
    args,
    cancel_admin_flow,
    clear_flow,
    flow,
    permissions_of,
    start_flow,
    symbol_of,
    update_flow,
)
from handlers.common.fallbacks import exit_conversation
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import (
    cancel_only_kb,
    confirm_cancel_kb,
    method_card_kb,
    method_type_kb,
    methods_report_kb,
    payment_methods_kb,
)
from keyboards.callback_data import NS_ADM_PMT, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from texts import admin_ar as t
from utils.formatters import money_text, safe
from utils.logging_setup import get_logger
from utils.validators import clean_text, normalize_digits, parse_amount_units

logger = get_logger(__name__)

#: حالات محادثة «إضافة طريقة شحن»
ASK_NAME, ASK_INSTRUCTIONS, ASK_ACCOUNT, ASK_TYPE, CONFIRM_NEW = range(5)

#: حالة محادثة «تعديل حقل في طريقة شحن»
ASK_FIELD_VALUE = 10

#: خريطة أزرار التعديل: رمز الزر ⇐ (حقل قاعدة البيانات، اسم الحقل للعرض، نوع الإدخال)
EDIT_FIELDS: dict[str, tuple[str, str, str]] = {
    "name": ("name_ar", "الاسم", "text"),
    "inst": ("instructions_ar", "التعليمات", "long_text"),
    "acct": ("account_details", "بيانات الحساب", "long_text"),
    "min": ("min_amount_units", "الحد الأدنى", "money"),
    "max": ("max_amount_units", "الحد الأقصى", "money"),
    "feep": ("fee_percent_bp", "الرسوم النسبية", "percent"),
    "feef": ("fee_fixed_units", "الرسوم الثابتة", "money"),
}


# ======================================================================== #
#                              أدوات داخلية                                #
# ======================================================================== #


async def _load_method(context: ContextTypes.DEFAULT_TYPE, method_id: int) -> PaymentMethod:
    """
    تحميل طريقة شحن (ولو كانت متوقفة) أو رفع خطأ عربي واضح.

    الاستثناءات: ValidationError إذا كان الزر يحمل معرفاً لم يعد موجوداً.
    """
    services = services_of(context)
    method = await services.payments.get_method(method_id, require_active=False)
    if method is None:  # pragma: no cover - الخدمة ترفع الاستثناء أصلاً
        raise ValidationError(f"طريقة شحن غير موجودة: {method_id}", user_message=t.METHOD_NOT_FOUND)
    return method


def _percent_text(fee_percent_bp: int) -> str:
    """عرض نسبة الرسوم المخزّنة بنقاط الأساس كنسبة مئوية مقروءة (250 ⇐ «2.5%»)."""
    if not fee_percent_bp:
        return "0%"
    value = Decimal(int(fee_percent_bp)) / Decimal(100)
    return f"{value.normalize():f}%"


def _parse_percent_to_bp(raw: str) -> int:
    """
    تحويل نسبة مكتوبة («2.5» أو «٢٫٥») إلى نقاط أساس صحيحة (250).

    الاستثناءات:
        InvalidAmountError : نص غير رقمي أو نسبة خارج المدى 0..100.
    """
    cleaned = normalize_digits(raw or "").replace("٫", ".").replace("%", "").strip()
    try:
        value = Decimal(cleaned)
    except (InvalidOperation, ValueError) as exc:
        raise InvalidAmountError(
            f"نسبة غير صالحة: {raw!r}", user_message="❌ أرسل النسبة كرقم (مثال: 2.5)."
        ) from exc
    basis_points = int(value * FEE_SCALE / 100)
    if not 0 <= basis_points <= MAX_FEE_PERCENT_BP:
        raise InvalidAmountError(
            f"نسبة خارج المدى: {value}", user_message="❌ النسبة يجب أن تكون بين 0 و100."
        )
    return basis_points


def _parse_money_or_zero(raw: str) -> int:
    """
    قراءة مبلغ من الأدمن مع السماح بالصفر (الصفر = تعطيل الحد أو الرسوم).

    الاستثناءات: InvalidAmountError عند إدخال نص غير رقمي أو مبلغ سالب.
    """
    cleaned = normalize_digits(raw or "").replace(",", "").replace("٫", ".").strip()
    if cleaned in {"0", "0.0", "0.00", ""}:
        return 0
    return parse_amount_units(cleaned)


async def _method_card_text(context: ContextTypes.DEFAULT_TYPE, method: PaymentMethod) -> str:
    """
    بناء نص بطاقة طريقة الشحن: الإعدادات كاملة + أرقام استخدامها الحقيقية.

    الأرقام تأتي من تقرير قاعدة البيانات لا من تقدير، وإن لم تُستخدم الطريقة
    بعد تظهر أصفاراً صريحة.
    """
    services = services_of(context)
    admin = require_user(context)
    symbol = await symbol_of(context)

    rows = await services.payments.methods_report(admin)
    stats = next((row for row in rows if row["method_id"] == method.id), None)

    return t.METHOD_CARD.format(
        name=safe(method.name_ar, limit=64),
        state=t.METHOD_STATE_ON if method.is_active else t.METHOD_STATE_OFF,
        code=safe(method.code, limit=32),
        type=t.METHOD_TYPE_LABELS.get(method.type, method.type),
        limits=await services.payments.limits_text(method),
        fee=await services.payments.fee_text(method),
        proof=t.METHOD_PROOF_REQUIRED if method.requires_proof else t.METHOD_PROOF_OPTIONAL,
        sort_order=method.sort_order,
        instructions=safe(method.instructions_ar, limit=600) or t.METHOD_NO_INSTRUCTIONS,
        account=safe(method.account_details, limit=300) or t.METHOD_NO_ACCOUNT,
        approved=stats["approved_count"] if stats else 0,
        pending=stats["pending_count"] if stats else 0,
        total=money_text(stats["total_units"] if stats else 0, symbol),
    )


async def _render_method(
    update: Update, context: ContextTypes.DEFAULT_TYPE, method_id: int, *, as_new: bool = False
) -> None:
    """عرض بطاقة طريقة الشحن بعد أي إجراء عليها (تحديث الرسالة أو إرسال جديدة)."""
    method = await _load_method(context, method_id)
    perms = await permissions_of(context)
    text = await _method_card_text(context, method)
    markup = method_card_kb(method, perms)
    if as_new:
        await send(update, context, text, markup)
    else:
        await render(update, context, text, markup)


# ======================================================================== #
#                             شاشات القراءة                                #
# ======================================================================== #


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def methods_home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة طرق الشحن بترتيب ظهورها للمستخدم مع حالتها ورسومها وحدودها."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    perms = await permissions_of(context)

    methods = await services.payments.all_methods(admin)
    if not methods:
        await render(update, context, t.METHODS_EMPTY, payment_methods_kb([], perms))
        return

    lines = []
    for method in methods:
        lines.append(
            t.METHOD_LINE.format(
                state=t.METHOD_STATE_ON if method.is_active else t.METHOD_STATE_OFF,
                name=safe(method.name_ar, limit=40),
                fee=await services.payments.fee_text(method),
                limits=await services.payments.limits_text(method),
                proof=(
                    t.METHOD_PROOF_REQUIRED if method.requires_proof else t.METHOD_PROOF_OPTIONAL
                ),
            )
        )

    await render(
        update,
        context,
        t.METHODS_HOME.format(
            active=sum(1 for method in methods if method.is_active),
            total=len(methods),
            lines="\n".join(lines),
        ),
        payment_methods_kb(methods, perms),
    )


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def method_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة طريقة شحن واحدة بكل إعداداتها."""
    await answer_callback(update)
    await _render_method(update, context, args(update).int_arg(0))


@guarded
@admin_required(Permission.PAYMENTS_VIEW)
async def methods_report_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تقرير استخدام طرق الشحن: المعتمد والمعلّق وما أُضيف فعلاً والرسوم المقتطعة."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    symbol = await symbol_of(context)

    rows = await services.payments.methods_report(admin)
    if not rows:
        await render(update, context, t.METHODS_REPORT_EMPTY, methods_report_kb())
        return

    lines = "".join(
        t.METHODS_REPORT_LINE.format(
            state=t.METHOD_STATE_ON if row["is_active"] else t.METHOD_STATE_OFF,
            name=safe(row["name_ar"], limit=40),
            approved=row["approved_count"],
            pending=row["pending_count"],
            total=money_text(row["total_units"], symbol),
            fees=money_text(row["fee_units"], symbol),
        )
        for row in rows
    )
    await render(
        update,
        context,
        t.METHODS_REPORT_TITLE.format(
            lines=lines,
            total=money_text(sum(row["total_units"] for row in rows), symbol),
            fees=money_text(sum(row["fee_units"] for row in rows), symbol),
        ),
        methods_report_kb(),
    )


# ======================================================================== #
#                         إجراءات بضغطة واحدة                              #
# ======================================================================== #


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def toggle_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تفعيل أو إيقاف طريقة الشحن (بلا حذف — الطلبات القديمة تبقى مرتبطة بها)."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    method = await _load_method(context, args(update).int_arg(0))

    new_state = not bool(method.is_active)
    await services.payments.set_method_active(admin, method.id, new_state)
    message = (t.METHOD_TOGGLED_ON if new_state else t.METHOD_TOGGLED_OFF).format(
        name=safe(method.name_ar, limit=40)
    )
    logger.info(
        "%s الأدمن %s طريقة الشحن %s",
        "فعّل" if new_state else "أوقف", admin.telegram_id, method.code,
    )
    await _render_method(update, context, method.id)
    await send(update, context, message)


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def toggle_proof(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """جعل إثبات التحويل إجبارياً أو اختيارياً لهذه الطريقة."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    method = await _load_method(context, args(update).int_arg(0))

    required = not bool(method.requires_proof)
    await services.payments.update_method(admin, method.id, requires_proof=required)
    await _render_method(update, context, method.id)
    await send(
        update,
        context,
        t.METHOD_PROOF_TOGGLED.format(
            state=t.METHOD_PROOF_REQUIRED if required else t.METHOD_PROOF_OPTIONAL,
            name=safe(method.name_ar, limit=40),
        ),
    )


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def move_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تحريك الطريقة لأعلى أو لأسفل في ترتيب عرضها للمستخدم."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    data = args(update)
    up = data.action == "up"
    method = await _load_method(context, data.int_arg(0))

    moved = await services.payments.move_method(admin, method.id, up=up)
    if not moved:
        await answer_callback(update, t.METHOD_MOVE_EDGE, alert=True)
        return
    await _render_method(update, context, method.id)
    await send(update, context, t.METHOD_MOVED.format(name=safe(method.name_ar, limit=40)))


# ======================================================================== #
#                       محادثة «إضافة طريقة شحن»                           #
# ======================================================================== #


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def start_new_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء إضافة طريقة شحن: الخطوة الأولى هي الاسم كما يراه المستخدم."""
    await answer_callback(update)
    start_flow(context)
    await render(update, context, t.METHOD_NEW_INTRO, cancel_only_kb())
    return ASK_NAME


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def receive_method_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال اسم الطريقة ثم طلب تعليمات التحويل."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_NAME

    name = clean_text(message.text, field="اسم الطريقة", max_length=64)
    update_flow(context, name=name)
    await send(update, context, t.METHOD_NEW_ASK_INSTRUCTIONS, cancel_only_kb())
    return ASK_INSTRUCTIONS


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def receive_method_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال تعليمات التحويل (تظهر للمستخدم كما كُتبت) ثم طلب بيانات الحساب."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_INSTRUCTIONS

    update_flow(context, instructions=message.text)
    await send(update, context, t.METHOD_NEW_ASK_ACCOUNT, cancel_only_kb())
    return ASK_ACCOUNT


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def receive_method_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال بيانات الحساب ثم سؤال الأدمن عن نوع الطريقة."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_ACCOUNT

    update_flow(context, account=message.text)
    await send(update, context, t.METHOD_NEW_ASK_TYPE, method_type_kb())
    return ASK_TYPE


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def receive_method_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال نوع الطريقة وعرض مراجعة نهائية قبل الإنشاء."""
    await answer_callback(update)
    method_type = args(update).arg(0) or "manual"
    data = update_flow(context, type=method_type)
    if not data.get("name"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    await render(
        update,
        context,
        t.METHOD_NEW_CONFIRM.format(
            name=safe(data["name"], limit=64),
            type=t.METHOD_TYPE_LABELS.get(method_type, method_type),
            instructions=safe(data.get("instructions", ""), limit=300),
            account=safe(data.get("account", ""), limit=200),
        ),
        confirm_cancel_kb(),
    )
    return CONFIRM_NEW


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def confirm_new_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إنشاء طريقة الشحن فعلياً (الخدمة تسجّل التدقيق وتشتق الكود الداخلي)."""
    await answer_callback(update)
    data = flow(context)
    if not data.get("name"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    method = await services.payments.create_method(
        admin,
        name_ar=data["name"],
        instructions_ar=data.get("instructions", ""),
        account_details=data.get("account", ""),
        type=data.get("type", "manual"),
    )
    clear_flow(context)
    logger.info("أضاف الأدمن %s طريقة شحن %s", admin.telegram_id, method.code)

    await render(
        update,
        context,
        t.METHOD_CREATED.format(name=safe(method.name_ar, limit=64), code=safe(method.code)),
    )
    await _render_method(update, context, method.id, as_new=True)
    return ConversationHandler.END


# ======================================================================== #
#                     محادثة «تعديل حقل في طريقة شحن»                      #
# ======================================================================== #


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def start_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء تعديل حقل واحد: السؤال يعرض القيمة الحالية حتى لا يعدّل الأدمن على العمياء."""
    await answer_callback(update)
    data = args(update)
    method = await _load_method(context, data.int_arg(0))
    field_code = data.arg(1)

    if field_code not in EDIT_FIELDS:
        await answer_callback(update, t.METHOD_NOT_FOUND, alert=True)
        return ConversationHandler.END

    column, label, _kind = EDIT_FIELDS[field_code]
    symbol = await symbol_of(context)
    start_flow(context, method_id=method.id, field=field_code)

    prompts = {
        "name": lambda: t.METHOD_ASK_NAME,
        "inst": lambda: t.METHOD_ASK_INSTRUCTIONS.format(
            current=safe(method.instructions_ar, limit=300) or "—"
        ),
        "acct": lambda: t.METHOD_ASK_ACCOUNT.format(
            current=safe(method.account_details, limit=200) or "—"
        ),
        "min": lambda: t.METHOD_ASK_MIN.format(
            symbol=symbol, current=money_text(method.min_amount_units, symbol)
        ),
        "max": lambda: t.METHOD_ASK_MAX.format(
            symbol=symbol,
            current=money_text(method.max_amount_units, symbol) if method.max_amount_units else "—",
        ),
        "feep": lambda: t.METHOD_ASK_FEE_PERCENT.format(current=_percent_text(method.fee_percent_bp)),
        "feef": lambda: t.METHOD_ASK_FEE_FIXED.format(
            symbol=symbol, current=money_text(method.fee_fixed_units, symbol)
        ),
    }
    logger.info(
        "بدأ الأدمن %s تعديل الحقل %s لطريقة الشحن %s",
        require_user(context).telegram_id, column, method.code,
    )
    await render(update, context, prompts[field_code](), cancel_only_kb())
    return ASK_FIELD_VALUE


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def receive_field_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    استقبال القيمة الجديدة وتطبيقها بعد تحويلها لنوعها الصحيح.

    التحويل هنا (نسبة ⇐ نقاط أساس، مبلغ ⇐ نقاط)، والتحقق النهائي من المدى
    داخل `PaymentService` حتى لا يوجد مسار يتجاوز الحارس.
    """
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_FIELD_VALUE

    data = flow(context)
    method_id, field_code = data.get("method_id"), data.get("field")
    if not method_id or field_code not in EDIT_FIELDS:
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    column, label, kind = EDIT_FIELDS[field_code]
    raw = message.text
    if kind == "text":
        value: object = clean_text(raw, field=label, max_length=64)
    elif kind == "long_text":
        value = raw
    elif kind == "percent":
        value = _parse_percent_to_bp(raw)
    else:  # money
        units = _parse_money_or_zero(raw)
        value = (units or None) if column == "max_amount_units" else units

    services = services_of(context)
    admin = require_user(context)
    changed = await services.payments.update_method(admin, int(method_id), **{column: value})
    clear_flow(context)

    await send(
        update,
        context,
        t.METHOD_FIELD_SAVED.format(field=label) if changed else t.METHOD_FIELD_UNCHANGED,
    )
    await _render_method(update, context, int(method_id), as_new=True)
    return ConversationHandler.END


# ============================== التسجيل ================================ #


def _fallbacks() -> list:
    """المسارات الاحتياطية الموحّدة لمحادثات هذا القسم."""
    return [
        CallbackQueryHandler(cancel_admin_flow, pattern=pattern(NS_FLOW, "cancel")),
        CommandHandler("cancel", cancel_admin_flow),
        CommandHandler("start", exit_conversation(ADMIN_FLOW_KEY)),
    ]


def conversations() -> list[ConversationHandler]:
    """محادثتا إضافة طريقة شحن وتعديل حقولها."""
    new_method = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_new_method, pattern=pattern(NS_ADM_PMT, "new"))],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_method_name)],
            ASK_INSTRUCTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_method_instructions)
            ],
            ASK_ACCOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_method_account)
            ],
            ASK_TYPE: [
                CallbackQueryHandler(receive_method_type, pattern=pattern(NS_ADM_PMT, "type"))
            ],
            CONFIRM_NEW: [
                CallbackQueryHandler(confirm_new_method, pattern=pattern(NS_FLOW, "confirm"))
            ],
        },
        fallbacks=_fallbacks(),
        name="admin_payment_method_new",
        per_chat=True,
        per_user=True,
    )

    edit_field = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_edit_field, pattern=pattern(NS_ADM_PMT, "edit"))],
        states={
            ASK_FIELD_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_field_value)
            ]
        },
        fallbacks=_fallbacks(),
        name="admin_payment_method_edit",
        per_chat=True,
        per_user=True,
    )
    return [new_method, edit_field]


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم طرق الشحن خارج المحادثات."""
    return [
        CallbackQueryHandler(methods_home_screen, pattern=pattern(NS_ADM_PMT, "home")),
        CallbackQueryHandler(method_card_screen, pattern=pattern(NS_ADM_PMT, "view")),
        CallbackQueryHandler(methods_report_screen, pattern=pattern(NS_ADM_PMT, "rep")),
        CallbackQueryHandler(toggle_method, pattern=pattern(NS_ADM_PMT, "toggle")),
        CallbackQueryHandler(toggle_proof, pattern=pattern(NS_ADM_PMT, "proof")),
        CallbackQueryHandler(move_method, pattern=pattern(NS_ADM_PMT, "up")),
        CallbackQueryHandler(move_method, pattern=pattern(NS_ADM_PMT, "down")),
    ]
```

### `handlers/admin/payments.py`  ·  مُحدَّث  ·  558 سطراً

تصفية طلبات الشحن بأربع حالات، البحث عن حوالة، وعرض الرسوم والصافي في البطاقة وشاشة الاعتماد.

```python
"""
قسم «💰 المدفوعات» في لوحة التحكم: مراجعة طلبات الشحن واعتمادها أو رفضها.

المسار المعتمد (مطابق للبند 4.3 من تصميم المرحلة 0):
    قائمة المعلّق ← بطاقة الطلب ← عرض الإثبات ← (اعتماد بمبلغ قابل للتعديل
    + شاشة تأكيد) أو (رفض بسبب إجباري يصل للمستخدم).

قواعد مطبّقة:
    • إضافة الرصيد تتم داخل `PaymentService.approve` وحدها (معاملة واحدة
      تشمل: تغيير الحالة + الحركة المالية + التدقيق + إشعار المستخدم).
    • الضغط المزدوج على «اعتماد» لا يضيف الرصيد مرتين: تغيير الحالة مشروط
      بالحالة السابقة، والثانية ترفع `DuplicateOperationError` برسالة عربية.
    • المبلغ المضاف قد يختلف عن المبلغ المطلوب (حوالة ناقصة مثلاً) — ولذلك
      تُعرض شاشة تأكيد تبيّن بالضبط ما سيُضاف.
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

from core.enums import PaymentStatus
from core.permissions import Permission
from handlers.admin.common import (
    ADMIN_FLOW_KEY,
    PAGE_SIZE,
    admin_required,
    args,
    cancel_admin_flow,
    clear_flow,
    flow,
    paginate,
    permissions_of,
    start_flow,
    symbol_of,
    update_flow,
)
from handlers.common.fallbacks import exit_conversation
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import (
    ADMIN_PAYMENT_FILTERS,
    cancel_only_kb,
    payment_approve_kb,
    payment_card_kb,
    payments_list_kb,
    payments_search_kb,
)
from keyboards.callback_data import NS_ADM_PAY, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from texts import admin_ar as t
from utils.formatters import datetime_text, money_text, payment_status_text, safe
from utils.logging_setup import get_logger
from utils.validators import clean_text, parse_amount_units, validate_amount_range

logger = get_logger(__name__)

#: حالات محادثة الاعتماد
CONFIRM_APPROVE, ASK_CREDITED = range(2)

#: حالة محادثة الرفض
ASK_REJECT_REASON = 10

#: حالة محادثة البحث عن حوالة
ASK_SEARCH_TERM = 20

#: التصفية الافتراضية لقائمة طلبات الشحن
DEFAULT_FILTER = "pend"


async def _payment_card_text(context: ContextTypes.DEFAULT_TYPE, payment) -> str:
    """بناء نص بطاقة طلب الشحن (بيانات الطلب + صاحبه + حالة المراجعة)."""
    services = services_of(context)
    symbol = await symbol_of(context)
    owner = await services.users.get(payment.user_id)
    method = await services.payments.get_method(payment.method_id, require_active=False)

    proof = t.PAYMENT_PROOF_NONE
    if payment.proof_file_id:
        proof = (
            t.PAYMENT_PROOF_PHOTO if payment.proof_file_type == "photo" else t.PAYMENT_PROOF_DOC
        )

    review_line = ""
    if payment.admin_id:
        reviewer = await services.users.get(payment.admin_id)
        detail = payment.reject_reason or payment.admin_note or "—"
        review_line = t.PAYMENT_REVIEW_LINE.format(
            admin=safe(reviewer.display_name if reviewer else str(payment.admin_id), limit=30),
            detail=safe(detail, limit=200),
        )

    # سطر الرسوم يظهر فقط للطلبات التي اقتُطعت منها رسوم طريقة الشحن
    fee_line = ""
    if payment.fee_units:
        fee_line = t.PAYMENT_FEE_LINE.format(
            fee=money_text(payment.fee_units, symbol),
            net=money_text(payment.net_units, symbol),
        )

    return t.PAYMENT_CARD.format(
        payment_id=payment.id,
        name=safe(owner.display_name if owner else "—", limit=30),
        telegram_id=owner.telegram_id if owner else "—",
        amount=money_text(payment.amount_units, symbol),
        method=safe(method.name_ar if method else "—", limit=30),
        reference=safe(payment.transaction_reference or "—", limit=40),
        proof=proof,
        created=datetime_text(payment.created_at),
        expires=datetime_text(payment.expires_at) if payment.expires_at else "—",
        status=payment_status_text(payment.status),
        fee_line=fee_line,
        note_line=t.PAYMENT_NOTE_LINE.format(note=safe(payment.user_note, limit=200))
        if payment.user_note
        else "",
        review_line=review_line,
    )


async def _render_payment(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    payment_id: int,
    *,
    as_new: bool = False,
    filter_code: str = DEFAULT_FILTER,
    page: int = 1,
) -> None:
    """عرض بطاقة طلب شحن بعد أي إجراء عليه (مع حفظ موضع القائمة للرجوع)."""
    services = services_of(context)
    admin = require_user(context)
    payment = await services.payments.admin_get(admin, payment_id)
    perms = await permissions_of(context)
    text = await _payment_card_text(context, payment)
    markup = payment_card_kb(
        payment,
        perms,
        is_pending=payment.status == PaymentStatus.PENDING,
        filter_code=filter_code,
        page=page,
    )
    if as_new:
        await send(update, context, text, markup)
    else:
        await render(update, context, text, markup)


# ============================= شاشات القراءة =========================== #


def _payment_lines(payments, symbol: str) -> str:
    """أسطر عرض طلبات الشحن في القوائم ونتائج البحث (سطر مختصر لكل طلب)."""
    return "\n\n".join(
        f"💳 <b>#{payment.id}</b> · {money_text(payment.amount_units, symbol)}"
        f" · {payment_status_text(payment.status)}\n"
        f"   🔢 {safe(payment.transaction_reference or '—', limit=30)}\n"
        f"   🕒 {datetime_text(payment.created_at)}"
        for payment in payments
    )


@guarded
@admin_required(Permission.PAYMENTS_VIEW)
async def payments_list_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    قائمة طلبات الشحن مُصفّاة (معلّقة / معتمدة / مرفوضة / الكل).

    المعلّقة تظهر الأقدم أولاً (طابور مراجعة عادل)، وبقية الحالات الأحدث أولاً.
    """
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    symbol = await symbol_of(context)
    perms = await permissions_of(context)

    data = args(update)
    filter_code = data.arg(0) or DEFAULT_FILTER
    if filter_code not in ADMIN_PAYMENT_FILTERS:
        filter_code = DEFAULT_FILTER
    filter_name, statuses = ADMIN_PAYMENT_FILTERS[filter_code]

    total = await services.payments.admin_count(admin, statuses=statuses)
    page, total_pages, offset = paginate(total, data.int_arg(1, 1))
    payments = await services.payments.admin_list(
        admin, statuses=statuses, limit=PAGE_SIZE, offset=offset
    )

    if not payments:
        empty_text = (
            t.PAYMENTS_EMPTY
            if filter_code == DEFAULT_FILTER
            else t.PAYMENTS_FILTER_EMPTY.format(filter_name=filter_name)
        )
        await render(
            update,
            context,
            empty_text,
            payments_list_kb(
                [], page=1, total_pages=1, symbol=symbol, filter_code=filter_code, perms=perms
            ),
        )
        return

    title = t.PAYMENTS_FILTER_TITLE.format(
        filter_name=filter_name, count=total, page=page, pages=total_pages
    )
    await render(
        update,
        context,
        f"{title}\n\n{_payment_lines(payments, symbol)}",
        payments_list_kb(
            payments,
            page=page,
            total_pages=total_pages,
            symbol=symbol,
            filter_code=filter_code,
            perms=perms,
        ),
    )


@guarded
@admin_required(Permission.PAYMENTS_VIEW)
async def payment_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة طلب شحن واحد (مع تذكّر التصفية والصفحة التي جاء منها)."""
    await answer_callback(update)
    data = args(update)
    await _render_payment(
        update,
        context,
        data.int_arg(0),
        filter_code=data.arg(1) or DEFAULT_FILTER,
        page=max(1, data.int_arg(2, 1)),
    )


@guarded
@admin_required(Permission.PAYMENTS_VIEW)
async def payment_proof_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إرسال ملف إثبات الدفع كما رفعه المستخدم (صورة أو مستند)."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    payment = await services.payments.admin_get(admin, args(update).int_arg(0))
    chat = update.effective_chat

    if not payment.proof_file_id or chat is None:
        await answer_callback(update, t.PAYMENT_PROOF_NONE, alert=True)
        return

    caption = t.PAYMENT_PROOF_CAPTION.format(payment_id=payment.id)
    if payment.proof_file_type == "photo":
        await context.bot.send_photo(chat_id=chat.id, photo=payment.proof_file_id, caption=caption)
    else:
        await context.bot.send_document(
            chat_id=chat.id, document=payment.proof_file_id, caption=caption
        )


# ============================ محادثة الاعتماد ========================== #


async def _approve_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, *, as_new: bool = False) -> int:
    """عرض شاشة تأكيد الاعتماد بالمبلغ الحالي (المطلوب أو المعدَّل)."""
    data = flow(context)
    services = services_of(context)
    admin = require_user(context)
    payment = await services.payments.admin_get(admin, int(data["payment_id"]))
    owner = await services.users.get(payment.user_id)
    symbol = await symbol_of(context)
    # الافتراضي هو الصافي بعد رسوم الطريقة (كما ستحسبه الخدمة عند الاعتماد)
    credited = int(data.get("credited_units") or payment.net_units)

    text = t.PAYMENT_APPROVE_CONFIRM.format(
        payment_id=payment.id,
        name=safe(owner.display_name if owner else "—", limit=30),
        amount=money_text(payment.amount_units, symbol),
        fee_line=t.PAYMENT_APPROVE_FEE_LINE.format(fee=money_text(payment.fee_units, symbol))
        if payment.fee_units
        else "",
        credited=money_text(credited, symbol),
        balance_after=money_text((owner.balance_units if owner else 0) + credited, symbol),
    )
    if as_new:
        await send(update, context, text, payment_approve_kb())
    else:
        await render(update, context, text, payment_approve_kb())
    return CONFIRM_APPROVE


@guarded
@admin_required(Permission.PAYMENTS_APPROVE)
async def start_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء اعتماد طلب شحن: شاشة التأكيد مع المبلغ المطلوب."""
    await answer_callback(update)
    payment_id = args(update).int_arg(0)
    start_flow(context, payment_id=payment_id)
    return await _approve_confirm(update, context)


@guarded
@admin_required(Permission.PAYMENTS_APPROVE)
async def ask_credited_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """طلب مبلغ مختلف عن المبلغ المذكور في الطلب (حوالة ناقصة أو زائدة)."""
    await answer_callback(update)
    data = flow(context)
    if not data.get("payment_id"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    payment = await services.payments.admin_get(admin, int(data["payment_id"]))
    symbol = await symbol_of(context)
    await render(
        update,
        context,
        t.PAYMENT_ASK_AMOUNT.format(
            amount=money_text(payment.amount_units, symbol),
            net=money_text(payment.net_units, symbol),
        ),
        cancel_only_kb(),
    )
    return ASK_CREDITED


@guarded
@admin_required(Permission.PAYMENTS_APPROVE)
async def receive_credited_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال المبلغ المعدَّل والعودة إلى شاشة التأكيد."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_CREDITED

    units = validate_amount_range(parse_amount_units(message.text), min_units=1, label="المبلغ")
    update_flow(context, credited_units=units)
    return await _approve_confirm(update, context, as_new=True)


@guarded
@admin_required(Permission.PAYMENTS_APPROVE)
async def confirm_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """اعتماد الطلب فعلياً: إضافة الرصيد + الحركة المالية + الإشعار (داخل الخدمة)."""
    await answer_callback(update)
    data = flow(context)
    if not data.get("payment_id"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    payment_id = int(data["payment_id"])
    credited = data.get("credited_units")
    symbol = await symbol_of(context)

    transaction = await services.payments.approve(
        admin,
        payment_id,
        credited_units=int(credited) if credited else None,
        admin_note=None,
    )
    owner = await services.users.get(transaction.user_id)
    clear_flow(context)
    logger.info("اعتمد الأدمن %s طلب الشحن #%s", admin.telegram_id, payment_id)

    await render(
        update,
        context,
        t.PAYMENT_APPROVED.format(
            payment_id=payment_id,
            name=safe(owner.display_name if owner else "—", limit=30),
            credited=money_text(transaction.amount_units, symbol),
            balance=money_text(transaction.balance_after_units, symbol),
        ),
    )
    await _render_payment(update, context, payment_id, as_new=True)
    return ConversationHandler.END


# ============================= محادثة الرفض ============================ #


@guarded
@admin_required(Permission.PAYMENTS_REJECT)
async def start_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء رفض طلب شحن: السبب إجباري ويصل للمستخدم كما كُتب."""
    await answer_callback(update)
    payment_id = args(update).int_arg(0)
    start_flow(context, payment_id=payment_id)
    await render(
        update, context, t.PAYMENT_ASK_REJECT_REASON.format(payment_id=payment_id), cancel_only_kb()
    )
    return ASK_REJECT_REASON


@guarded
@admin_required(Permission.PAYMENTS_REJECT)
async def receive_reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ الرفض بعد استلام السبب (الخدمة تُشعر المستخدم وتسجّل التدقيق)."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_REJECT_REASON

    data = flow(context)
    if not data.get("payment_id"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    reason = clean_text(message.text, field="سبب الرفض", max_length=300, min_length=3)
    services = services_of(context)
    admin = require_user(context)
    payment_id = int(data["payment_id"])
    await services.payments.reject(admin, payment_id, reason)
    clear_flow(context)
    logger.info("رفض الأدمن %s طلب الشحن #%s", admin.telegram_id, payment_id)

    await send(
        update,
        context,
        t.PAYMENT_REJECTED.format(payment_id=payment_id, reason=safe(reason, limit=300)),
    )
    await _render_payment(update, context, payment_id, as_new=True)
    return ConversationHandler.END


# ============================= محادثة البحث ============================ #


@guarded
@admin_required(Permission.PAYMENTS_VIEW)
async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء البحث عن طلب شحن برقم العملية أو برقم الطلب."""
    await answer_callback(update)
    start_flow(context)
    await render(update, context, t.PAYMENT_SEARCH_ASK, cancel_only_kb())
    return ASK_SEARCH_TERM


@guarded
@admin_required(Permission.PAYMENTS_VIEW)
async def receive_search_term(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    تنفيذ البحث وعرض النتائج كأزرار تفتح بطاقة الطلب مباشرة.

    يشمل البحث كل الحالات (حتى الملغاة والمنتهية) لأن سؤال العميل عادةً
    عن حوالة لم تصل، وقد تكون رُفضت أو انتهت صلاحيتها.
    """
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_SEARCH_TERM

    services = services_of(context)
    admin = require_user(context)
    symbol = await symbol_of(context)
    term = message.text.strip()

    results = await services.payments.admin_search(admin, term)
    clear_flow(context)
    if not results:
        await send(
            update,
            context,
            t.PAYMENT_SEARCH_EMPTY.format(term=safe(term, limit=40)),
            payments_search_kb([], symbol=symbol),
        )
        return ConversationHandler.END

    await send(
        update,
        context,
        t.PAYMENT_SEARCH_TITLE.format(
            term=safe(term, limit=40),
            count=len(results),
            lines=_payment_lines(results, symbol),
        ),
        payments_search_kb(results, symbol=symbol),
    )
    return ConversationHandler.END


# ============================== التسجيل ================================ #


def _fallbacks() -> list:
    """المسارات الاحتياطية الموحّدة لمحادثات هذا القسم."""
    return [
        CallbackQueryHandler(cancel_admin_flow, pattern=pattern(NS_FLOW, "cancel")),
        CommandHandler("cancel", cancel_admin_flow),
        CommandHandler("start", exit_conversation(ADMIN_FLOW_KEY)),
    ]


def conversations() -> list[ConversationHandler]:
    """محادثات القسم: الاعتماد، الرفض، والبحث عن حوالة."""
    approve = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_approve, pattern=pattern(NS_ADM_PAY, "ok"))],
        states={
            CONFIRM_APPROVE: [
                CallbackQueryHandler(confirm_approve, pattern=pattern(NS_FLOW, "confirm")),
                CallbackQueryHandler(
                    ask_credited_amount, pattern=pattern(NS_ADM_PAY, "amount")
                ),
            ],
            ASK_CREDITED: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_credited_amount)
            ],
        },
        fallbacks=_fallbacks(),
        name="admin_payment_approve",
        per_chat=True,
        per_user=True,
    )

    reject = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_reject, pattern=pattern(NS_ADM_PAY, "no"))],
        states={
            ASK_REJECT_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reject_reason)
            ]
        },
        fallbacks=_fallbacks(),
        name="admin_payment_reject",
        per_chat=True,
        per_user=True,
    )

    search = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_search, pattern=pattern(NS_ADM_PAY, "find"))],
        states={
            ASK_SEARCH_TERM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_search_term)
            ]
        },
        fallbacks=_fallbacks(),
        name="admin_payment_search",
        per_chat=True,
        per_user=True,
    )
    return [approve, reject, search]


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم المدفوعات خارج المحادثات."""
    return [
        CallbackQueryHandler(payments_list_screen, pattern=pattern(NS_ADM_PAY, "list")),
        CallbackQueryHandler(payment_card_screen, pattern=pattern(NS_ADM_PAY, "view")),
        CallbackQueryHandler(payment_proof_screen, pattern=pattern(NS_ADM_PAY, "proof")),
    ]
```

### `keyboards/admin_kb.py`  ·  مُحدَّث (مقتطف)  ·  1159 سطراً (المعروض: 276 سطراً)

لوحات طرق الشحن + صف التصفية + لوحة نتائج البحث.

```python
# ============================= المدفوعات ================================ #


def admin_payments_filters_row(current: str) -> list[InlineKeyboardButton]:
    """صف تصفية طلبات الشحن (المعلّق/المعتمد/المرفوض/الكل) مع تمييز الحالي."""
    return [
        InlineKeyboardButton(
            f"• {label} •" if code == current else label,
            callback_data=pack(NS_ADM_PAY, "list", code, 1),
        )
        for code, (label, _statuses) in ADMIN_PAYMENT_FILTERS.items()
    ]


def payments_list_kb(
    payments: list[Payment],
    *,
    page: int,
    total_pages: int,
    symbol: str,
    filter_code: str = "pend",
    perms: set[str] | None = None,
) -> InlineKeyboardMarkup:
    """
    قائمة طلبات الشحن: أزرار الطلبات + صف التصفية + البحث + طرق الشحن.

    المدخلات:
        filter_code : رمز التصفية الحالي (يُعاد في أزرار الصفحات والرجوع).
        perms       : صلاحيات الأدمن — زر «طرق الشحن» لا يظهر بدون صلاحيته.
    """
    permissions = perms or set()
    rows = [
        [
            InlineKeyboardButton(
                f"#{payment.id} · {money_text(payment.amount_units, symbol)}",
                callback_data=pack(NS_ADM_PAY, "view", payment.id, filter_code, page),
            )
        ]
        for payment in payments
    ]
    rows.append(admin_payments_filters_row(filter_code))
    nav = pagination_row(
        NS_ADM_PAY, "list", page=page, total_pages=total_pages, prefix_args=(filter_code,)
    )
    if nav:
        rows.append(nav)

    tools = [InlineKeyboardButton(t.BTN_PAYMENT_SEARCH, callback_data=pack(NS_ADM_PAY, "find"))]
    if Permission.PAYMENTS_METHODS in permissions:
        tools.append(InlineKeyboardButton(t.BTN_METHODS, callback_data=pack(NS_ADM_PMT, "home")))
    rows.append(tools)
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def payments_search_kb(payments: list[Payment], *, symbol: str) -> InlineKeyboardMarkup:
    """نتائج البحث عن حوالة: زر لكل طلب مطابق + إعادة البحث."""
    rows = [
        [
            InlineKeyboardButton(
                f"#{payment.id} · {money_text(payment.amount_units, symbol)}",
                callback_data=pack(NS_ADM_PAY, "view", payment.id, "all", 1),
            )
        ]
        for payment in payments
    ]
    rows.append(
        [InlineKeyboardButton(t.BTN_PAYMENT_SEARCH, callback_data=pack(NS_ADM_PAY, "find"))]
    )
    rows.append(_back_row(NS_ADM_PAY, "list", "pend", 1))
    return InlineKeyboardMarkup(rows)


def payment_card_kb(
    payment: Payment,
    perms: set[str],
    *,
    is_pending: bool,
    filter_code: str = "pend",
    page: int = 1,
) -> InlineKeyboardMarkup:
    """أزرار بطاقة طلب الشحن (الاعتماد/الرفض تظهر للمعلّق فقط)."""
    rows: list[list[InlineKeyboardButton]] = []
    if payment.proof_file_id:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_PAYMENT_PROOF, callback_data=pack(NS_ADM_PAY, "proof", payment.id)
                )
            ]
        )
    if is_pending:
        action_row: list[InlineKeyboardButton] = []
        if Permission.PAYMENTS_APPROVE in perms:
            action_row.append(
                InlineKeyboardButton(
                    t.BTN_PAYMENT_APPROVE, callback_data=pack(NS_ADM_PAY, "ok", payment.id)
                )
            )
        if Permission.PAYMENTS_REJECT in perms:
            action_row.append(
                InlineKeyboardButton(
                    t.BTN_PAYMENT_REJECT, callback_data=pack(NS_ADM_PAY, "no", payment.id)
                )
            )
        if action_row:
            rows.append(action_row)
    if Permission.USERS_VIEW in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    "👤 صاحب الطلب", callback_data=pack(NS_ADM_USERS, "view", payment.user_id)
                )
            ]
        )
    rows.append(_back_row(NS_ADM_PAY, "list", filter_code, page))
    return InlineKeyboardMarkup(rows)


def payment_approve_kb() -> InlineKeyboardMarkup:
    """تأكيد الاعتماد مع إمكانية تعديل المبلغ المضاف."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_CONFIRM_DANGER, callback_data=pack(NS_FLOW, "confirm"))],
            [InlineKeyboardButton(t.BTN_EDIT_AMOUNT, callback_data=pack(NS_ADM_PAY, "amount"))],
            _cancel_row(),
        ]
    )


# ============================= طرق الشحن ================================ #


def payment_methods_kb(methods: list[PaymentMethod], perms: set[str]) -> InlineKeyboardMarkup:
    """
    قائمة طرق الشحن في اللوحة: زر لكل طريقة + الإضافة + التقرير.

    أزرار الإضافة لا تظهر إلا لمن يملك `payments.methods`، لأن طريقة الشحن
    تحدد إلى أين تذهب أموال العملاء فعلياً.
    """
    rows = [
        [
            InlineKeyboardButton(
                f"{t.METHOD_STATE_ON if method.is_active else t.METHOD_STATE_OFF} {method.name_ar}",
                callback_data=pack(NS_ADM_PMT, "view", method.id),
            )
        ]
        for method in methods
    ]
    actions: list[InlineKeyboardButton] = []
    if Permission.PAYMENTS_METHODS in perms:
        actions.append(
            InlineKeyboardButton(t.BTN_METHOD_NEW, callback_data=pack(NS_ADM_PMT, "new"))
        )
    actions.append(
        InlineKeyboardButton(t.BTN_METHODS_REPORT, callback_data=pack(NS_ADM_PMT, "rep"))
    )
    rows.append(actions)
    rows.append(_back_row(NS_ADM_PAY, "list", "pend", 1))
    return InlineKeyboardMarkup(rows)


def method_card_kb(method: PaymentMethod, perms: set[str]) -> InlineKeyboardMarkup:
    """
    أزرار بطاقة طريقة الشحن: تعديل الحقول، الرسوم، الحدود، الإثبات، الترتيب، التفعيل.

    كل زر هنا يقابله معالج يفحص `payments.methods` من جديد على الـcallback نفسه.
    """
    rows: list[list[InlineKeyboardButton]] = []
    if Permission.PAYMENTS_METHODS in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_METHOD_EDIT_NAME,
                    callback_data=pack(NS_ADM_PMT, "edit", method.id, "name"),
                ),
                InlineKeyboardButton(
                    t.BTN_METHOD_EDIT_INSTRUCTIONS,
                    callback_data=pack(NS_ADM_PMT, "edit", method.id, "inst"),
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_METHOD_EDIT_ACCOUNT,
                    callback_data=pack(NS_ADM_PMT, "edit", method.id, "acct"),
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_METHOD_EDIT_MIN,
                    callback_data=pack(NS_ADM_PMT, "edit", method.id, "min"),
                ),
                InlineKeyboardButton(
                    t.BTN_METHOD_EDIT_MAX,
                    callback_data=pack(NS_ADM_PMT, "edit", method.id, "max"),
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_METHOD_EDIT_FEEP,
                    callback_data=pack(NS_ADM_PMT, "edit", method.id, "feep"),
                ),
                InlineKeyboardButton(
                    t.BTN_METHOD_EDIT_FEEF,
                    callback_data=pack(NS_ADM_PMT, "edit", method.id, "feef"),
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_METHOD_PROOF_ON if method.requires_proof else t.BTN_METHOD_PROOF_OFF,
                    callback_data=pack(NS_ADM_PMT, "proof", method.id),
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_METHOD_UP, callback_data=pack(NS_ADM_PMT, "up", method.id)
                ),
                InlineKeyboardButton(
                    t.BTN_METHOD_DOWN, callback_data=pack(NS_ADM_PMT, "down", method.id)
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_METHOD_OFF if method.is_active else t.BTN_METHOD_ON,
                    callback_data=pack(NS_ADM_PMT, "toggle", method.id),
                )
            ]
        )
    rows.append(_back_row(NS_ADM_PMT, "home"))
    return InlineKeyboardMarkup(rows)


def method_type_kb() -> InlineKeyboardMarkup:
    """اختيار نوع طريقة الشحن أثناء إنشائها (يطابق أنواع المخطط الثلاثة)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t.BTN_METHOD_TYPE_MANUAL, callback_data=pack(NS_ADM_PMT, "type", "manual")
                )
            ],
            [
                InlineKeyboardButton(
                    t.BTN_METHOD_TYPE_CRYPTO, callback_data=pack(NS_ADM_PMT, "type", "crypto")
                )
            ],
            [
                InlineKeyboardButton(
                    t.BTN_METHOD_TYPE_GATEWAY, callback_data=pack(NS_ADM_PMT, "type", "gateway")
                )
            ],
            _cancel_row(),
        ]
    )


def methods_report_kb() -> InlineKeyboardMarkup:
    """أزرار شاشة تقرير طرق الشحن."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADM_PMT, "rep"))],
            _back_row(NS_ADM_PMT, "home"),
        ]
    )
```

### `handlers/admin/__init__.py`  ·  مُحدَّث  ·  75 سطراً

تسجيل قسم `payment_methods` ضمن أقسام اللوحة.

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
    catalog,
    dashboard,
    logs,
    orders,
    payment_methods,
    payments,
    providers,
    settings,
    system,
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

### `keyboards/callback_data.py`  ·  مُحدَّث (مقتطف)  ·  160 سطراً (المعروض: 20 سطراً)

مساحة الأزرار الجديدة `pm`.

```python
# ----------------------- مساحات لوحة الأدمن ----------------------------- #
# مختصرة عمداً: حدّ تيليجرام 64 بايت، وبعض الأزرار تحمل معرفات طويلة.

NS_ADMIN = "adm"      # لوحة التحكم والصحة العامة
NS_ADM_USERS = "au"   # إدارة المستخدمين
NS_ADM_PAY = "ap"     # مراجعة طلبات الشحن
NS_ADM_ORD = "ao"     # إدارة الطلبات
NS_ADM_TKT = "at"     # تذاكر الدعم (جانب الأدمن)
NS_ADM_CAT = "ac"     # إدارة الكتالوج (تصنيفات/خدمات)
NS_ADM_SET = "as"     # الإعدادات
NS_ADM_LOG = "al"     # السجلات (تدقيق/أخطاء)
NS_ADM_PRV = "pv"     # المزودون وربط الـAPI (المرحلة 5)
NS_ADM_PMT = "pm"     # طرق الشحن وإدارتها (المرحلة 7)

#: كل المساحات المعروفة — تُستخدم في اختبار «لا أزرار بلا وظيفة»
ALL_NAMESPACES: tuple[str, ...] = (
    NS_NAV, NS_CATALOG, NS_NEW, NS_ORDERS, NS_WALLET, NS_DEPOSIT, NS_SUPPORT, NS_ACCOUNT, NS_FLOW,
    NS_ADMIN, NS_ADM_USERS, NS_ADM_PAY, NS_ADM_ORD, NS_ADM_TKT, NS_ADM_CAT, NS_ADM_SET, NS_ADM_LOG,
    NS_ADM_PRV, NS_ADM_PMT,
)
```

---

## واجهة المستخدم والنصوص

### `handlers/user/deposit.py`  ·  مُحدَّث (مقتطف)  ·  326 سطراً (المعروض: 120 سطراً)

عرض الرسوم عند اختيار الطريقة، والصافي في المراجعة وبعد الإرسال.

```python
async def _fee_lines(context: ContextTypes.DEFAULT_TYPE, method, amount_units: int) -> str:
    """
    سطرا «الرسوم» و«سيُضاف لرصيدك» للطريقة ذات الرسوم (أو نص فارغ).

    تُحترم إعداد `deposit_fee_visible`: بعض المالكين يفضّلون إخفاء تفصيل
    الرسوم وعرض المبلغ كما هو — والافتراضي هو الإظهار (الشفافية أولاً).
    """
    services = services_of(context)
    if not method.has_fees or not await services.payments.fee_visible_to_user():
        return ""
    symbol = await services.settings.money_symbol()
    fee_units, net_units = services.payments.fee_for(method, amount_units)
    return ar.DEPOSIT_FEE_LINES.format(
        fee=money_text(fee_units, symbol), net=money_text(net_units, symbol)
    )


async def _summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """عرض مراجعة نهائية لطلب الشحن قبل إرساله."""
    flow = _flow(context)
    services = services_of(context)
    symbol = await services.settings.money_symbol()
    amount_units = flow.get("amount_units", 0)
    method = await services.payments.get_method(flow["method_id"])
    text = ar.DEPOSIT_SUMMARY.format(
        method=safe(flow.get("method_name", "")),
        amount=money_text(amount_units, symbol),
        fee_lines=await _fee_lines(context, method, amount_units),
        reference=safe(flow.get("reference") or "—"),
        proof=ar.DEPOSIT_PROOF_ATTACHED if flow.get("proof_file_id") else ar.DEPOSIT_PROOF_NONE,
    )
    await send(update, context, text, confirm_cancel_markup())
    return CONFIRM


@guarded
async def start_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء محادثة الشحن بعرض طرق الدفع المفعّلة."""
    await answer_callback(update)
    services = services_of(context)
    methods = await services.payments.active_methods()
    if not methods:
        await render(update, context, ar.DEPOSIT_METHODS_EMPTY, wallet_kb())
        return ConversationHandler.END

    if context.user_data is not None:
        context.user_data[FLOW_KEY] = {}
    await render(update, context, ar.DEPOSIT_METHODS_TITLE, deposit_methods_kb(methods))
    return CHOOSE_METHOD


@guarded
async def choose_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ الطريقة المختارة وعرض تعليماتها وحدودها وسؤال المستخدم عن المبلغ."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    method_id = data.int_arg(0)

    services = services_of(context)
    method = await services.payments.get_method(method_id)
    limits = await services.payments.limits_text(method)

    if context.user_data is not None:
        context.user_data[FLOW_KEY] = {
            "method_id": method.id,
            "method_name": method.name_ar,
            "requires_proof": bool(method.requires_proof),
        }

    fee_line = ""
    if method.has_fees and await services.payments.fee_visible_to_user():
        fee_line = ar.DEPOSIT_FEE_NOTICE.format(fee=await services.payments.fee_text(method))

    text = ar.DEPOSIT_ASK_AMOUNT.format(
        method=safe(method.name_ar),
        instructions=safe(method.instructions_ar or ""),
        account=safe(method.account_details or ""),
        limits=limits,
        fee_line=fee_line,
    )
    await render(update, context, text, cancel_markup())
    return ASK_AMOUNT


@guarded
async def receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال المبلغ والتحقق من الحدود قبل الانتقال لرقم العملية."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, ar.ERR_NOT_TEXT, cancel_markup())
        return ASK_AMOUNT

    flow = _flow(context)
    if not flow.get("method_id"):
        await send(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    services = services_of(context)
    symbol = await services.settings.money_symbol()
    method = await services.payments.get_method(flow["method_id"])
    minimum, maximum = await services.payments.method_limits(method)

    amount_units = parse_amount_units(message.text)
    validate_amount_range(
        amount_units, min_units=minimum, max_units=maximum, label="مبلغ الشحن"
    )
    flow["amount_units"] = amount_units
    # نحتفظ بالمبلغ نصاً عشرياً دقيقاً (لا float) لأن خدمة الدفع تُعيد تحليله بنفسها
    flow["raw_amount"] = str(from_units(amount_units))

    if flow.get("requires_proof"):
        await send(
            update,
            context,
            ar.DEPOSIT_ASK_REFERENCE.format(amount=money_text(amount_units, symbol)),
            cancel_markup(),
        )
        return ASK_REFERENCE

    return await _summary(update, context)
```

### `texts/admin_ar.py`  ·  مُحدَّث (مقتطف)  ·  930 سطراً (المعروض: 195 سطراً)

نصوص طرق الشحن والتصفية والبحث والتقرير.

```python
# ======================================================================== #
#              طرق الشحن والرسوم والبحث في المدفوعات (المرحلة 7)           #
# ======================================================================== #

# --------------------------- تصفية طلبات الشحن -------------------------- #

PAYMENT_FILTER_PENDING = "⏳ معلّقة"
PAYMENT_FILTER_APPROVED = "✅ معتمدة"
PAYMENT_FILTER_REJECTED = "❌ مرفوضة"
PAYMENT_FILTER_ALL = "📋 الكل"

PAYMENTS_FILTER_TITLE = (
    "💰 <b>طلبات الشحن — {filter_name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "العدد: {count} · الصفحة {page} من {pages}"
)
PAYMENTS_FILTER_EMPTY = "📭 لا توجد طلبات شحن ضمن «{filter_name}»."

# ------------------------------ البحث ----------------------------------- #

BTN_PAYMENT_SEARCH = "🔎 بحث عن حوالة"
PAYMENT_SEARCH_ASK = (
    "🔎 <b>البحث في طلبات الشحن</b>\n\n"
    "أرسل <b>رقم العملية</b> (كلياً أو جزئياً) أو <b>رقم طلب الشحن</b>."
)
PAYMENT_SEARCH_TITLE = "🔎 <b>نتائج البحث عن «{term}»</b>\n\nعدد النتائج: {count}\n\n{lines}"
PAYMENT_SEARCH_EMPTY = (
    "🔎 لا يوجد طلب شحن مطابق لـ«{term}».\n\n"
    "تأكد من الرقم، وتذكّر أن الطلب الملغى من المستخدم يظهر أيضاً في البحث."
)

# -------------------------- الرسوم في بطاقة الطلب ----------------------- #

PAYMENT_FEE_LINE = "🧾 رسوم الطريقة: {fee}\n💵 الصافي للمستخدم: {net}\n"
PAYMENT_APPROVE_FEE_LINE = "🧾 رسوم الطريقة: {fee}\n"

# ---------------------------- شاشة طرق الشحن ---------------------------- #

MENU_PAYMENT_METHODS = "🏦 طرق الشحن"
BTN_METHODS = "🏦 طرق الشحن"
BTN_METHOD_NEW = "➕ طريقة جديدة"
BTN_METHOD_ON = "✅ تفعيل"
BTN_METHOD_OFF = "⛔ إيقاف"
BTN_METHOD_UP = "🔼 أعلى"
BTN_METHOD_DOWN = "🔽 أسفل"
BTN_METHOD_PROOF_ON = "📎 الإثبات: إجباري"
BTN_METHOD_PROOF_OFF = "📎 الإثبات: اختياري"
BTN_METHODS_REPORT = "📊 تقرير الطرق"

METHODS_HOME = (
    "🏦 <b>طرق الشحن</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "المفعّلة: {active} من {total}\n\n"
    "{lines}\n"
    "ℹ️ الترتيب هنا هو نفسه ترتيب ظهورها للمستخدم."
)
METHODS_EMPTY = (
    "🏦 <b>طرق الشحن</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "⚠️ لا توجد أي طريقة شحن بعد، ولهذا <b>لا يستطيع أي مستخدم شحن رصيده الآن</b>.\n\n"
    "اضغط «➕ طريقة جديدة» لإضافة أول طريقة (محفظة، حوالة بنكية، عملة رقمية...)."
)
METHOD_LINE = "{state} <b>{name}</b> · {fee}\n   💵 {limits} · 📎 {proof}\n"
METHOD_STATE_ON = "🟢"
METHOD_STATE_OFF = "🔴"
METHOD_PROOF_REQUIRED = "إثبات إجباري"
METHOD_PROOF_OPTIONAL = "إثبات اختياري"

METHOD_CARD = (
    "🏦 <b>{name}</b> {state}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🔖 الكود: <code>{code}</code> · النوع: {type}\n"
    "💵 الحدود: {limits}\n"
    "🧾 الرسوم: {fee}\n"
    "📎 الإثبات: {proof}\n"
    "🔢 ترتيب العرض: {sort_order}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📋 <b>التعليمات كما يراها المستخدم:</b>\n{instructions}\n\n"
    "🏧 <b>بيانات الحساب:</b>\n{account}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📊 الطلبات: معتمدة {approved} · معلّقة {pending}\n"
    "💰 أُضيف عبرها: {total}"
)
METHOD_TYPE_LABELS = {
    "manual": "تحويل يدوي",
    "crypto": "عملة رقمية",
    "gateway": "بوابة دفع",
}
METHOD_NO_INSTRUCTIONS = "<i>(لا توجد تعليمات — المستخدم لن يعرف كيف يحوّل!)</i>"
METHOD_NO_ACCOUNT = "<i>(لا توجد بيانات حساب — المستخدم لن يعرف لمن يحوّل!)</i>"
METHOD_NOT_FOUND = "❌ طريقة الشحن غير موجودة (ربما حُذفت أو تغيّر معرّفها)."

# ------------------------- تعديل حقول طريقة الشحن ----------------------- #

BTN_METHOD_EDIT_NAME = "✏️ الاسم"
BTN_METHOD_EDIT_INSTRUCTIONS = "📋 التعليمات"
BTN_METHOD_EDIT_ACCOUNT = "🏧 بيانات الحساب"
BTN_METHOD_EDIT_MIN = "⬇️ الحد الأدنى"
BTN_METHOD_EDIT_MAX = "⬆️ الحد الأقصى"
BTN_METHOD_EDIT_FEEP = "％ رسوم نسبية"
BTN_METHOD_EDIT_FEEF = "🧾 رسوم ثابتة"

METHOD_ASK_NAME = "✏️ أرسل اسم طريقة الشحن كما سيراه المستخدم (مثال: محفظة كريمي):"
METHOD_ASK_INSTRUCTIONS = (
    "📋 أرسل <b>تعليمات التحويل</b> كما ستظهر للمستخدم.\n\n"
    "اكتبها خطوات واضحة: إلى أين يحوّل، وماذا يرسل بعد التحويل.\n"
    "الحالي: {current}"
)
METHOD_ASK_ACCOUNT = (
    "🏧 أرسل <b>بيانات الحساب</b> التي يحوّل إليها المستخدم\n"
    "(رقم المحفظة / رقم الحساب / عنوان المحفظة الرقمية).\n\n"
    "الحالي: {current}"
)
METHOD_ASK_MIN = (
    "⬇️ أرسل <b>الحد الأدنى</b> للشحن بهذه الطريقة بالعملة ({symbol}).\n"
    "أرسل <code>0</code> لاستخدام الحد العام من الإعدادات.\n\n"
    "الحالي: {current}"
)
METHOD_ASK_MAX = (
    "⬆️ أرسل <b>الحد الأقصى</b> للشحن بهذه الطريقة بالعملة ({symbol}).\n"
    "أرسل <code>0</code> لإلغاء الحد الأقصى.\n\n"
    "الحالي: {current}"
)
METHOD_ASK_FEE_PERCENT = (
    "％ أرسل <b>نسبة الرسوم</b> المقتطعة من كل حوالة (مثال: <code>2.5</code> تعني 2.5%).\n"
    "أرسل <code>0</code> لإلغاء النسبة.\n\n"
    "الحالي: {current}\n"
    "ℹ️ الرسوم تُخصم من مبلغ الحوالة، والمستخدم يرى الصافي قبل الإرسال."
)
METHOD_ASK_FEE_FIXED = (
    "🧾 أرسل <b>الرسوم الثابتة</b> المقتطعة من كل حوالة بالعملة ({symbol}).\n"
    "أرسل <code>0</code> لإلغائها.\n\n"
    "الحالي: {current}"
)
METHOD_FIELD_SAVED = "✅ حُفظ التعديل على «{field}»."
METHOD_FIELD_UNCHANGED = "ℹ️ لا تغيير — القيمة الجديدة مطابقة للحالية."

# --------------------------- إضافة طريقة جديدة -------------------------- #

METHOD_NEW_INTRO = (
    "➕ <b>إضافة طريقة شحن</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "سنأخذ 4 خطوات: الاسم ← التعليمات ← بيانات الحساب ← النوع.\n"
    "الحدود والرسوم تُضبط بعد الإنشاء من بطاقة الطريقة.\n\n"
    "✏️ أرسل الآن <b>اسم الطريقة</b> كما سيراه المستخدم:"
)
METHOD_NEW_ASK_INSTRUCTIONS = (
    "📋 أرسل <b>تعليمات التحويل</b> للمستخدم (خطوات واضحة):"
)
METHOD_NEW_ASK_ACCOUNT = "🏧 أرسل <b>بيانات الحساب</b> (رقم المحفظة/الحساب):"
METHOD_NEW_ASK_TYPE = "🏷 اختر <b>نوع الطريقة</b>:"
BTN_METHOD_TYPE_MANUAL = "🏧 تحويل يدوي"
BTN_METHOD_TYPE_CRYPTO = "🪙 عملة رقمية"
BTN_METHOD_TYPE_GATEWAY = "💳 بوابة دفع"
METHOD_NEW_CONFIRM = (
    "🧾 <b>مراجعة الطريقة الجديدة</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🏦 الاسم: {name}\n"
    "🏷 النوع: {type}\n"
    "📋 التعليمات: {instructions}\n"
    "🏧 الحساب: {account}\n"
    "📎 الإثبات: إجباري (قابل للتغيير لاحقاً)\n"
    "🧾 الرسوم: بلا رسوم (قابلة للضبط لاحقاً)\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "⚠️ ستظهر للمستخدمين فور إنشائها."
)
METHOD_CREATED = (
    "✅ <b>أُضيفت طريقة الشحن «{name}»</b>\n\n"
    "🔖 الكود الداخلي: <code>{code}</code>\n"
    "الخطوة التالية: اضبط الحدود والرسوم من بطاقة الطريقة إن لزم."
)
METHOD_TOGGLED_ON = "✅ فُعّلت طريقة الشحن «{name}» — صارت ظاهرة للمستخدمين."
METHOD_TOGGLED_OFF = (
    "⛔ أُوقفت طريقة الشحن «{name}» — لم تعد ظاهرة للمستخدمين.\n"
    "الطلبات السابقة عبرها تبقى كما هي."
)
METHOD_PROOF_TOGGLED = "📎 إثبات التحويل صار «{state}» لطريقة «{name}»."
METHOD_MOVED = "🔀 تغيّر ترتيب «{name}»."
METHOD_MOVE_EDGE = "ℹ️ هذه الطريقة في طرف القائمة أصلاً."

# ---------------------------- تقرير طرق الشحن --------------------------- #

METHODS_REPORT_TITLE = (
    "📊 <b>تقرير طرق الشحن</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "{lines}\n"
    "💰 الإجمالي المضاف: {total}\n"
    "🧾 إجمالي الرسوم المقتطعة: {fees}"
)
METHODS_REPORT_LINE = (
    "{state} <b>{name}</b>\n"
    "   ✅ معتمدة: {approved} · ⏳ معلّقة: {pending}\n"
    "   💰 أُضيف: {total} · 🧾 رسوم: {fees}\n"
)
METHODS_REPORT_EMPTY = "📊 لا توجد طرق شحن لعرض تقرير عنها."
```

### `texts/ar.py`  ·  مُحدَّث (مقتطف)  ·  344 سطراً (المعروض: 54 سطراً)

أسطر الرسوم والصافي في واجهة المستخدم.

```python
# ============================== الشحن ================================= #

DEPOSIT_METHODS_TITLE = (
    "➕ <b>شحن الرصيد</b>\n\n"
    "اختر طريقة التحويل المناسبة لك:"
)
DEPOSIT_METHODS_EMPTY = (
    "⚠️ لا توجد طرق شحن مفعّلة حالياً.\n"
    "تواصل مع الدعم الفني وسنفعّلها في أقرب وقت."
)
DEPOSIT_ASK_AMOUNT = (
    "💵 <b>{method}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "{instructions}\n"
    "{account}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "{limits}\n"
    "{fee_line}"
    "\nأرسل <b>المبلغ الذي حوّلته</b> كرقم."
)
#: يظهر فقط للطرق التي لها رسوم (وعندما يسمح الإعداد بإظهارها)
DEPOSIT_FEE_NOTICE = "🧾 رسوم هذه الطريقة: {fee} — تُخصم من المبلغ المحوَّل.\n"
DEPOSIT_ASK_REFERENCE = (
    "🧾 أرسل <b>رقم عملية التحويل</b> كما يظهر في إشعار الحوالة.\n\n"
    "المبلغ: {amount}"
)
DEPOSIT_ASK_PROOF = (
    "📸 أرسل <b>صورة الإيصال</b> (اختياري).\n\n"
    "يمكنك الضغط على «تخطي» إذا كان رقم العملية كافياً."
)
DEPOSIT_SUMMARY = (
    "🧾 <b>مراجعة طلب الشحن</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🏦 الطريقة: {method}\n"
    "💵 المبلغ المحوَّل: <b>{amount}</b>\n"
    "{fee_lines}"
    "🔢 رقم العملية: {reference}\n"
    "📸 الإيصال: {proof}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "سيراجع الفريق طلبك ويُضاف الرصيد بعد الاعتماد."
)
#: سطرا الرسوم والصافي داخل المراجعة وإشعار الاستلام
DEPOSIT_FEE_LINES = "🧾 رسوم الطريقة: {fee}\n💰 سيُضاف لرصيدك: <b>{net}</b>\n"
DEPOSIT_PROOF_ATTACHED = "مرفقة ✅"
DEPOSIT_PROOF_NONE = "بدون صورة"
DEPOSIT_CREATED = (
    "✅ <b>استلمنا طلب الشحن #{payment_id}</b>\n\n"
    "💵 المبلغ المحوَّل: {amount}\n"
    "{fee_lines}"
    "📊 الحالة: قيد المراجعة\n\n"
    "سيصلك إشعار فور اعتماده أو رفضه."
)
DEPOSITS_TITLE = "🧾 <b>طلبات الشحن</b>\n\n{lines}"
DEPOSITS_EMPTY = "📭 لا توجد طلبات شحن سابقة."
```

### `texts/templates.py`  ·  مُحدَّث (مقتطف)  ·  321 سطراً (المعروض: 23 سطراً)

إشعار استلام طلب الشحن صار يذكر الرسوم والصافي.

```python
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
    المستخدم بفارق بين ما حوّله وما أُضيف لرصيده.
    """
    body = f"طلب الشحن #{payment_id} بمبلغ {money(amount_units, symbol)} قيد المراجعة.\n"
    if fee_units > 0:
        expected = amount_units - fee_units if net_units is None else net_units
        body += (
            f"🧾 رسوم الطريقة: {money(fee_units, symbol)}\n"
            f"💵 المتوقع إضافته: {money(expected, symbol)}\n"
        )
    body += "سنعلمك فور اعتماده."
    return ("📥 تم استلام طلب الشحن", body)
```

### `scripts/boot_check.py`  ·  مُحدَّث (مقتطف)  ·  198 سطراً (المعروض: 10 سطراً)

تحذير صريح عند عدم وجود أي طريقة شحن مفعّلة.

```python
        active_methods = len(await services.payments.active_methods())
        if active_methods:
            ok("طرق الدفع الفعّالة:", active_methods)
        else:
            # بلا طريقة شحن واحدة مفعّلة لا يستطيع أي مستخدم شحن رصيده إطلاقاً
            warn(
                "لا توجد طريقة شحن مفعّلة — المستخدمون لن يتمكنوا من شحن أرصدتهم. "
                "أضفها من: /admin ← 💰 المدفوعات ← 🏦 طرق الشحن"
            )
            problems += 1
```

---

## الاختبارات

### `tests/unit/test_deposit_fees.py`  ·  جديد  ·  85 سطراً

11 اختبار وحدة لحساب الرسوم والتقريب والحدود.

```python
"""
اختبارات وحدة لحساب رسوم طرق الشحن (المرحلة 7).

لماذا اختبار مستقل بلا قاعدة بيانات؟
    لأن هذه الدوال هي المكان الوحيد الذي يقرر كم يُخصم من مال العميل،
    وأي خطأ تقريب فيها يتحول إلى فروق رصيد لا تُكتشف إلا متأخراً.
"""

from __future__ import annotations

import pytest

from core.exceptions import InvalidAmountError
from core.money import (
    FEE_SCALE,
    MAX_FEE_PERCENT_BP,
    MONEY_SCALE,
    deposit_fee_units,
    net_after_fee,
)


def test_no_fees_configured_means_zero_fee() -> None:
    """طريقة بلا رسوم: الصافي = كامل المبلغ."""
    fee, net = net_after_fee(100 * MONEY_SCALE)
    assert fee == 0
    assert net == 100 * MONEY_SCALE


def test_percent_fee_is_exact_for_round_values() -> None:
    """نسبة 2.5% على 1000 = 25 بالضبط (بلا كسور عائمة)."""
    fee = deposit_fee_units(1000 * MONEY_SCALE, percent_bp=250)
    assert fee == 25 * MONEY_SCALE


def test_fixed_and_percent_fees_add_up() -> None:
    """الرسوم النسبية والثابتة تُجمعان معاً على نفس الحوالة."""
    fee, net = net_after_fee(
        200 * MONEY_SCALE, percent_bp=100, fixed_units=5 * MONEY_SCALE  # 1% + 5
    )
    assert fee == 2 * MONEY_SCALE + 5 * MONEY_SCALE
    assert net == 200 * MONEY_SCALE - fee


def test_percent_fee_uses_half_up_rounding_on_units() -> None:
    """التقريب نصفي لأعلى على مستوى النقطة الواحدة (لا قص ولا float)."""
    # 1 نقطة × 50% = 0.5 نقطة ⇒ تُقرَّب إلى 1
    assert deposit_fee_units(1, percent_bp=FEE_SCALE // 2) == 1
    # 1 نقطة × 49.99% = 0.4999 ⇒ تُقرَّب إلى 0
    assert deposit_fee_units(1, percent_bp=FEE_SCALE // 2 - 1) == 0


def test_fee_never_exceeds_the_transfer_itself() -> None:
    """مهما كانت الإعدادات لا تتجاوز الرسوم مبلغ الحوالة (حماية من رصيد سالب)."""
    fee, net = net_after_fee(10 * MONEY_SCALE, percent_bp=MAX_FEE_PERCENT_BP, fixed_units=999999)
    assert fee == 10 * MONEY_SCALE
    assert net == 0


def test_hundred_percent_fee_is_allowed_but_zero_percent_is_default() -> None:
    """نسبة 100% مسموحة كحد أقصى، والافتراضي صفر."""
    assert deposit_fee_units(50 * MONEY_SCALE, percent_bp=MAX_FEE_PERCENT_BP) == 50 * MONEY_SCALE
    assert deposit_fee_units(50 * MONEY_SCALE) == 0


@pytest.mark.parametrize("bad_percent", [-1, MAX_FEE_PERCENT_BP + 1, 99_999])
def test_invalid_percent_is_rejected(bad_percent: int) -> None:
    """نسبة خارج المدى 0..100% ترفع خطأ مالياً واضحاً."""
    with pytest.raises(InvalidAmountError):
        deposit_fee_units(100 * MONEY_SCALE, percent_bp=bad_percent)


def test_negative_amount_or_fixed_fee_is_rejected() -> None:
    """المبالغ السالبة مرفوضة في الطرفين (المبلغ والرسوم الثابتة)."""
    with pytest.raises(InvalidAmountError):
        deposit_fee_units(-1, percent_bp=0)
    with pytest.raises(InvalidAmountError):
        deposit_fee_units(100, fixed_units=-5)


def test_fee_calculation_is_integer_only() -> None:
    """الناتج دائماً int — لا Decimal ولا float يتسرب إلى طبقة المال."""
    fee, net = net_after_fee(123_456, percent_bp=333, fixed_units=77)
    assert isinstance(fee, int) and isinstance(net, int)
    assert fee + net == 123_456  # لا تتبخّر أي نقطة في الحساب
```

### `tests/integration/test_payments_phase7.py`  ·  جديد  ·  611 سطراً

34 اختبار تكامل للخدمة والشاشات والصلاحيات والدورة الكاملة.

```python
"""
اختبارات المرحلة 7 — نظام الدفع والشحن المتقدم.

ما تغطيه:
    1. إدارة طرق الشحن من الخدمة: إنشاء، تعديل محروس، ترتيب، تفعيل/إيقاف.
    2. الرسوم: حسابها، تخزينها كلقطة على الطلب، وأثرها على المبلغ المضاف.
    3. شاشات اللوحة: قائمة الطرق، البطاقة، التقرير، التصفية، البحث.
    4. الصلاحيات: من لا يملك `payments.methods` لا يرى الأزرار ولا ينفّذ.
    5. جانب المستخدم: رؤية الرسوم والصافي قبل الإرسال.
"""

from __future__ import annotations

import pytest

from core.enums import PaymentStatus
from core.exceptions import PermissionDeniedError, ValidationError
from core.money import MONEY_SCALE
from database.models import User
from database.repositories import Repositories
from handlers.admin import payment_methods as methods_admin
from handlers.admin import payments as payments_admin
from handlers.user import deposit as user_deposit
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


@pytest.fixture
async def fee_method(services: ServiceContainer, super_admin: User):
    """طريقة شحن برسوم 2.5% + 1 عملة ثابتة (كمحفظة إلكترونية حقيقية)."""
    method = await services.payments.create_method(
        super_admin,
        name_ar="محفظة الرسوم",
        instructions_ar="حوّل ثم أرسل رقم العملية",
        account_details="770000000",
        fee_percent_bp=250,
        fee_fixed_units=1 * MONEY_SCALE,
    )
    return method


async def _submit(services: ServiceContainer, user: User, method, amount: str = "100"):
    """إرسال طلب شحن بمبلغ محدد عبر طريقة محددة."""
    return await services.payments.create_payment(
        user,
        method_id=method.id,
        raw_amount=amount,
        transaction_reference=f"TRX-{method.id}-{amount}",
    )


# ======================================================================== #
#                      1) إدارة طرق الشحن (الخدمة)                         #
# ======================================================================== #


async def test_create_method_derives_unique_code_and_appends_to_end(
    services: ServiceContainer, super_admin: User, payment_method
) -> None:
    """الكود يُشتق تلقائياً ويكون فريداً، والطريقة الجديدة تُضاف آخر القائمة."""
    first = await services.payments.create_method(super_admin, name_ar="محفظة كريمي")
    second = await services.payments.create_method(super_admin, name_ar="محفظة كريمي")

    assert first.code != second.code
    assert second.sort_order > first.sort_order >= payment_method.sort_order
    assert first.is_active == 1


async def test_create_method_requires_methods_permission(
    services: ServiceContainer, user: User
) -> None:
    """المستخدم العادي لا يستطيع إنشاء طريقة شحن."""
    with pytest.raises(PermissionDeniedError):
        await services.payments.create_method(user, name_ar="طريقة مزيفة")


async def test_update_method_rejects_unknown_field(
    services: ServiceContainer, super_admin: User, payment_method
) -> None:
    """الحقول غير المسموحة (مثل الكود) لا تُعدَّل عبر update_method."""
    with pytest.raises(ValidationError):
        await services.payments.update_method(super_admin, payment_method.id, code="hacked")


async def test_update_method_validates_fee_range(
    services: ServiceContainer, super_admin: User, payment_method
) -> None:
    """نسبة رسوم أكبر من 100% مرفوضة قبل الوصول لقاعدة البيانات."""
    with pytest.raises(ValidationError):
        await services.payments.update_method(
            super_admin, payment_method.id, fee_percent_bp=10_001
        )
    reloaded = await services.payments.get_method(payment_method.id, require_active=False)
    assert reloaded.fee_percent_bp == 0


async def test_update_method_rejects_min_greater_than_max(
    services: ServiceContainer, super_admin: User, payment_method
) -> None:
    """حدّ أدنى أكبر من الحد الأقصى يُرفض برسالة عربية واضحة."""
    await services.payments.update_method(
        super_admin, payment_method.id, max_amount_units=50 * MONEY_SCALE
    )
    with pytest.raises(ValidationError):
        await services.payments.update_method(
            super_admin, payment_method.id, min_amount_units=90 * MONEY_SCALE
        )


async def test_update_method_keeps_instruction_lines(
    services: ServiceContainer, super_admin: User, payment_method
) -> None:
    """تعليمات التحويل تحتفظ بأسطرها (خطوات مرقّمة لا تُدمج في سطر واحد)."""
    await services.payments.update_method(
        super_admin, payment_method.id, instructions_ar="1- حوّل المبلغ\n2- أرسل الإيصال"
    )
    reloaded = await services.payments.get_method(payment_method.id, require_active=False)
    assert reloaded.instructions_ar.splitlines() == ["1- حوّل المبلغ", "2- أرسل الإيصال"]


async def test_move_method_swaps_order_and_stops_at_edges(
    services: ServiceContainer, super_admin: User, payment_method
) -> None:
    """أزرار الترتيب تبدّل الطريقتين، وفي الطرف تُرجع False بلا تغيير."""
    second = await services.payments.create_method(super_admin, name_ar="طريقة ثانية")

    assert await services.payments.move_method(super_admin, second.id, up=True) is True
    first_after = await services.payments.get_method(payment_method.id, require_active=False)
    second_after = await services.payments.get_method(second.id, require_active=False)
    assert second_after.sort_order < first_after.sort_order

    # صارت في القمة ⇒ لا جارة أعلى منها
    assert await services.payments.move_method(super_admin, second.id, up=True) is False


async def test_disabled_method_hidden_from_users_but_kept_in_history(
    services: ServiceContainer, super_admin: User, user: User, payment_method
) -> None:
    """إيقاف الطريقة يخفيها عن المستخدم ولا يحذفها ولا يمس طلباتها السابقة."""
    payment = await _submit(services, user, payment_method, amount="10")
    await services.payments.set_method_active(super_admin, payment_method.id, False)

    assert payment_method.id not in {m.id for m in await services.payments.active_methods()}
    assert payment_method.id in {
        m.id for m in await services.payments.all_methods(super_admin)
    }
    stored = await services.payments.admin_get(super_admin, payment.id)
    assert stored.method_id == payment_method.id


# ======================================================================== #
#                       2) الرسوم في دورة الشحن                            #
# ======================================================================== #


async def test_payment_stores_fee_snapshot_on_creation(
    services: ServiceContainer, user: User, fee_method
) -> None:
    """الرسوم تُحسب وتُخزَّن على الطلب: 2.5% من 100 + 1 = 3.5، والصافي 96.5."""
    payment = await _submit(services, user, fee_method, amount="100")

    assert payment.fee_units == int(3.5 * MONEY_SCALE)
    assert payment.net_units == int(96.5 * MONEY_SCALE)


async def test_changing_method_fee_does_not_touch_existing_payments(
    services: ServiceContainer, super_admin: User, user: User, fee_method
) -> None:
    """رفع الرسوم لاحقاً لا يغيّر طلباً أُرسل قبل التغيير (لقطة محفوظة)."""
    payment = await _submit(services, user, fee_method, amount="100")
    await services.payments.update_method(super_admin, fee_method.id, fee_percent_bp=5_000)

    reloaded = await services.payments.admin_get(super_admin, payment.id)
    assert reloaded.fee_units == payment.fee_units


async def test_approve_credits_net_amount_by_default(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, fee_method
) -> None:
    """الاعتماد يضيف الصافي بعد الرسوم تلقائياً — لا المبلغ المحوَّل كاملاً."""
    payment = await _submit(services, user, fee_method, amount="100")
    transaction = await services.payments.approve(admin, payment.id)

    assert transaction.amount_units == payment.net_units
    refreshed = await repos.users.get_by_id(user.id)
    assert refreshed.balance_units == payment.net_units


async def test_admin_can_override_credited_amount_above_net(
    services: ServiceContainer, user: User, admin: User, fee_method
) -> None:
    """يبقى للأدمن حق اعتماد مبلغ مختلف (تسوية خاصة) ويُسجَّل الفرق في الملاحظة."""
    payment = await _submit(services, user, fee_method, amount="100")
    transaction = await services.payments.approve(
        admin, payment.id, credited_units=100 * MONEY_SCALE
    )

    assert transaction.amount_units == 100 * MONEY_SCALE
    stored = await services.payments.admin_get(admin, payment.id)
    assert "رسوم الطريقة" in (stored.admin_note or "")


async def test_amount_smaller_than_fees_is_rejected(
    services: ServiceContainer, super_admin: User, user: User, fee_method
) -> None:
    """مبلغ لا يغطي الرسوم يُرفض عند الإنشاء بدل أن يُعتمد بصفر رصيد."""
    await services.payments.update_method(
        super_admin, fee_method.id, fee_fixed_units=20 * MONEY_SCALE, min_amount_units=0
    )
    with pytest.raises(ValidationError):
        await _submit(services, user, fee_method, amount="5")


async def test_methods_report_counts_real_rows_only(
    services: ServiceContainer, user: User, admin: User, super_admin: User, fee_method
) -> None:
    """التقرير يعكس قاعدة البيانات: معتمد ومعلّق ورسوم محصّلة فعلاً."""
    approved = await _submit(services, user, fee_method, amount="100")
    await services.payments.approve(admin, approved.id)
    await _submit(services, user, fee_method, amount="50")  # يبقى معلّقاً

    report = {row["method_id"]: row for row in await services.payments.methods_report(super_admin)}
    row = report[fee_method.id]
    assert row["approved_count"] == 1
    assert row["pending_count"] == 1
    assert row["total_units"] == approved.net_units
    assert row["fee_units"] == approved.fee_units


# ======================================================================== #
#                        3) شاشات طرق الشحن                                #
# ======================================================================== #


async def test_methods_home_warns_when_no_methods_exist(
    bot: FakeBot, context: FakeContext, super_admin: User
) -> None:
    """بلا طرق شحن: رسالة صريحة أن المستخدمين لا يستطيعون الشحن + زر الإضافة."""
    await load_user(bot, context, super_admin)
    await press(
        bot, context, methods_admin.methods_home_screen, pack("pm", "home"), super_admin.telegram_id
    )

    assert "لا يستطيع أي مستخدم شحن رصيده" in bot.last.text
    assert "pm:new:v1" in bot.last.buttons


async def test_methods_home_lists_methods_with_state_and_fees(
    bot: FakeBot, context: FakeContext, super_admin: User, fee_method
) -> None:
    """قائمة الطرق تعرض حالة كل طريقة ورسومها وحدودها."""
    await load_user(bot, context, super_admin)
    await press(
        bot, context, methods_admin.methods_home_screen, pack("pm", "home"), super_admin.telegram_id
    )

    assert "محفظة الرسوم" in bot.last.text
    assert "2.5%" in bot.last.text
    assert f"pm:view:{fee_method.id}:v1" in bot.last.buttons


async def test_method_card_shows_settings_and_usage(
    bot: FakeBot, context: FakeContext, super_admin: User, user: User, services: ServiceContainer, fee_method
) -> None:
    """بطاقة الطريقة تعرض الإعدادات وأرقام الاستخدام الحقيقية."""
    await _submit(services, user, fee_method, amount="40")
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        methods_admin.method_card_screen,
        pack("pm", "view", fee_method.id),
        super_admin.telegram_id,
    )

    assert "محفظة الرسوم" in bot.last.text
    assert "معلّقة 1" in bot.last.text
    assert f"pm:edit:{fee_method.id}:feep:v1" in bot.last.buttons


async def test_toggle_method_switches_visibility_for_users(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer, fee_method
) -> None:
    """زر الإيقاف يُخفي الطريقة عن المستخدمين فوراً ويُعلم الأدمن بذلك."""
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        methods_admin.toggle_method,
        pack("pm", "toggle", fee_method.id),
        super_admin.telegram_id,
    )

    assert "أُوقفت طريقة الشحن" in " ".join(message.text for message in bot.sent)
    assert fee_method.id not in {m.id for m in await services.payments.active_methods()}


async def test_toggle_proof_flips_requirement(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer, fee_method
) -> None:
    """زر الإثبات ينقل الطريقة بين «إجباري» و«اختياري»."""
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        methods_admin.toggle_proof,
        pack("pm", "proof", fee_method.id),
        super_admin.telegram_id,
    )

    reloaded = await services.payments.get_method(fee_method.id, require_active=False)
    assert not reloaded.requires_proof


async def test_edit_fee_percent_flow_updates_method(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer, fee_method
) -> None:
    """محادثة تعديل النسبة: «1.25» تُخزَّن 125 نقطة أساس."""
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        methods_admin.start_edit_field,
        pack("pm", "edit", fee_method.id, "feep"),
        super_admin.telegram_id,
    )
    await write(bot, context, methods_admin.receive_field_value, "1.25", super_admin.telegram_id)

    reloaded = await services.payments.get_method(fee_method.id, require_active=False)
    assert reloaded.fee_percent_bp == 125


async def test_edit_max_limit_with_zero_clears_it(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer, fee_method
) -> None:
    """إرسال 0 في الحد الأقصى يعني «بلا حد» (NULL) لا صفراً."""
    await services.payments.update_method(
        super_admin, fee_method.id, max_amount_units=90 * MONEY_SCALE
    )
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        methods_admin.start_edit_field,
        pack("pm", "edit", fee_method.id, "max"),
        super_admin.telegram_id,
    )
    await write(bot, context, methods_admin.receive_field_value, "0", super_admin.telegram_id)

    reloaded = await services.payments.get_method(fee_method.id, require_active=False)
    assert reloaded.max_amount_units is None


async def test_new_method_conversation_creates_visible_method(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer
) -> None:
    """محادثة الإضافة الكاملة تُنشئ طريقة ظاهرة للمستخدمين فوراً."""
    await load_user(bot, context, super_admin)
    await press(bot, context, methods_admin.start_new_method, pack("pm", "new"), super_admin.telegram_id)
    await write(bot, context, methods_admin.receive_method_name, "بنك اليمن", super_admin.telegram_id)
    await write(
        bot,
        context,
        methods_admin.receive_method_instructions,
        "1- حوّل\n2- أرسل الإيصال",
        super_admin.telegram_id,
    )
    await write(bot, context, methods_admin.receive_method_account, "123-456", super_admin.telegram_id)
    await press(
        bot,
        context,
        methods_admin.receive_method_type,
        pack("pm", "type", "manual"),
        super_admin.telegram_id,
    )
    await press(bot, context, methods_admin.confirm_new_method, pack("flow", "confirm"), super_admin.telegram_id)

    names = {method.name_ar for method in await services.payments.active_methods()}
    assert "بنك اليمن" in names


async def test_methods_report_screen_shows_totals(
    bot: FakeBot, context: FakeContext, super_admin: User, user: User, admin: User, services: ServiceContainer, fee_method
) -> None:
    """شاشة التقرير تجمع المضاف والرسوم عبر كل الطرق."""
    payment = await _submit(services, user, fee_method, amount="100")
    await services.payments.approve(admin, payment.id)

    await load_user(bot, context, super_admin)
    await press(
        bot, context, methods_admin.methods_report_screen, pack("pm", "rep"), super_admin.telegram_id
    )

    assert "تقرير طرق الشحن" in bot.last.text
    assert "إجمالي الرسوم المقتطعة" in bot.last.text


async def test_support_without_methods_permission_cannot_open_methods(
    bot: FakeBot, context: FakeContext, db, repos: Repositories
) -> None:
    """دور الدعم يرى المدفوعات لكنه لا يفتح شاشة طرق الشحن ولا يرى زرها."""
    async with db.transaction() as tx:
        support = await repos.users.create(
            tx, telegram_id=515151, username="supportman", first_name="دعم", role="support"
        )

    await load_user(bot, context, support)
    await press(
        bot, context, methods_admin.methods_home_screen, pack("pm", "home"), support.telegram_id
    )
    assert not bot.sent  # الرفض يحدث قبل إرسال أي شاشة
    assert bot.answers and "صلاحية" in bot.answers[-1]["text"]

    bot.clear()
    await press(
        bot, context, payments_admin.payments_list_screen, pack("ap", "list", "pend", 1), support.telegram_id
    )
    assert "pm:home:v1" not in bot.last.buttons


# ======================================================================== #
#                    4) تصفية طلبات الشحن والبحث                           #
# ======================================================================== #


async def test_payments_list_filters_by_status(
    bot: FakeBot, context: FakeContext, admin: User, user: User, services: ServiceContainer, payment_method
) -> None:
    """تصفية «معتمدة» تعرض المعتمد فقط ولا تعرض المعلّق."""
    approved = await _submit(services, user, payment_method, amount="20")
    await services.payments.approve(admin, approved.id)
    pending = await _submit(services, user, payment_method, amount="30")

    await load_user(bot, context, admin)
    await press(
        bot, context, payments_admin.payments_list_screen, pack("ap", "list", "ok", 1), admin.telegram_id
    )

    assert f"#{approved.id}" in bot.last.text
    assert f"#{pending.id}" not in bot.last.text
    assert f"ap:view:{approved.id}:ok:1:v1" in bot.last.buttons


async def test_payments_list_all_filter_includes_every_status(
    bot: FakeBot, context: FakeContext, admin: User, user: User, services: ServiceContainer, payment_method
) -> None:
    """تصفية «الكل» تشمل المعلّق والمعتمد معاً."""
    approved = await _submit(services, user, payment_method, amount="20")
    await services.payments.approve(admin, approved.id)
    pending = await _submit(services, user, payment_method, amount="30")

    await load_user(bot, context, admin)
    await press(
        bot, context, payments_admin.payments_list_screen, pack("ap", "list", "all", 1), admin.telegram_id
    )

    assert f"#{approved.id}" in bot.last.text and f"#{pending.id}" in bot.last.text


async def test_search_finds_payment_by_reference(
    bot: FakeBot, context: FakeContext, admin: User, user: User, services: ServiceContainer, payment_method
) -> None:
    """البحث برقم العملية يفتح الطلب المطابق كزر مباشر."""
    payment = await _submit(services, user, payment_method, amount="25")

    await load_user(bot, context, admin)
    await press(bot, context, payments_admin.start_search, pack("ap", "find"), admin.telegram_id)
    await write(
        bot, context, payments_admin.receive_search_term, payment.transaction_reference, admin.telegram_id
    )

    assert f"ap:view:{payment.id}:all:1:v1" in bot.last.buttons


async def test_search_reports_no_results_clearly(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """بحث بلا نتائج يعطي رسالة صريحة لا قائمة فارغة."""
    await load_user(bot, context, admin)
    await press(bot, context, payments_admin.start_search, pack("ap", "find"), admin.telegram_id)
    await write(bot, context, payments_admin.receive_search_term, "TRX-NOPE", admin.telegram_id)

    assert "لا يوجد طلب شحن مطابق" in bot.last.text


async def test_payment_card_shows_fee_and_net(
    bot: FakeBot, context: FakeContext, admin: User, user: User, services: ServiceContainer, fee_method
) -> None:
    """بطاقة الطلب تفصل المبلغ المحوَّل عن الرسوم وعن الصافي."""
    payment = await _submit(services, user, fee_method, amount="100")

    await load_user(bot, context, admin)
    await press(
        bot,
        context,
        payments_admin.payment_card_screen,
        pack("ap", "view", payment.id, "pend", 1),
        admin.telegram_id,
    )

    assert "رسوم الطريقة" in bot.last.text
    assert "الصافي للمستخدم" in bot.last.text


# ======================================================================== #
#                       5) جانب المستخدم (الشفافية)                        #
# ======================================================================== #


async def test_user_sees_fee_notice_when_choosing_method(
    bot: FakeBot, context: FakeContext, user: User, fee_method
) -> None:
    """المستخدم يرى رسوم الطريقة قبل أن يكتب المبلغ."""
    await load_user(bot, context, user)
    await press(
        bot, context, user_deposit.choose_method, pack("dep", "method", fee_method.id), user.telegram_id
    )

    assert "رسوم هذه الطريقة" in bot.last.text


async def test_user_summary_shows_net_amount(
    bot: FakeBot, context: FakeContext, user: User, fee_method
) -> None:
    """مراجعة الطلب تُظهر ما سيُضاف فعلاً للرصيد بعد خصم الرسوم."""
    await load_user(bot, context, user)
    await press(
        bot, context, user_deposit.choose_method, pack("dep", "method", fee_method.id), user.telegram_id
    )
    await write(bot, context, user_deposit.receive_amount, "100", user.telegram_id)
    await write(bot, context, user_deposit.receive_reference, "TRX-USER-1", user.telegram_id)
    await press(bot, context, user_deposit.skip_proof, pack("flow", "skip"), user.telegram_id)

    assert "سيُضاف لرصيدك" in bot.last.text
    assert "96.50" in bot.last.text


async def test_fee_display_can_be_switched_off(
    bot: FakeBot, context: FakeContext, user: User, services: ServiceContainer, fee_method
) -> None:
    """إعداد `deposit_fee_visible` يخفي تفصيل الرسوم عن المستخدم دون تعطيلها."""
    await services.settings.set("deposit_fee_visible", "0")

    await load_user(bot, context, user)
    await press(
        bot, context, user_deposit.choose_method, pack("dep", "method", fee_method.id), user.telegram_id
    )

    assert "رسوم هذه الطريقة" not in bot.last.text


async def test_user_cannot_deposit_when_no_active_methods(
    bot: FakeBot, context: FakeContext, user: User, super_admin: User, services: ServiceContainer, payment_method
) -> None:
    """بلا طرق مفعّلة يرى المستخدم رسالة واضحة بدل قائمة فارغة."""
    await services.payments.set_method_active(super_admin, payment_method.id, False)

    await load_user(bot, context, user)
    await press(bot, context, user_deposit.start_deposit, pack("dep", "start"), user.telegram_id)

    assert "لا توجد طرق شحن مفعّلة" in bot.last.text


async def test_full_deposit_cycle_with_fees_credits_net_balance(
    bot: FakeBot,
    context: FakeContext,
    user: User,
    admin: User,
    services: ServiceContainer,
    repos: Repositories,
    fee_method,
) -> None:
    """
    الدورة الكاملة مع رسوم: المستخدم يرسل ← الأدمن يعتمد ← يُضاف الصافي.

    هذه هي الضمانة النهائية للمرحلة 7: ما يراه المستخدم في المراجعة هو
    بالضبط ما يصل رصيده بعد الاعتماد.
    """
    await load_user(bot, context, user)
    await press(
        bot, context, user_deposit.choose_method, pack("dep", "method", fee_method.id), user.telegram_id
    )
    await write(bot, context, user_deposit.receive_amount, "200", user.telegram_id)
    await write(bot, context, user_deposit.receive_reference, "TRX-CYCLE-7", user.telegram_id)
    await press(bot, context, user_deposit.skip_proof, pack("flow", "skip"), user.telegram_id)
    await press(bot, context, user_deposit.confirm_deposit, pack("flow", "confirm"), user.telegram_id)

    payment = (await services.payments.list_for_user(user, limit=1))[0]
    assert payment.status == PaymentStatus.PENDING
    assert payment.fee_units == int(6 * MONEY_SCALE)  # 2.5% من 200 = 5 + 1 ثابت

    transaction = await services.payments.approve(admin, payment.id)
    refreshed = await repos.users.get_by_id(user.id)

    assert transaction.amount_units == int(194 * MONEY_SCALE)
    assert refreshed.balance_units == int(194 * MONEY_SCALE)
```

