"""
الأساس المشترك لكل شاشات لوحة التحكم: فحص الصلاحية، بيانات المحادثات، أدوات العرض.

لماذا ملف مستقل؟
    القاعدة الإلزامية في تصميم المرحلة 0 (البند 5): **فحص الصلاحية يتم على
    الـcallback نفسه، لا على القائمة فقط**. إخفاء الزر وحده لا يكفي لأن الزر
    القديم يبقى في محادثة المستخدم بعد سحب صلاحيته. لذلك كل معالج أدمن يُلفّ
    بـ`@admin_required(...)` الذي:

        1. يتحقق من `admin.access` (بوابة اللوحة كلها).
        2. يتحقق من الصلاحية الدقيقة للإجراء.
        3. يترك `AuthService` يسجّل المحاولة المرفوضة في سجل التدقيق تلقائياً.
        4. يرد بتنبيه عربي ويُنهي أي محادثة جارية بدل ترك المستخدم معلّقاً.

ترتيب المزخرفات المعتمد في كل الوحدات:

        @guarded                       ← يلتقط أخطاء النظام المتوقعة (الخارجي)
        @admin_required(Permission.X)  ← يفحص الصلاحية (الداخلي)
        async def screen(update, context): ...
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from core.exceptions import PermissionDeniedError, ValidationError
from core.permissions import Permission
from database.models import User
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import back_panel_kb
from keyboards.callback_data import Callback, unpack
from middlewares.context import require_user, services_of
from services import ServiceContainer
from texts import admin_ar as t
from utils.logging_setup import get_logger
from utils.security import new_token

logger = get_logger(__name__)

Handler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]]
_T = TypeVar("_T", bound=Handler)

#: عدد العناصر في صفحة قوائم لوحة الأدمن
PAGE_SIZE = 6

#: عدد أسطر السجلات في الصفحة (أسطر قصيرة ⇐ عدد أكبر)
LOG_PAGE_SIZE = 8

#: مفتاح واحد لبيانات كل محادثات الأدمن (محادثة واحدة نشطة لكل أدمن في كل وقت)
ADMIN_FLOW_KEY = "admin_flow"


# ============================ فحص الصلاحيات ============================= #


def admin_required(permission: str | None = None) -> Callable[[_T], _T]:
    """
    مزخرف يمنع تنفيذ معالج الأدمن إلا لمن يملك الصلاحية فعلاً.

    المدخلات:
        permission : رمز الصلاحية المطلوبة للإجراء (None ⇐ يكفي دخول اللوحة).

    المخرجات:
        نفس المعالج مغلَّفاً؛ وعند الرفض يرد بتنبيه ويُرجع `ConversationHandler.END`
        (قيمة غير ضارة خارج المحادثات، وتُنهي المحادثة داخلها).
    """

    def decorator(func: _T) -> _T:
        """تغليف المعالج بفحص الصلاحية المطلوبة."""

        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """التحقق من الصلاحية قبل تمرير التحديث إلى الشاشة الفعلية."""
            services = services_of(context)
            user = require_user(context)
            try:
                await services.auth.require_permission(
                    user, Permission.ADMIN_ACCESS, context=func.__name__
                )
                if permission is not None and permission != Permission.ADMIN_ACCESS:
                    await services.auth.require_permission(
                        user, permission, context=func.__name__
                    )
            except PermissionDeniedError as exc:
                logger.warning(
                    "رفض وصول إداري: المستخدم %s ← %s (%s)",
                    user.telegram_id,
                    permission or Permission.ADMIN_ACCESS,
                    func.__name__,
                )
                await answer_callback(update, exc.user_message, alert=True)
                if update.callback_query is None:
                    await send(update, context, exc.user_message, back_panel_kb())
                clear_flow(context)
                return ConversationHandler.END
            return await func(update, context)

        #: تُقرأ في الاختبارات للتأكد أن كل معالج أدمن محميّ بصلاحية صحيحة
        wrapper.admin_permission = permission or Permission.ADMIN_ACCESS  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


async def permissions_of(context: ContextTypes.DEFAULT_TYPE) -> set[str]:
    """
    مجموعة صلاحيات الأدمن الحالي — تُقرأ طازجة من قاعدة البيانات عند كل شاشة.

    السبب: الصلاحيات تُدار من قاعدة البيانات ويمكن سحبها أثناء الجلسة،
    والأزرار يجب أن تختفي فور ذلك.
    """
    services = services_of(context)
    return await services.auth.permissions_of(require_user(context))


def actor(context: ContextTypes.DEFAULT_TYPE) -> User:
    """الأدمن المنفِّذ للإجراء الحالي (كما حمّلته الطبقة الوسيطة)."""
    return require_user(context)


# ============================ بيانات المحادثات ========================== #


def flow(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """قراءة بيانات محادثة الأدمن الجارية (قاموس فارغ إن لم توجد)."""
    if context.user_data is None:
        return {}
    return context.user_data.get(ADMIN_FLOW_KEY) or {}


def start_flow(context: ContextTypes.DEFAULT_TYPE, **data: Any) -> dict:
    """
    بدء محادثة أدمن جديدة ببيانات أولية.

    يُولَّد مع كل محادثة `token` فريد يُمرَّر للعمليات المالية كمفتاح منع تكرار،
    فلو ضُغط زر التأكيد مرتين لا تُنفَّذ العملية مرتين.
    """
    payload = {"token": new_token(10), **data}
    if context.user_data is not None:
        context.user_data[ADMIN_FLOW_KEY] = payload
    return payload


def update_flow(context: ContextTypes.DEFAULT_TYPE, **data: Any) -> dict:
    """تحديث بيانات المحادثة الجارية دون فقدان ما سبق."""
    payload = dict(flow(context))
    payload.update(data)
    if context.user_data is not None:
        context.user_data[ADMIN_FLOW_KEY] = payload
    return payload


def clear_flow(context: ContextTypes.DEFAULT_TYPE) -> None:
    """مسح بيانات المحادثة بعد الانتهاء أو الإلغاء."""
    if context.user_data is not None:
        context.user_data.pop(ADMIN_FLOW_KEY, None)


@guarded
async def cancel_admin_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء أي محادثة أدمن جارية (زر ❌ إلغاء أو الأمر /cancel)."""
    await answer_callback(update)
    clear_flow(context)
    if update.callback_query is not None:
        await render(update, context, t.CANCELLED, back_panel_kb())
    else:
        await send(update, context, t.CANCELLED, back_panel_kb())
    return ConversationHandler.END


