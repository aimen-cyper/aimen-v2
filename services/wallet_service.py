"""
خدمة المحفظة — **الجهة الوحيدة في النظام التي تعدّل رصيد المستخدم**.

قواعد غير قابلة للكسر:
    1. لا تعديل للرصيد خارج هذه الخدمة (المستودعات تُستدعى من هنا فقط).
    2. كل تغيير في الرصيد يرافقه صف في `transactions` داخل **نفس المعاملة** —
       لا خصم بلا حركة، ولا استرجاع بلا حركة.
    3. كل حركة لها `reference` فريد، فحتى لو استُدعيت العملية مرتين لن تُنفَّذ مرتين.
    4. الخصم يستخدم تحديثاً مشروطاً (`balance_units >= amount`) فلا يمكن أن يصبح الرصيد سالباً.
    5. الدوال التي تأخذ `tx` لا تفتح معاملة بنفسها — المتصل يضمن الذرّية مع بقية العملية
       (مثلاً: إنشاء الطلب + الخصم + الإشعار في معاملة واحدة).
"""

from __future__ import annotations

from dataclasses import dataclass

from core.constants import (
    REF_MANUAL,
    REF_ORDER_DEBIT,
    REF_ORDER_PARTIAL_REFUND,
    REF_ORDER_REFUND,
    REF_PAYMENT_DEPOSIT,
)
from core.permissions import Permission
from core.enums import TransactionType
from core.exceptions import (
    DuplicateOperationError,
    InsufficientBalanceError,
    InvalidAmountError,
    WalletError,
)
from database.database import Database, Tx
from database.models import Transaction, User
from database.repositories import Repositories
from services.auth_service import AuthService
from services.settings_service import SettingsService
from utils.datetime_utils import day_bounds_utc
from utils.logging_setup import get_logger
from utils.security import new_token

logger = get_logger(__name__)


class _AdjustCapExceeded(Exception):
    """إشارة داخلية: تجاوز سقف التسوية اليدوية (تُحوَّل إلى InvalidAmountError خارج المعاملة)."""

    def __init__(self, event: str, message: str, details: dict) -> None:
        """حفظ اسم الحدث الأمني ورسالة المستخدم وتفاصيل التجاوز."""
        super().__init__(event)
        self.event = event
        self.user_message = message
        self.details = details


@dataclass(frozen=True, slots=True)
class LedgerCheck:
    """نتيجة مطابقة الرصيد المخزَّن مع مجموع دفتر الحركات."""

    user_id: int
    stored_units: int
    ledger_units: int

    @property
    def is_balanced(self) -> bool:
        """هل الرصيد مطابق للدفتر؟"""
        return self.stored_units == self.ledger_units

    @property
    def difference_units(self) -> int:
        """الفرق بين المخزَّن والدفتر (صفر يعني سلامة محاسبية)."""
        return self.stored_units - self.ledger_units


