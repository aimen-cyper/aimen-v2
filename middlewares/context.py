"""
الطبقة الوسيطة (Middleware) التي تسبق كل معالج.

تُسجَّل كـ`TypeHandler` في المجموعة `-10`، أي قبل أي معالج آخر، وتؤدي بالترتيب:

    1. تجاهل التحديثات خارج المحادثة الخاصة (البوت خاص بالاستخدام الفردي).
    2. تسجيل المستخدم أو تحديث بياناته (`UserService.get_or_create`).
    3. رفض المحظورين برسالة تشرح السبب.
    4. تطبيق وضع الصيانة على غير الأدمن.
    5. تطبيق حد معدل الاستخدام (عام + حسّاس) والإيقاف المؤقت للمفرطين.
    6. بوابة الاشتراك الإجباري (القنوات الأربع) لغير الفريق الإداري — بعد حد المعدل حتى لا يُغرق
       أحدٌ تيليجرام بنداءات `getChatMember`.
    7. تحديث آخر نشاط (مرة كل دقيقة على الأكثر لتفادي كتابة عند كل ضغطة).

أي رفض يوقف سلسلة المعالجات عبر `ApplicationHandlerStop` فلا يصل التحديث
إلى بقية المعالجات إطلاقاً — وهذا ما يمنع تكرار فحوص الأمان داخل كل معالج.
"""

from __future__ import annotations

import time

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from core.exceptions import MaintenanceModeError, UserBannedError, ValidationError
from database.models import User
from handlers.common.ui import answer_callback, render, send
from keyboards.callback_data import NS_FLOW, NS_SUB, CallbackError, unpack
from keyboards.user_kb import subscription_kb
from middlewares.rate_limit import (
    BUCKET_PRE,
    BUCKET_SENSITIVE,
    SENSITIVE_ADMIN_ACTIONS,
    SENSITIVE_FLOW_ACTIONS,
    AbuseGuard,
    RateLimiter,
)
from services import ServiceContainer
from texts import ar
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: مفاتيح التخزين داخل `context.user_data`
USER_KEY = "db_user"
LAST_TOUCH_KEY = "last_activity_touch"

#: لا نحدّث «آخر نشاط» أكثر من مرة خلال هذه المدة (ثانية)
ACTIVITY_THROTTLE_SECONDS: float = 60.0

#: الأدوار الإدارية: لها حد عام أعلى (تتنقل بين صفحات كثيرة) وحد حسّاس ×3
STAFF_ROLES: frozenset[str] = frozenset({"support", "admin", "super_admin"})

#: مضاعف الحد الحسّاس للفريق الإداري
STAFF_SENSITIVE_MULTIPLIER = 3


def services_of(context: ContextTypes.DEFAULT_TYPE) -> ServiceContainer:
    """
    جلب حاوية الخدمات المحقونة في التطبيق عند الإقلاع.

    الاستثناءات:
        RuntimeError : التطبيق لم يُهيَّأ بالخدمات (خطأ برمجي لا يحدث في التشغيل الصحيح).
    """
    services = context.application.bot_data.get("services")
    if services is None:
        raise RuntimeError("حاوية الخدمات غير محقونة في bot_data — راجع main.py")
    return services


def current_user(context: ContextTypes.DEFAULT_TYPE) -> User | None:
    """المستخدم المحمَّل من قاعدة البيانات لهذا التحديث (None إن لم يُحمَّل بعد)."""
    if context.user_data is None:
        return None
    return context.user_data.get(USER_KEY)


def require_user(context: ContextTypes.DEFAULT_TYPE) -> User:
    """
    المستخدم الحالي مع ضمان وجوده.

    الاستثناءات:
        RuntimeError : استُدعي معالج قبل الطبقة الوسيطة (خطأ تسجيل handlers).
    """
    user = current_user(context)
    if user is None:
        raise RuntimeError("المستخدم غير محمَّل — تأكد من تسجيل الطبقة الوسيطة في المجموعة -10")
    return user


def refresh_user(context: ContextTypes.DEFAULT_TYPE, user: User) -> None:
    """تحديث نسخة المستخدم المخزَّنة بعد أي تغيير (رصيد، دور، حظر)."""
    if context.user_data is not None:
        context.user_data[USER_KEY] = user


