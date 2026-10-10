"""
خدمة سجل التدقيق: تسجيل كل عملية إدارية حسّاسة بمن نفّذها وما تغيّر.

قاعدة المشروع: أي إجراء إداري يمسّ المال أو الصلاحيات أو بيانات المستخدمين
يجب أن يترك أثراً في هذا السجل — والسجل لا يُحذف.
"""

from __future__ import annotations

from typing import Any

from core.exceptions import ValidationError
from database.database import Database, Tx
from database.models import AuditLog
from database.repositories import Repositories
from utils.logging_setup import get_logger
from utils.security import sanitize

logger = get_logger(__name__)

#: فئات فلتر سجل التدقيق: مفتاح الفئة ← بادئات أسماء الإجراءات الفعلية المسجَّلة في النظام.
#: (الفئة `all` بلا بادئات = كل السجلات). لا تداخل بين الفئات عمداً حتى يطابق العدّ ما يُعرض.
AUDIT_CATEGORIES: dict[str, tuple[str, ...]] = {
    "all": (),
    "users": ("users.register", "users.role", "users.ban", "users.unban", "users.note"),
    "money": ("payments.", "users.balance."),
    "orders": ("orders.",),
    "catalog": ("services.", "providers."),
    "tickets": ("tickets.",),
    "settings": ("settings.", "notifications.", "broadcast."),
    "security": ("security.", "admins.", "admin."),
    "system": ("backup.", "stats.", "system."),
}