class WalletService:
    """كل عمليات المال: إيداع، خصم، استرجاع، تسويات يدوية."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        *,
        settings: SettingsService | None = None,
        auth: AuthService | None = None,
    ) -> None:
        """
        تهيئة الخدمة.

        المدخلات الاختيارية (تُمرَّر دائماً في `build_services`):
            settings : لقراءة سقوف التسويات اليدوية.
            auth     : لحاجز «الإجراء الذاتي» وتسجيل الأحداث الأمنية.
        غيابهما يعطّل حواجز الأمان فقط (مفيد لاختبارات وحدة المحفظة المعزولة).
        """
        self.db = db
        self.repos = repos
        self.settings = settings
        self.auth = auth

    # ------------------------------- القراءة ------------------------------ #

    async def balance_units(self, user_id: int) -> int:
        """الرصيد الحالي بوحدات المال الصحيحة."""
        return await self.repos.users.get_balance_units(user_id)

    async def history(self, user_id: int, *, limit: int = 10, offset: int = 0) -> list[Transaction]:
        """آخر حركات المستخدم المالية."""
        return await self.repos.transactions.list_by_user(user_id, limit=limit, offset=offset)

    async def history_count(self, user_id: int) -> int:
        """إجمالي عدد حركات المستخدم (للتصفح بالصفحات)."""
        return await self.repos.transactions.count_by_user(user_id)

    async def order_transactions(self, order_id: int) -> list[Transaction]:
        """كل الحركات المالية المرتبطة بطلب (خصم + استرجاعات)."""
        return await self.repos.transactions.list_by_order(order_id)

    async def verify_ledger(self, user_id: int) -> LedgerCheck:
        """
        مطابقة محاسبية: هل رصيد المستخدم = مجموع حركاته؟

        تُستخدم في الاختبارات وفي تقرير الأدمن لاكتشاف أي خلل مبكراً.
        """
        stored = await self.repos.users.get_balance_units(user_id)
        ledger = await self.repos.transactions.user_balance_from_ledger(user_id)
        check = LedgerCheck(user_id=user_id, stored_units=stored, ledger_units=ledger)
        if not check.is_balanced:
            logger.error(
                "اختلال محاسبي للمستخدم %s: الرصيد %s ودفتر الحركات %s",
                user_id, stored, ledger,
            )
        return check

    # ------------------------------ أدوات داخلية -------------------------- #

    @staticmethod
    def _validate_amount(amount_units: int) -> int:
        """
        التأكد أن المبلغ عدد صحيح موجب.

        الاستثناءات:
            InvalidAmountError : مبلغ صفر أو سالب أو ليس عدداً صحيحاً.
        """
        if isinstance(amount_units, bool) or not isinstance(amount_units, int):
            raise InvalidAmountError(f"المبلغ يجب أن يكون عدداً صحيحاً: {amount_units!r}")
        if amount_units <= 0:
            raise InvalidAmountError(f"المبلغ يجب أن يكون أكبر من صفر: {amount_units}")
        return amount_units

    async def _ensure_new_reference(self, reference: str) -> None:
        """
        رفض تكرار عملية بنفس المرجع قبل محاولة الكتابة.

        الحماية النهائية هي قيد UNIQUE في قاعدة البيانات، وهذا الفحص لإعطاء رسالة أوضح.
        """
        if await self.repos.transactions.exists_reference(reference):
            raise DuplicateOperationError(f"عملية مكررة بالمرجع {reference}")

    # -------------------------------- الخصم ------------------------------- #

    async def charge_for_order(
        self, tx: Tx, *, user_id: int, order_id: int, amount_units: int, description: str = ""
    ) -> Transaction:
        """
        خصم قيمة طلب من رصيد المستخدم وتسجيل الحركة — داخل معاملة المتصل.

        المخرجات: الحركة المالية المُنشأة.

        الاستثناءات:
            InsufficientBalanceError : الرصيد لا يكفي (لم يُخصم شيء).
            DuplicateOperationError  : سبق خصم هذا الطلب.
        """
        self._validate_amount(amount_units)
        reference = REF_ORDER_DEBIT.format(order_id=order_id)
        await self._ensure_new_reference(reference)

        before = await self.repos.users.get_balance_units(user_id)
        debited = await self.repos.users.try_debit(tx, user_id, amount_units)
        if not debited:
            raise InsufficientBalanceError(
                f"رصيد المستخدم {user_id} ({before}) لا يكفي لخصم {amount_units}"
            )
        after = before - amount_units

        transaction = await self.repos.transactions.insert(
            tx,
            user_id=user_id,
            type=TransactionType.ORDER,
            amount_units=amount_units,
            balance_before_units=before,
            balance_after_units=after,
            order_id=order_id,
            reference=reference,
            description=description or f"خصم قيمة الطلب #{order_id}",
        )
        logger.info("خصم %s وحدة من المستخدم %s للطلب %s", amount_units, user_id, order_id)
        return transaction

    # ------------------------------ الاسترجاع ----------------------------- #

    async def refund_order(
        self,
        tx: Tx,
        *,
        user_id: int,
        order_id: int,
        amount_units: int,
        partial: bool = False,
        description: str = "",
    ) -> Transaction | None:
        """
        استرجاع مبلغ طلب (كامل أو جزئي) مع تسجيل الحركة وتحديث مبلغ الاسترجاع على الطلب.

        المخرجات: الحركة المالية، أو None إذا كان الاسترجاع قد نُفِّذ مسبقاً
                  (لا نرفع خطأ لأن إعادة المحاولة سلوك طبيعي في المهام الدورية).

        الاستثناءات:
            InvalidAmountError : مبلغ غير صالح.
            WalletError        : مبلغ الاسترجاع يتجاوز تكلفة الطلب.
        """
        self._validate_amount(amount_units)
        reference = (
            REF_ORDER_PARTIAL_REFUND.format(order_id=order_id)
            if partial
            else REF_ORDER_REFUND.format(order_id=order_id)
        )
        if await self.repos.transactions.exists_reference(reference):
            logger.info("تجاهل استرجاع مكرر للطلب %s (المرجع %s موجود)", order_id, reference)
            return None

        # تسجيل مبلغ الاسترجاع على الطلب أولاً: التحديث مشروط بعدم تجاوز التكلفة
        recorded = await self.repos.orders.add_refund_amount(tx, order_id, amount_units)
        if not recorded:
            raise WalletError(
                f"مبلغ الاسترجاع {amount_units} يتجاوز تكلفة الطلب #{order_id} أو الطلب غير موجود"
            )

        before = await self.repos.users.get_balance_units(user_id)
        credited = await self.repos.users.refund_spent(tx, user_id, amount_units)
        if not credited:
            raise WalletError(f"تعذر إعادة المبلغ لرصيد المستخدم {user_id}")
        after = before + amount_units

        transaction = await self.repos.transactions.insert(
            tx,
            user_id=user_id,
            type=TransactionType.PARTIAL_REFUND if partial else TransactionType.REFUND,
            amount_units=amount_units,
            balance_before_units=before,
            balance_after_units=after,
            order_id=order_id,
            reference=reference,
            description=description or (
                f"استرجاع جزئي للطلب #{order_id}" if partial else f"استرجاع كامل للطلب #{order_id}"
            ),
        )
        logger.info(
            "استرجاع %s وحدة للمستخدم %s (طلب %s، جزئي=%s)", amount_units, user_id, order_id, partial
        )
        return transaction

    # ------------------------------- الإيداع ------------------------------ #

    async def credit_from_payment(
        self, tx: Tx, *, user_id: int, payment_id: int, amount_units: int, actor_id: int | None = None
    ) -> Transaction:
        """
        إضافة رصيد بعد اعتماد طلب شحن — داخل نفس معاملة اعتماد الدفعة.

        الاستثناءات:
            DuplicateOperationError : سبق إيداع هذه الدفعة (نفس المرجع).
        """
        self._validate_amount(amount_units)
        reference = REF_PAYMENT_DEPOSIT.format(payment_id=payment_id)
        await self._ensure_new_reference(reference)

        before = await self.repos.users.get_balance_units(user_id)
        credited = await self.repos.users.credit(tx, user_id, amount_units, count_as_deposit=True)
        if not credited:
            raise WalletError(f"تعذر إضافة الرصيد للمستخدم {user_id}")
        after = before + amount_units

        transaction = await self.repos.transactions.insert(
            tx,
            user_id=user_id,
            type=TransactionType.DEPOSIT,
            amount_units=amount_units,
            balance_before_units=before,
            balance_after_units=after,
            payment_id=payment_id,
            reference=reference,
            description=f"شحن رصيد عبر طلب الدفع #{payment_id}",
            actor_id=actor_id,
        )
        logger.info("إيداع %s وحدة للمستخدم %s من الدفعة %s", amount_units, user_id, payment_id)
        return transaction

    # --------------------------- التسويات اليدوية -------------------------- #

    async def manual_credit(
        self, tx: Tx, *, user_id: int, amount_units: int, admin_id: int, reason: str, token: str | None = None
    ) -> Transaction:
        """
        إضافة رصيد يدوية من الإدارة (مع مرجع فريد يمنع التكرار عند الضغط المزدوج).

        الاستثناءات:
            InvalidAmountError · DuplicateOperationError
        """
        self._validate_amount(amount_units)
        reference = REF_MANUAL.format(kind="credit", admin_id=admin_id, token=token or new_token(8))
        await self._ensure_new_reference(reference)

        before = await self.repos.users.get_balance_units(user_id)
        if not await self.repos.users.credit(tx, user_id, amount_units):
            raise WalletError(f"تعذر إضافة الرصيد للمستخدم {user_id}")
        after = before + amount_units

        return await self.repos.transactions.insert(
            tx,
            user_id=user_id,
            type=TransactionType.MANUAL_CREDIT,
            amount_units=amount_units,
            balance_before_units=before,
            balance_after_units=after,
            reference=reference,
            description=reason,
            actor_id=admin_id,
        )

    async def manual_debit(
        self, tx: Tx, *, user_id: int, amount_units: int, admin_id: int, reason: str, token: str | None = None
    ) -> Transaction:
        """
        خصم رصيد يدوي من الإدارة (لا يسمح بجعل الرصيد سالباً).

        الاستثناءات:
            InsufficientBalanceError · DuplicateOperationError
        """
        self._validate_amount(amount_units)
        reference = REF_MANUAL.format(kind="debit", admin_id=admin_id, token=token or new_token(8))
        await self._ensure_new_reference(reference)

        before = await self.repos.users.get_balance_units(user_id)
        if not await self.repos.users.try_debit(tx, user_id, amount_units):
            raise InsufficientBalanceError(
                f"رصيد المستخدم {user_id} ({before}) لا يكفي لخصم {amount_units}"
            )
        after = before - amount_units

        return await self.repos.transactions.insert(
            tx,
            user_id=user_id,
            type=TransactionType.MANUAL_DEBIT,
            amount_units=amount_units,
            balance_before_units=before,
            balance_after_units=after,
            reference=reference,
            description=reason,
            actor_id=admin_id,
        )

    async def _enforce_adjust_caps(self, tx: Tx, admin: User, amount_units: int) -> None:
        """
        فرض سقف العملية الواحدة والسقف اليومي على تسويات غير الأدمن الأعلى.

        يُستدعى **داخل** معاملة الكتابة (القراءة والإدراج ذرّيان فلا يتجاوز طلبان
        متزامنان السقف). الأدمن الأعلى مستثنى لكن عملياته مُدقَّقة دائماً.
        صفر في أي سقف = بلا سقف.

        الاستثناءات: _AdjustCapExceeded (تُحوَّل لاحقاً خارج المعاملة).
        """
        if self.settings is None or admin.role == "super_admin":
            return
        per_operation = await self.settings.get_money_units("admin_adjust_max_units", 0)
        if per_operation > 0 and amount_units > per_operation:
            raise _AdjustCapExceeded(
                "adjust_cap_exceeded",
                "🚫 المبلغ يتجاوز سقف التسوية اليدوية المسموح لحسابك. اطلب من الأدمن الأعلى تنفيذها.",
                {"amount_units": amount_units, "cap_units": per_operation, "scope": "operation"},
            )
        daily = await self.settings.get_money_units("admin_adjust_daily_max_units", 0)
        if daily > 0:
            start_today, _ = day_bounds_utc(0)
            used = await self.repos.transactions.sum_manual_by_actor(tx, admin.id, start_today)
            if used + amount_units > daily:
                raise _AdjustCapExceeded(
                    "adjust_daily_cap_exceeded",
                    "🚫 تجاوزت السقف اليومي للتسويات اليدوية. اطلب من الأدمن الأعلى أو انتظر الغد.",
                    {"amount_units": amount_units, "used_today_units": used, "cap_units": daily, "scope": "daily"},
                )

    async def adjust_balance(
        self, *, target: User, amount_units: int, admin: User, reason: str, credit: bool, token: str | None = None
    ) -> Transaction:
        """
        واجهة عالية المستوى للوحة الأدمن: تفتح معاملتها بنفسها وتُرجع الحركة.

        حواجز المرحلة 9: لا تسوية على حساب المنفِّذ نفسه، وسقف للعملية الواحدة
        ولليوم لغير الأدمن الأعلى (تُسجَّل محاولات التجاوز كأحداث أمنية).

        الاستثناءات: InvalidAmountError · InsufficientBalanceError · DuplicateOperationError
                     · PermissionDeniedError (إجراء ذاتي)
        """
        self._validate_amount(amount_units)
        if self.auth is not None:
            # دفاع في العمق: الصلاحية تُفرض في الخدمة نفسها لا في المعالج وحده (المرحلة 11)
            await self.auth.require_permission(
                admin,
                Permission.USERS_BALANCE_CREDIT if credit else Permission.USERS_BALANCE_DEBIT,
                context=f"wallet.adjust:user:{target.id}",
            )
            await self.auth.ensure_not_self_dealing(
                admin, target.id, what="تعديل رصيدك", context="wallet.adjust"
            )
        try:
            async with self.db.transaction() as tx:
                await self._enforce_adjust_caps(tx, admin, amount_units)
                if credit:
                    transaction = await self.manual_credit(
                        tx, user_id=target.id, amount_units=amount_units,
                        admin_id=admin.id, reason=reason, token=token,
                    )
                else:
                    transaction = await self.manual_debit(
                        tx, user_id=target.id, amount_units=amount_units,
                        admin_id=admin.id, reason=reason, token=token,
                    )
                await self.repos.audit.log(
                    tx,
                    action="users.balance.credit" if credit else "users.balance.debit",
                    admin_id=admin.id,
                    target_type="user",
                    target_id=target.id,
                    before={"balance_units": transaction.balance_before_units},
                    after={"balance_units": transaction.balance_after_units},
                    details={"reason": reason, "amount_units": amount_units},
                )
        except _AdjustCapExceeded as exc:
            # التسجيل خارج المعاملة الملغاة حتى لا يضيع الأثر مع التراجع
            if self.auth is not None:
                await self.auth.audit.log_security_event(
                    event=exc.event,
                    user_id=admin.id,
                    target_type="user",
                    target_id=target.id,
                    details=exc.details,
                )
            raise InvalidAmountError(
                f"{exc.event}: {exc.details}", user_message=exc.user_message
            ) from exc
        return transaction
