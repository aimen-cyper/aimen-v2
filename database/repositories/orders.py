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
    "last_checked_at",
    "last_check_ok_at",
    "last_check_error",
    "check_fail_streak",
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

    async def list_by_statuses(
        self,
        statuses: Sequence[str] | None = None,
        *,
        user_id: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Order]:
        """
        قائمة الطلبات لعدة حالات دفعة واحدة (قوائم لوحة الأدمن).

        المدخلات:
            statuses : الحالات المطلوبة، و`None` أو قائمة فارغة تعني كل الحالات.
            user_id  : حصر النتائج بمستخدم واحد (تبويب «طلباته» في بطاقة المستخدم).
            limit/offset : الترقيم.

        المخرجات: قائمة طلبات مرتبة من الأحدث إلى الأقدم.
        """
        where, params = self._admin_filter(statuses, user_id)
        rows = await self.db.fetchall(
            f"SELECT * FROM orders WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        return Order.from_rows(rows)

    async def count_by_statuses(
        self, statuses: Sequence[str] | None = None, *, user_id: int | None = None
    ) -> int:
        """عدد الطلبات المطابقة لنفس مرشّحات `list_by_statuses` (لحساب عدد الصفحات)."""
        where, params = self._admin_filter(statuses, user_id)
        return await self.count("orders", where, tuple(params))

    @staticmethod
    def _admin_filter(
        statuses: Sequence[str] | None, user_id: int | None
    ) -> tuple[str, list[Any]]:
        """بناء شرط WHERE المشترك بين قائمة الأدمن وعدّادها (مصدر واحد للمنطق)."""
        clauses: list[str] = ["1 = 1"]
        params: list[Any] = []
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(statuses)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        return " AND ".join(clauses), params

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

    # ------------------------- الإحصائيات المالية (م10) ------------------------- #
    #
    # دلالة الأرقام (موحَّدة في كل التقارير):
    #   • الفترة تُحسب بوقت إنشاء الطلب (created_at) لأن الخصم يقع وقتها.
    #   • الإجمالي (gross) = Σ cost_units · المسترجع = Σ refund_amount_units.
    #   • الإيراد الصافي = الإجمالي − المسترجع. الطلب الملغى/الفاشل المسترجع كاملاً يُنتج صفراً،
    #     والجزئي يُحتسب بما بقي مخصوماً فعلاً. (المجموع الخام القديم كان يُضخّم الإيراد.)

    async def period_totals(self, start_iso: str, end_iso: str) -> dict[str, int]:
        """
        مجاميع فترة: عدد الطلبات، الإجمالي، المسترجع، الصافي، وعدد المشترين المختلفين.

        المخرجات: orders_count, gross_units, refund_units, net_units, buyers.
        """
        row = await self.db.fetchone(
            """
            SELECT COUNT(*)                                   AS orders_count,
                   COALESCE(SUM(cost_units), 0)               AS gross_units,
                   COALESCE(SUM(refund_amount_units), 0)      AS refund_units,
                   COUNT(DISTINCT user_id)                    AS buyers
              FROM orders
             WHERE created_at >= ? AND created_at < ?
            """,
            (start_iso, end_iso),
        )
        gross = int(row["gross_units"]) if row else 0
        refund = int(row["refund_units"]) if row else 0
        return {
            "orders_count": int(row["orders_count"]) if row else 0,
            "gross_units": gross,
            "refund_units": refund,
            "net_units": gross - refund,
            "buyers": int(row["buyers"]) if row else 0,
        }

    async def sum_net_between(self, start_iso: str, end_iso: str) -> int:
        """الإيراد الصافي لفترة (الإجمالي − المسترجع) بوحدات المال الصحيحة."""
        return (await self.period_totals(start_iso, end_iso))["net_units"]

    async def status_counts_between(self, start_iso: str, end_iso: str) -> dict[str, int]:
        """عدد طلبات الفترة في كل حالة."""
        rows = await self.db.fetchall(
            """
            SELECT status, COUNT(*) AS c FROM orders
             WHERE created_at >= ? AND created_at < ? GROUP BY status
            """,
            (start_iso, end_iso),
        )
        return {row["status"]: int(row["c"]) for row in rows}

    async def profit_inputs(self, start_iso: str, end_iso: str) -> dict[str, int]:
        """
        مدخلات الربح التقديري لفترة — **للطلبات المنتهية فقط** (مكتمل/جزئي).

        لماذا المنتهية فقط؟ إيراد الطلب الجاري غير مُحقَّق وقد يُسترجع، فخلطه بتكلفة مزود
        لم تُحسم يعطي ربحاً وهمياً. ولماذا «المغطّاة» فقط؟ تكلفة المزود تُسجَّل حين يردّ
        المزود بها؛ الطلب بلا تكلفة مسجّلة لا يدخل الحساب ويُعلن نسبة التغطية بدل التخمين.

        التكلفة الفعلية للطلب الجزئي تُقسَّم بنسبة ما بقي مخصوماً: `تكلفة × (cost−refund)/cost`
        (المزود لم يُسلّم الباقي). تُحسب بحساب صحيح في بايثون للصفوف ذات الاسترجاع (قليلة)،
        وفي SQL لغيرها (لا مضروبات ضخمة تتحول إلى أعداد عشرية).

        المخرجات:
            eligible_orders / eligible_net_units : كل الطلبات المنتهية وصافيها.
            covered_orders  / covered_net_units  : المغطّاة بتكلفة مزود وصافيها.
            covered_cost_units                   : تكلفة المزود الفعلية لها.
        """
        eligible = await self.db.fetchone(
            """
            SELECT COUNT(*) AS n, COALESCE(SUM(cost_units - refund_amount_units), 0) AS net
              FROM orders
             WHERE created_at >= ? AND created_at < ? AND status IN ('completed', 'partial')
            """,
            (start_iso, end_iso),
        )
        full = await self.db.fetchone(
            """
            SELECT COUNT(*) AS n,
                   COALESCE(SUM(cost_units), 0) AS net,
                   COALESCE(SUM(provider_cost_units), 0) AS cost
              FROM orders
             WHERE created_at >= ? AND created_at < ? AND status IN ('completed', 'partial')
               AND provider_cost_units IS NOT NULL AND refund_amount_units = 0
            """,
            (start_iso, end_iso),
        )
        prorated = await self.db.fetchall(
            """
            SELECT cost_units, refund_amount_units, provider_cost_units FROM orders
             WHERE created_at >= ? AND created_at < ? AND status IN ('completed', 'partial')
               AND provider_cost_units IS NOT NULL AND refund_amount_units > 0
            """,
            (start_iso, end_iso),
        )
        covered_orders = int(full["n"]) if full else 0
        covered_net = int(full["net"]) if full else 0
        covered_cost = int(full["cost"]) if full else 0
        for row in prorated:
            cost, refund, provider_cost = (int(row[k]) for k in ("cost_units", "refund_amount_units", "provider_cost_units"))
            net = cost - refund
            covered_orders += 1
            covered_net += net
            covered_cost += (provider_cost * net) // cost if cost > 0 else provider_cost
        return {
            "eligible_orders": int(eligible["n"]) if eligible else 0,
            "eligible_net_units": int(eligible["net"]) if eligible else 0,
            "covered_orders": covered_orders,
            "covered_net_units": covered_net,
            "covered_cost_units": covered_cost,
        }

    async def count_between(self, start_iso: str, end_iso: str) -> int:
        """عدد الطلبات المنشأة بين تاريخين (للإحصائيات)."""
        return await self.count("orders", "created_at >= ? AND created_at < ?", (start_iso, end_iso))

    async def count_between_by_status(
        self, start_iso: str, end_iso: str, statuses: Sequence[str]
    ) -> int:
        """عدد الطلبات بين تاريخين ضمن حالات محددة (نسبة النجاح/الفشل)."""
        placeholders = ", ".join("?" for _ in statuses)
        return await self.count(
            "orders",
            f"created_at >= ? AND created_at < ? AND status IN ({placeholders})",
            [start_iso, end_iso, *statuses],
        )

    async def top_services(
        self, *, start_iso: str, end_iso: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """
        أكثر الخدمات طلباً خلال فترة (مرتبة بعدد الطلبات ثم بالصافي).

        المخرجات: صفوف فيها service_name و orders_count و total_units (الصافي) و gross_units.
        """
        rows = await self.db.fetchall(
            """
            SELECT service_name_snapshot                         AS service_name,
                   COUNT(*)                                       AS orders_count,
                   COALESCE(SUM(cost_units), 0)                   AS gross_units,
                   COALESCE(SUM(cost_units - refund_amount_units), 0) AS total_units
              FROM orders
             WHERE created_at >= ? AND created_at < ?
             GROUP BY service_id
             ORDER BY orders_count DESC, total_units DESC, service_id
             LIMIT ?
            """,
            (start_iso, end_iso, limit),
        )
        return [dict(row) for row in rows]

    async def top_buyers(self, *, start_iso: str, end_iso: str, limit: int = 5) -> list[dict[str, Any]]:
        """
        أكثر العملاء إنفاقاً **صافياً** خلال فترة (من الطلبات لا من عدّاد المستخدم المتراكم).

        المخرجات: صفوف فيها user_id و orders_count و net_units (الأعلى أولاً، بلا أصفار).
        """
        rows = await self.db.fetchall(
            """
            SELECT user_id,
                   COUNT(*) AS orders_count,
                   COALESCE(SUM(cost_units - refund_amount_units), 0) AS net_units
              FROM orders
             WHERE created_at >= ? AND created_at < ?
             GROUP BY user_id
            HAVING net_units > 0
             ORDER BY net_units DESC, user_id
             LIMIT ?
            """,
            (start_iso, end_iso, limit),
        )
        return [dict(row) for row in rows]

    async def minute_buckets(self, start_iso: str, end_iso: str) -> list[dict[str, Any]]:
        """
        تجميع الطلبات بالدقيقة (UTC) بدل اليوم: يترك للخدمة تجميعها بأيام **محلية**.

        لماذا؟ `substr(created_at,1,10)` يقسّم اليوم عند منتصف الليل UTC لا المحلي، فتظهر
        طلبات ما بعد الثالثة فجراً (توقيت عدن) في اليوم الخطأ. التجميع بالدقيقة صحيح
        لأي إزاحة (حتى نصف الساعة) وعدد الصفوف لا يتجاوز عدد الطلبات.
        """
        rows = await self.db.fetchall(
            """
            SELECT substr(created_at, 1, 16)                    AS minute,
                   COUNT(*)                                      AS orders_count,
                   COALESCE(SUM(cost_units), 0)                  AS gross_units,
                   COALESCE(SUM(refund_amount_units), 0)         AS refund_units
              FROM orders
             WHERE created_at >= ? AND created_at < ?
             GROUP BY minute
             ORDER BY minute
            """,
            (start_iso, end_iso),
        )
        return [dict(row) for row in rows]

    async def export_rows(self, start_iso: str, end_iso: str, *, limit: int) -> list[dict[str, Any]]:
        """
        صفوف طلبات الفترة للتصدير (الأقدم أولاً). لا رابط العميل ولا معرّف تيليجرام عمداً.

        المخرجات: حتى `limit` صفاً (اطلب سقفاً+1 لمعرفة هل قُطعت النتيجة).
        """
        rows = await self.db.fetchall(
            """
            SELECT id, public_code, created_at, user_id, service_name_snapshot AS service_name,
                   quantity, status, cost_units, refund_amount_units, provider_cost_units,
                   delivered_quantity
              FROM orders
             WHERE created_at >= ? AND created_at < ?
             ORDER BY id
             LIMIT ?
            """,
            (start_iso, end_iso, limit),
        )
        return [dict(row) for row in rows]

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

        ملاحظة: يُحترم `next_check_at` هنا أيضاً، لأن الطلب الذي فشل إرساله مؤقتاً
        يعود إلى pending بموعد محاولة مؤجَّل؛ وتجاهل الموعد يعني إغراق المزود
        بمحاولات متتالية بلا تهدئة.
        """
        now = utc_now_iso()
        candidates = await tx.fetchall(
            """
            SELECT id FROM orders
             WHERE status = 'pending'
               AND (next_check_at IS NULL OR next_check_at <= ?)
               AND (locked_until IS NULL OR locked_until < ?)
             ORDER BY id LIMIT ?
            """,
            (now, now, limit),
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

    async def renew_submit_lock(self, tx: Tx, order_id: int, *, worker: str, lock_seconds: int = ORDER_LOCK_SECONDS) -> bool:
        """
        تمديد قفل طلب في `submitting` قبل إرساله فعلاً.

        الفائدة: دفعة من عدة طلبات تُحجز بقفل واحد، وقد يبدأ إرسال آخرها بعد انتهاء قفله
        فيحسبه الاسترداد الدوري عالقاً. التمديد مشروط بأن يظل الطلب لهذا العامل.
        """
        result = await tx.execute(
            """
            UPDATE orders SET locked_until = ?, updated_at = ?
             WHERE id = ? AND status = 'submitting' AND locked_by = ?
            """,
            (iso_plus_seconds(lock_seconds), self.now(), order_id, worker),
        )
        return result.rowcount == 1

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

    async def recover_submitting_orders(self, tx: Tx, *, only_expired: bool = False) -> list[int]:
        """
        معالجة الطلبات العالقة في حالة submitting (بعد إعادة تشغيل مفاجئ أو انتهاء مهلة جولة الإرسال).

        القاعدة: إذا لم يُسجَّل رقم الطلب عند المزود فالنتيجة غير مؤكدة
        (ربما وصل الطلب وربما لا) ⇒ تُنقل إلى submit_uncertain لمراجعة الأدمن،
        وممنوع إعادة إرسالها تلقائياً.

        المدخلات:
            only_expired : False عند الإقلاع (لا عامل حيّ بعد، فكل `submitting` عالق).
                           True أثناء التشغيل: لا يُمسّ إلا ما انتهى قفله (لا ينتزع طلباً
                           ما زال عامل حيّ يرسله).

        المخرجات: قائمة معرفات الطلبات التي نُقلت إلى submit_uncertain.
        """
        if only_expired:
            rows = await tx.fetchall(
                """
                SELECT id FROM orders
                 WHERE status = 'submitting' AND provider_order_id IS NULL
                   AND (locked_until IS NULL OR locked_until < ?)
                """,
                (utc_now_iso(),),
            )
        else:
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
                    reason="استرداد بعد انقطاع الإرسال" if only_expired else "استرداد بعد إعادة تشغيل البوت",
                )
        return ids
