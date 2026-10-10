"""
مُغلِّف موحّد لمعالجات الواجهة: تحويل أخطاء النظام إلى رسائل عربية مفهومة.

لماذا؟
    خدمات المرحلة 2 ترفع استثناءات مُصنّفة ولكل منها `user_message` عربي جاهز
    (رصيد غير كافٍ، كمية خارج الحدود، صلاحية مرفوضة...). بدل تكرار `try/except`
    في كل معالج، نلفّ المعالج مرة واحدة:

        • `SMMBotError`      ⇐ تُعرض رسالتها للمستخدم (خطأ متوقع، يُسجَّل كمعلومة).
        • أي استثناء آخر     ⇐ يُترك ليعالجه المعالج العام في `errors.py`
                               (يُسجَّل كخطأ حقيقي مع كامل التتبع).

ملاحظة مهمة لمحادثات `ConversationHandler`:
    عند الخطأ المتوقع نُعيد `None` فيبقى المستخدم في نفس الخطوة ويستطيع
    إعادة المحاولة فوراً — بدل إسقاط المحادثة كلها وإجباره على البدء من جديد.
"""

from __future__ import annotations

from functools import wraps
from typing import Awaitable, Callable, TypeVar

from telegram import Update
from telegram.ext import ContextTypes

from core.exceptions import SMMBotError
from handlers.common.ui import answer_callback, send
from utils.logging_setup import get_logger

logger = get_logger(__name__)

Handler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[object]]
_T = TypeVar("_T", bound=Handler)


def guarded(func: _T) -> _T:
    """
    لفّ معالج واجهة لعرض أخطاء النظام المتوقعة برسالة عربية بدل تعطّل البوت.

    المخرجات: نفس المعالج مغلَّفاً (يحافظ على قيمة الإرجاع في المسار الناجح).
    """

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تنفيذ المعالج مع تحويل أخطاء النظام المعروفة إلى رسالة عربية للمستخدم."""
        try:
            return await func(update, context)
        except SMMBotError as exc:
            user = update.effective_user
            logger.info(
                "خطأ متوقع في %s للمستخدم %s: %s",
                func.__name__, user.id if user else "?", exc,
            )
            await answer_callback(update)
            await send(update, context, exc.user_message)
            return None

    return wrapper  # type: ignore[return-value]
