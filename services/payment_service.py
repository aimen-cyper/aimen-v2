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
    clean_multiline,
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

        # فحص مبكر للرد السريع؛ الفحص الحاكم يُعاد داخل المعاملة أدناه (يمنع سباق التسجيلين المتزامنين)
        await self._ensure_reference_unused(reference)

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
            await self._ensure_reference_unused(reference)
            await self._check_pending_limit(user)
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

    async def _ensure_reference_unused(self, reference: str | None) -> None:
        """
        التأكد أن رقم الحوالة لم يُستخدم في طلب شحن معلّق أو معتمد (R5: إثبات مكرر).

        تُستدعى مرتين عمداً: قبل المعاملة (ردّ سريع) وداخلها (الفحص الحاكم تحت قفل الكتابة).

        الاستثناءات: DuplicateOperationError إن وُجد طلب سابق بنفس الرقم.
        """
        if not reference:
            return
        duplicate = await self.repos.payments.find_duplicate_reference(reference)
        if duplicate is not None:
            raise DuplicateOperationError(
                f"رقم الحوالة {reference} مستخدم في الطلب {duplicate.id}",
                user_message=(
                    "⚠️ رقم العملية هذا مُستخدم في طلب شحن سابق. "
                    "تواصل مع الدعم إن كان هناك خطأ."
                ),
            )

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
        # عينان على كل عملية مالية: لا يعتمد الأدمن شحنته هو
        await self.auth.ensure_not_self_dealing(
            actor, payment.user_id, what="اعتماد طلب شحن يخصّك", context=f"payment:{payment_id}"
        )

        # الافتراضي هو الصافي بعد رسوم الطريقة المحفوظة على الطلب نفسه
        default_units = payment.net_units
        amount_units = int(credited_units) if credited_units is not None else default_units
        if amount_units <= 0:
            raise ValidationError(
                f"مبلغ اعتماد غير صالح: {amount_units}",
                user_message="❌ المبلغ المعتمد يجب أن يكون أكبر من صفر.",
            )
        if amount_units > payment.amount_units:
            # لا يُضاف للمحفظة أكثر مما حوّله العميل فعلاً (الرسوم تُخصم ولا تُضاف)
            await self.audit.log_security_event(
                event="over_credit_blocked",
                user_id=actor.id,
                target_type="payment",
                target_id=payment_id,
                details={"requested_units": amount_units, "paid_units": payment.amount_units},
            )
            raise ValidationError(
                f"مبلغ الاعتماد {amount_units} يتجاوز المحوَّل {payment.amount_units}",
                user_message="❌ لا يمكن اعتماد مبلغ أكبر من المبلغ الذي حوّله العميل.",
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
                # التعليمات اختيارية (قد تُترك فارغة لطريقة بسيطة) ⇒ min_length=0
                clean[key] = clean_multiline(
                    value, field="التعليمات", max_length=MAX_METHOD_INSTRUCTIONS, min_length=0
                )
            elif key == "account_details":
                clean[key] = clean_multiline(
                    value, field="بيانات الحساب", max_length=MAX_METHOD_ACCOUNT, min_length=0
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
        # الاتساق بين الحدين عند الإنشاء أيضاً (كان يُفحص عند التعديل فقط فتُنشأ طريقة لا يستطيع أحد الشحن بها)
        self._check_limit_pair(clean_code, values["min_amount_units"], values["max_amount_units"])
        order = (
            int(sort_order)
            if sort_order is not None
            else await self.repos.payment_methods.next_sort_order()
        )

        async with self.db.transaction() as tx:
            # إعادة الفحص داخل المعاملة: الفحص الأول للرد السريع فقط، وهذا الحاكم عند التزامن
            if await tx.fetchval("SELECT 1 FROM payment_methods WHERE code = ?", (clean_code,)):
                raise ValidationError(
                    f"كود طريقة الدفع {clean_code} مستخدم",
                    user_message="❌ يوجد طريقة شحن بنفس الكود.",
                )
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
        before = {key: getattr(method, key, None) for key in values}

        async with self.db.transaction() as tx:
            # إعادة قراءة الطريقة وفحص الحدين داخل المعاملة: تعديلان متزامنان لحدّين مختلفين لا يمرّان معاً
            fresh = await self.repos.payment_methods.get(method_id)
            if fresh is not None:
                self._assert_limits_consistent(fresh, values)
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
        self._check_limit_pair(
            method.code,
            values.get("min_amount_units", method.min_amount_units),
            values.get("max_amount_units", method.max_amount_units),
        )

    @staticmethod
    def _check_limit_pair(code: str, minimum: Any, maximum: Any) -> None:
        """رفض حدّين متعارضين (أدنى > أقصى). `None`/0 تعني «بلا حد»."""
        low = int(minimum or 0)
        if maximum is not None and low and int(maximum) < low:
            raise ValidationError(
                f"حدود متعارضة للطريقة {code}: {low} > {maximum}",
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
