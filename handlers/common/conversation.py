"""
مصنع المحادثات الموحّد مع مهلة عدم النشاط (المرحلة 9).

المشكلة:
    محادثة تأكيد مالية (اعتماد شحن، تعديل رصيد، إرسال إذاعة…) تبقى مفتوحة
    للأبد في ذاكرة البوت. لو ترك الأدمن شاشة «تأكيد» ثم عاد بعد يومين وضغط
    الزر القديم لنُفِّذت عملية بناءً على قرار نسيه — وقد تتغير حالة الحساب
    أو صلاحياته خلال ذلك. كذلك كل محادثة معلّقة تحجز ذاكرة بلا نهاية.

الحل:
    كل محادثات المشروع تُبنى عبر `conversation(...)` فتنتهي تلقائياً بعد
    `CONVERSATION_TIMEOUT_SECONDS` من آخر تفاعل: تُمسح بيانات كل المسارات
    ويُعلَم المستخدم برسالة واضحة، فيتحول الزر القديم إلى «زر منتهٍ» عادي
    تتعامل معه المسارات الاحتياطية بدل أن ينفّذ شيئاً.
"""

from __future__ import annotations

import warnings
from typing import Any

from telegram import Update
from telegram.warnings import PTBUserWarning
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from handlers.common.ui import send
from keyboards.user_kb import main_menu_kb
from texts import ar
from utils.logging_setup import get_logger

# تحذير PTB «per_message=False» استشاري: كل محادثاتنا تتتبّع المستخدم/المحادثة عمداً (لا الرسالة الواحدة)،
# وإظهاره عند كل إقلاع يُخفي التحذيرات الحقيقية في اللوق ⇒ نُسكت هذا النص تحديداً لا غير.
warnings.filterwarnings("ignore", message=r".*per_message=False.*CallbackQueryHandler.*", category=PTBUserWarning)

logger = get_logger(__name__)

#: مهلة عدم النشاط قبل إنهاء المحادثة (ثانية) — 15 دقيقة
CONVERSATION_TIMEOUT_SECONDS: int = 15 * 60

#: كل مفاتيح بيانات المسارات في `user_data` (تُمسح كلها عند انتهاء المهلة)
FLOW_DATA_KEYS: tuple[str, ...] = (
    "admin_flow",
    "order_flow",
    "deposit_flow",
    "ticket_flow",
    "ticket_reply_flow",
)


async def on_conversation_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    إنهاء محادثة منتهية المهلة: مسح بياناتها وإبلاغ المستخدم بوضوح.

    المخرجات: `ConversationHandler.END`.
    """
    if context.user_data is not None:
        for key in FLOW_DATA_KEYS:
            context.user_data.pop(key, None)
    user = update.effective_user
    logger.info("انتهت مهلة محادثة المستخدم %s بسبب عدم النشاط", user.id if user else "?")
    await send(update, context, ar.CONVERSATION_TIMED_OUT, main_menu_kb())
    return ConversationHandler.END


def conversation(*, states: dict[Any, list], **kwargs: Any) -> ConversationHandler:
    """
    بناء `ConversationHandler` بمهلة عدم نشاط موحّدة.

    يقبل نفس وسائط `ConversationHandler` (entry_points/fallbacks/name/per_chat…)،
    ويضيف حالة `TIMEOUT` تمسح البيانات وتُبلغ المستخدم. لا يُسمح بتمرير
    `conversation_timeout` يدوياً حتى لا تشذّ محادثة عن السياسة.
    """
    if "conversation_timeout" in kwargs:
        raise ValueError("المهلة موحّدة في CONVERSATION_TIMEOUT_SECONDS ولا تُمرَّر يدوياً")
    merged = dict(states)
    merged[ConversationHandler.TIMEOUT] = [
        CallbackQueryHandler(on_conversation_timeout),
        MessageHandler(filters.ALL, on_conversation_timeout),
    ]
    return ConversationHandler(
        states=merged, conversation_timeout=CONVERSATION_TIMEOUT_SECONDS, **kwargs
    )