async def reload_user(context: ContextTypes.DEFAULT_TYPE) -> User:
    """إعادة قراءة المستخدم من قاعدة البيانات (بعد عملية غيّرت رصيده مثلاً)."""
    services = services_of(context)
    user = require_user(context)
    fresh = await services.users.get(user.id)
    if fresh is not None:
        refresh_user(context, fresh)
        return fresh
    return user


def is_sensitive_update(update: Update) -> bool:
    """
    هل التحديث إجراء حسّاس يخضع للحد الأضيق؟

    الحسّاس: زر «تأكيد» داخل محادثة (إنشاء طلب، إرسال شحن، تأكيد عملية إدارية …)
    أو رسالة تحمل صورة/ملفاً (إثبات الدفع). التصفح والنصوص العادية ليست حسّاسة.
    """
    query = update.callback_query
    if query is not None:
        if not query.data:
            return False
        try:
            callback = unpack(query.data)
        except CallbackError:
            return False
        if callback.namespace == NS_FLOW and callback.action in SENSITIVE_FLOW_ACTIONS:
            return True
        return callback.action in SENSITIVE_ADMIN_ACTIONS.get(callback.namespace, frozenset())
    message = update.effective_message
    return bool(message is not None and (message.photo or message.document))


class UserContextMiddleware:
    """الطبقة الوسيطة الموحّدة لتحميل المستخدم وفرض قواعد الأمان."""

    def __init__(self, limiter: RateLimiter | None = None, guard: AbuseGuard | None = None) -> None:
        """تهيئة الطبقة مع عدّاد حد الاستخدام وحارس الإساءة (يُحقنان في الاختبارات)."""
        self.limiter = limiter or RateLimiter()
        self.guard = guard or AbuseGuard()

    async def __call__(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        تنفيذ الفحوص قبل أي معالج.

        الاستثناءات:
            ApplicationHandlerStop : التحديث مرفوض (حظر/صيانة/حد استخدام/تسجيل مغلق).
        """
        telegram_user = update.effective_user
        chat = update.effective_chat
        if telegram_user is None or telegram_user.is_bot:
            raise ApplicationHandlerStop

        # البوت مصمَّم للمحادثة الخاصة فقط — المجموعات تُرفض برسالة واضحة مرة واحدة
        if chat is not None and chat.type != "private":
            await send(update, context, ar.ERR_NO_PRIVATE)
            raise ApplicationHandlerStop

        # موقوف مؤقتاً بسبب الإفراط: تجاهل صامت قبل أي قراءة من قاعدة البيانات
        if self.guard.is_blocked(telegram_user.id):
            raise ApplicationHandlerStop

        services = services_of(context)

        # فحص معدل مسبق في الذاكرة **قبل** أي قراءة/كتابة في قاعدة البيانات: من يُغرق البوت بتحديثات
        # لا يستطيع إجبار `get_or_create` على الجري لكل تحديث (الدور غير معروف بعد ⇒ الحدّ الأعلى)
        if not await self._pre_check(update, context, services, telegram_user.id):
            raise ApplicationHandlerStop

        try:
            user, created = await services.users.get_or_create(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
            )
        except ValidationError as exc:
            # التسجيل مغلق من الإعدادات ومحاولة إنشاء حساب جديد — إلا الأدمن الأعلى المعتمد من البيئة:
            # لا يجوز أن يُقفل المالك خارج بوته بسبب إغلاق التسجيل
            if not services.auth.is_emergency_super_admin(telegram_user.id):
                await answer_callback(update)
                await send(update, context, exc.user_message)
                raise ApplicationHandlerStop from None
            await services.auth.bootstrap_super_admins((telegram_user.id,))
            user = await services.users.get_by_telegram(telegram_user.id)
            if user is None:
                raise ApplicationHandlerStop from None
            created = False

        # الأدمن الأعلى المعتمد من SUPER_ADMIN_IDS: تصحيح لحظي لدور مفقود أو حظر خاطئ (يُدقَّق)
        user = await services.auth.bootstrap_user(user)

        if context.user_data is not None:
            context.user_data[USER_KEY] = user
            context.user_data["is_new_user"] = created

        # 1) الحظر — يسبق كل شيء
        try:
            await services.auth.ensure_not_banned(user)
        except UserBannedError as exc:
            await answer_callback(update, "🚫")
            await send(update, context, exc.user_message)
            raise ApplicationHandlerStop from None

        # 2) الصيانة — لا تمنع الأدمن
        try:
            await services.auth.ensure_available(user)
        except MaintenanceModeError as exc:
            await answer_callback(update, "🚧")
            await send(update, context, exc.user_message)
            raise ApplicationHandlerStop from None

        # 3) حد معدل الاستخدام: عام لكل الإجراءات + أضيق للحسّاسة، والمتكرر يُوقَف مؤقتاً
        is_staff = user.role in STAFF_ROLES
        if is_staff:
            general_limit = await services.settings.get_int("rate_limit_admin_actions_per_minute", 120)
        else:
            general_limit = await services.settings.get_int("rate_limit_actions_per_minute", 30)
        allowed = self.limiter.hit(telegram_user.id, general_limit)
        if allowed and is_sensitive_update(update):
            sensitive_limit = await services.settings.get_int("rate_limit_sensitive_per_minute", 8)
            if is_staff:
                sensitive_limit *= STAFF_SENSITIVE_MULTIPLIER
            allowed = self.limiter.hit(telegram_user.id, sensitive_limit, bucket=BUCKET_SENSITIVE)
        if not allowed:
            await self._handle_violation(update, context, services, user)
            raise ApplicationHandlerStop

        # 4) الاشتراك الإجباري (الفريق الإداري معفى)
        if not is_staff:
            await self._enforce_subscription(update, context, services, telegram_user.id)

        # 5) تحديث آخر نشاط بتهدئة
        await self._touch_activity(context, services, user)

    async def _enforce_subscription(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, services: ServiceContainer, telegram_id: int
    ) -> None:
        """
        بوابة الاشتراك: غير المشترك فعلياً في كل القنوات المطلوبة يرى شاشة الاشتراك فقط.

        • ضغط «✅ تحقق» يتجاوز الكاش ويعيد الفحص من تيليجرام؛ نجاحه يمرّر التحديث لمعالجه (القائمة الرئيسية).
        • الفشل مغلق: تعذّر التحقق لا يُعدّ اشتراكاً (يُبلَّغ المستخدم بوضوح ويُنبَّه الأدمن مرة يومياً).

        الاستثناءات:
            ApplicationHandlerStop : المستخدم غير مكتمل الاشتراك.
        """
        is_check = False
        if update.callback_query is not None and update.callback_query.data:
            try:
                callback = unpack(update.callback_query.data)
                is_check = callback.namespace == NS_SUB and callback.action == "check"
            except CallbackError:
                is_check = False

        status = await services.subscriptions.check(context.bot, telegram_id, force=is_check)
        if status.ok:
            return

        lines: list[str] = []
        missing_keys = {channel.key for channel in status.missing}
        buttons: list[tuple[str, str | None]] = []
        for channel in status.channels:
            if channel.key in missing_keys:
                lines.append(ar.SUB_LINE_MISSING.format(title=channel.title))
                buttons.append((channel.title, channel.ref.join_url))
            elif channel.key in status.unverifiable:
                lines.append(ar.SUB_LINE_UNKNOWN.format(title=channel.title))
                if channel.ref.join_url:
                    buttons.append((channel.title, channel.ref.join_url))
            else:
                lines.append(ar.SUB_LINE_OK.format(title=channel.title))
        text = ar.SUB_GATE_TITLE + "\n".join(lines)
        if status.unverifiable:
            text += ar.SUB_GATE_UNVERIFIABLE_NOTE

        if is_check:
            if status.missing:
                names = "، ".join(channel.label for channel in status.missing)
                await answer_callback(update, ar.SUB_CHECK_FAILED.format(names=names), alert=True)
            else:
                await answer_callback(update, ar.SUB_CHECK_UNVERIFIED, alert=True)
        else:
            await answer_callback(update)
        await render(update, context, text, subscription_kb(buttons))
        raise ApplicationHandlerStop

    async def _pre_check(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, services: ServiceContainer, telegram_id: int
    ) -> bool:
        """
        فحص حد المعدل قبل قاعدة البيانات بالحد الأعلى بين حدّي العادي والأدمن.

        الدور الحقيقي يُطبَّق بدقة بعد تحميل المستخدم؛ هذا الفحص يقطع السيل فقط. المخالفة هنا تُسجَّل في
        `AbuseGuard` (فيُوقَف المُغرِق بصمت بلا قاعدة بيانات) مع تحذير مُهدَّأ بلا أي قراءة من القاعدة.

        المخرجات: True إن سُمح بالمتابعة.
        """
        user_limit = await services.settings.get_int("rate_limit_actions_per_minute", 30)
        staff_limit = await services.settings.get_int("rate_limit_admin_actions_per_minute", 120)
        if self.limiter.hit(telegram_id, max(user_limit, staff_limit), bucket=BUCKET_PRE):
            return True
        strikes_limit = await services.settings.get_int("rate_limit_strikes_before_block", 5)
        block_minutes = await services.settings.get_int("rate_limit_block_minutes", 5)
        result = self.guard.record_violation(
            telegram_id, strikes_limit=strikes_limit, block_seconds=block_minutes * 60.0
        )
        logger.info("تجاوز المستخدم %s الحد المسبق (مخالفات: %s/%s)", telegram_id, result.strikes, strikes_limit)
        if result.blocked:
            message = ar.ERR_RATE_BLOCKED.format(minutes=block_minutes)
        elif result.warn:
            message = ar.ERR_RATE_LIMITED
        else:
            return False
        await answer_callback(update, message, alert=True)
        if update.callback_query is None:
            await send(update, context, message)
        return False

    async def _handle_violation(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        services: ServiceContainer,
        user: User,
    ) -> None:
        """
        معالجة تجاوز الحد: تسجيل مخالفة، وبدء الإيقاف المؤقت عند التكرار، وتحذير مُهدَّأ.

        التحذير لا يُرسل لكل تحديث (سيضاعف الضغط)، والإيقاف يُسجَّل في سجل التدقيق
        كحدث أمني `security.rate_limit_block`.
        """
        strikes_limit = await services.settings.get_int("rate_limit_strikes_before_block", 5)
        block_minutes = await services.settings.get_int("rate_limit_block_minutes", 5)
        result = self.guard.record_violation(
            user.telegram_id, strikes_limit=strikes_limit, block_seconds=block_minutes * 60.0
        )
        logger.info(
            "تجاوز المستخدم %s حد الاستخدام (مخالفات: %s/%s)", user.telegram_id, result.strikes, strikes_limit
        )

        if result.blocked:
            try:
                await services.audit.log_security_event(
                    event="rate_limit_block",
                    user_id=user.id,
                    target_type="user",
                    target_id=user.id,
                    details={"strikes": result.strikes, "minutes": block_minutes, "role": user.role},
                )
            except Exception:                                    # noqa: BLE001
                logger.exception("تعذّر تسجيل حدث الإيقاف المؤقت للمستخدم %s", user.telegram_id)
            message = ar.ERR_RATE_BLOCKED.format(minutes=block_minutes)
            await answer_callback(update, message, alert=True)
            if update.callback_query is None:
                await send(update, context, message)
            return

        if result.warn:
            await answer_callback(update, ar.ERR_RATE_LIMITED, alert=True)
            if update.callback_query is None:
                await send(update, context, ar.ERR_RATE_LIMITED)

    async def _touch_activity(
        self, context: ContextTypes.DEFAULT_TYPE, services: ServiceContainer, user: User
    ) -> None:
        """تحديث وقت آخر نشاط مرة واحدة كل دقيقة على الأكثر."""
        if context.user_data is None:
            return
        now = time.monotonic()
        last = context.user_data.get(LAST_TOUCH_KEY)
        if last is not None and now - last < ACTIVITY_THROTTLE_SECONDS:
            return
        context.user_data[LAST_TOUCH_KEY] = now
        await services.users.touch_activity(user.id)