# ============================== أدوات العرض ============================= #


def args(update: Update) -> Callback:
    """تفكيك بيانات الزر المضغوط (namespace/action/args)."""
    return unpack(update.callback_query.data if update.callback_query else None)


def paginate(total: int, page: int, page_size: int = PAGE_SIZE) -> tuple[int, int, int]:
    """
    حساب الترقيم الموحّد لأي قائمة إدارية.

    المخرجات: (الصفحة بعد التصحيح، عدد الصفحات، إزاحة SQL).
    """
    total_pages = max(1, -(-max(0, total) // page_size))
    current = min(max(1, page), total_pages)
    return current, total_pages, (current - 1) * page_size


async def symbol_of(context: ContextTypes.DEFAULT_TYPE) -> str:
    """رمز العملة المعتمد في الإعدادات (يُعرض بجانب كل مبلغ)."""
    services: ServiceContainer = services_of(context)
    return await services.settings.money_symbol()


async def load_user_or_fail(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> User:
    """
    تحميل مستخدم بالمعرف الداخلي لعرض بطاقته أو تنفيذ إجراء عليه.

    الاستثناءات:
        ValidationError : الزر يحمل معرفاً لم يعد موجوداً (يُعرض كرسالة عربية).
    """
    services = services_of(context)
    target = await services.users.get(user_id)
    if target is None:
        raise ValidationError(
            f"المستخدم {user_id} غير موجود", user_message="❌ هذا المستخدم لم يعد موجوداً."
        )
    return target
