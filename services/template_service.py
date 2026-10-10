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