class AuditService:
    """كتابة وقراءة سجل التدقيق."""

    def __init__(self, db: Database, repos: Repositories) -> None:
        """تهيئة الخدمة."""
        self.db = db
        self.repos = repos

    # ------------------------------- الكتابة ------------------------------ #

    async def log(
        self,
        tx: Tx,
        *,
        action: str,
        admin_id: int | None = None,
        target_type: str | None = None,
        target_id: str | int | None = None,
        before: Any = None,
        after: Any = None,
        details: Any = None,
        source: str = "telegram",
    ) -> int | None:
        """
        تسجيل عملية داخل معاملة قائمة (حتى يسقط السجل مع العملية إن فشلت).

        ملاحظة أمنية: كل النصوص تمر على أداة تنقية الأسرار قبل التخزين.
        """
        return await self.repos.audit.log(
            tx,
            action=action,
            admin_id=admin_id,
            target_type=target_type,
            target_id=target_id,
            before=_clean(before),
            after=_clean(after),
            details=_clean(details),
            source=source,
        )

    async def log_standalone(
        self,
        *,
        action: str,
        admin_id: int | None = None,
        target_type: str | None = None,
        target_id: str | int | None = None,
        details: Any = None,
        source: str = "system",
    ) -> int | None:
        """تسجيل عملية بمعاملة مستقلة (عندما لا توجد معاملة جارية)."""
        async with self.db.transaction() as tx:
            return await self.log(
                tx,
                action=action,
                admin_id=admin_id,
                target_type=target_type,
                target_id=target_id,
                details=details,
                source=source,
            )

    async def log_permission_denied(
        self, *, user_id: int, permission: str, context: str = ""
    ) -> None:
        """
        تسجيل محاولة وصول مرفوضة.

        تُسجَّل دائماً لأنها مؤشر أمني مهم (محاولة استخدام زر إداري بلا صلاحية).
        """
        async with self.db.transaction() as tx:
            await self.repos.audit.log(
                tx,
                action="security.permission_denied",
                admin_id=user_id,
                target_type="permission",
                target_id=permission,
                details={"context": sanitize(context)},
                source="security",
            )
        logger.warning("رُفض وصول المستخدم %s إلى الصلاحية %s (%s)", user_id, permission, context)

    async def log_security_event(
        self,
        *,
        event: str,
        user_id: int | None,
        target_type: str | None = None,
        target_id: str | int | None = None,
        details: Any = None,
    ) -> None:
        """
        تسجيل حدث أمني مستقل (معاملة خاصة به) — يبقى حتى لو فشلت العملية الأصلية.

        المدخلات:
            event   : اسم الحدث بلا بادئة (مثل `hierarchy_denied`) فيُخزَّن `security.<event>`.
            user_id : المستخدم المنفِّذ (أو None لحدث نظام).

        لماذا معاملة منفصلة؟ الأحداث الأمنية تُسجَّل غالباً لحظة رفض العملية،
        والعملية المرفوضة تتراجع — ولو شاركتها المعاملة لضاع الأثر مع التراجع.
        """
        async with self.db.transaction() as tx:
            await self.repos.audit.log(
                tx,
                action=f"security.{event}",
                admin_id=user_id,
                target_type=target_type,
                target_id=target_id,
                details=_clean(details),
                source="security",
            )
        logger.warning("حدث أمني %s: المستخدم %s ← %s:%s %s", event, user_id, target_type, target_id, details)

    # ------------------------------- القراءة ------------------------------ #

    async def recent(self, *, limit: int = 20, offset: int = 0) -> list[AuditLog]:
        """أحدث عمليات التدقيق (لعرضها في اللوحة)."""
        return await self.repos.audit.list_recent(limit=limit, offset=offset)

    async def by_admin(self, admin_id: int, *, limit: int = 20, offset: int = 0) -> list[AuditLog]:
        """سجل عمليات أدمن محدد."""
        return await self.repos.audit.list_by_admin(admin_id, limit=limit, offset=offset)

    async def by_target(self, target_type: str, target_id: str | int, *, limit: int = 20) -> list[AuditLog]:
        """سجل العمليات التي جرت على هدف محدد (مستخدم، طلب، إعداد…)."""
        return await self.repos.audit.list_by_target(target_type, target_id, limit=limit)

    async def count(self) -> int:
        """إجمالي عدد السجلات."""
        return await self.repos.audit.count_all()

    async def recent_errors(self, *, limit: int = 10, offset: int = 0) -> list[dict]:
        """
        آخر الأخطاء المسجَّلة في `error_logs` (شاشة «السجلات ← الأخطاء»).

        وُضعت هنا لأن شاشة السجلات واحدة في لوحة الأدمن: التدقيق والأخطاء معاً،
        وفحص صلاحية `logs.view` يتم في طبقة المعالجات قبل الوصول إليها.
        """
        return await self.repos.error_logs.list_recent(limit=limit, offset=offset)

    # ----------------------- الفلترة والتفاصيل (المرحلة 10) ---------------------- #

    @staticmethod
    def category_prefixes(category: str) -> tuple[str, ...]:
        """بادئات فئة فلتر؛ فئة غير معروفة ترفع `ValidationError` (لا تُحوَّل صامتاً إلى «الكل»)."""
        if category not in AUDIT_CATEGORIES:
            raise ValidationError(f"فئة سجل غير معروفة: {category!r}", user_message="❌ فئة سجل غير معروفة.")
        return AUDIT_CATEGORIES[category]

    async def list_filtered(self, category: str = "all", *, limit: int = 8, offset: int = 0) -> list[AuditLog]:
        """صفحة من سجل التدقيق ضمن فئة (الأحدث أولاً)."""
        return await self.repos.audit.list_by_prefixes(self.category_prefixes(category), limit=limit, offset=offset)

    async def count_filtered(self, category: str = "all") -> int:
        """عدد سجلات التدقيق ضمن فئة (لحساب الصفحات)."""
        return await self.repos.audit.count_by_prefixes(self.category_prefixes(category))

    async def get_entry(self, audit_id: int) -> AuditLog | None:
        """سجل تدقيق واحد بمعرّفه."""
        return await self.repos.audit.get(audit_id)

    async def count_errors(self) -> int:
        """إجمالي الأخطاء المسجلة (لترقيم شاشة الأخطاء بدقة)."""
        return await self.repos.error_logs.count_all()

    async def get_error(self, error_id: int) -> dict | None:
        """خطأ واحد بمعرّفه (لشاشة التفاصيل)."""
        return await self.repos.error_logs.get(error_id)

    async def provider_calls(self, *, only_failed: bool = False, limit: int = 8, offset: int = 0) -> list[dict]:
        """صفحة من سجل استدعاءات المزودين (الأحدث أولاً)."""
        return await self.repos.provider_requests.list_page(only_failed=only_failed, limit=limit, offset=offset)

    async def count_provider_calls(self, *, only_failed: bool = False) -> int:
        """عدد استدعاءات المزودين (أو الفاشلة فقط)."""
        return await self.repos.provider_requests.count_calls(only_failed=only_failed)

    async def get_provider_call(self, request_id: int) -> dict | None:
        """استدعاء مزود واحد بمعرّفه."""
        return await self.repos.provider_requests.get_call(request_id)

    async def errors_since(self, since_iso: str) -> int:
        """عدد الأخطاء منذ وقت محدد (يُعرض كمؤشر في رأس شاشة الأخطاء)."""
        return await self.repos.error_logs.count_since(since_iso)


def _clean(value: Any) -> Any:
    """تنقية القيم النصية من الأسرار قبل حفظها في السجل."""
    if value is None:
        return None
    if isinstance(value, str):
        return sanitize(value)
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    return value
