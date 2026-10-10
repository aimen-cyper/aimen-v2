"""
خدمة الإعدادات: قراءة إعدادات النظام من قاعدة البيانات مع ذاكرة مؤقتة قصيرة.

لماذا ذاكرة مؤقتة؟ لأن كل طلب مستخدم يقرأ عدة إعدادات (الصيانة، الحدود، العملة…)،
وقراءتها من القرص في كل مرة إهدار. المدة قصيرة (ثوانٍ) والتعديل من اللوحة يُبطلها فوراً،
فلا يحدث تأخير في ظهور أي تغيير.
"""

from __future__ import annotations

import time
from decimal import Decimal
from collections.abc import Awaitable, Callable
from typing import Any

from core.money import parse_usd_rate
from core.setting_rules import check_ordered_pairs, normalize_setting_value
from database.database import Database
from database.models import Setting
from database.repositories import Repositories
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: نوع مراقب الإعدادات: دالة غير متزامنة (المفتاح، القيمة الجديدة)
SettingListener = Callable[[str, str], Awaitable[None]]

#: مدة صلاحية الذاكرة المؤقتة بالثواني
CACHE_TTL_SECONDS: float = 20.0


class SettingsService:
    """واجهة واحدة لقراءة وتعديل إعدادات النظام."""

    def __init__(self, db: Database, repos: Repositories, *, ttl_seconds: float = CACHE_TTL_SECONDS) -> None:
        """تهيئة الخدمة بقاعدة البيانات ومستودعاتها ومدة صلاحية الذاكرة المؤقتة."""
        self.db = db
        self.repos = repos
        self._ttl = ttl_seconds
        self._cache: dict[str, str] = {}
        self._expires_at: float = 0.0
        self._listeners: list[SettingListener] = []
        self._warned_usd_rate = False

    # ------------------------------ الداخلية ------------------------------ #

    async def _values(self) -> dict[str, str]:
        """إرجاع كل الإعدادات كقاموس، مع إعادة التحميل عند انتهاء صلاحية الذاكرة."""
        now = time.monotonic()
        if now >= self._expires_at or not self._cache:
            self._cache = await self.repos.settings.as_dict()
            self._expires_at = now + self._ttl
        return self._cache

    def invalidate(self) -> None:
        """إبطال الذاكرة المؤقتة فوراً (بعد أي تعديل على الإعدادات)."""
        self._cache = {}
        self._expires_at = 0.0

    # ------------------------------- القراءة ------------------------------ #

    async def get_str(self, key: str, default: str = "") -> str:
        """قراءة إعداد نصي."""
        values = await self._values()
        raw = values.get(key)
        return raw if raw not in (None, "") else default

    async def get_int(self, key: str, default: int = 0) -> int:
        """قراءة إعداد رقمي (يُرجع الافتراضي إذا كانت القيمة تالفة، مع تسجيل تحذير)."""
        values = await self._values()
        raw = values.get(key)
        if raw is None or raw == "":
            return default
        try:
            return int(str(raw).strip())
        except ValueError:
            logger.warning("قيمة الإعداد %s ليست رقماً صحيحاً: %r — استُخدم الافتراضي", key, raw)
            return default

    async def get_bool(self, key: str, default: bool = False) -> bool:
        """قراءة إعداد منطقي (يقبل 1/true/yes/on)."""
        values = await self._values()
        raw = values.get(key)
        if raw is None or raw == "":
            return default
        return str(raw).strip().lower() in {"1", "true", "yes", "on", "نعم"}

    async def get_money_units(self, key: str, default: int = 0) -> int:
        """قراءة إعداد مالي مخزَّن بوحدات صحيحة."""
        return await self.get_int(key, default)

    async def get_json(self, key: str, default: Any = None) -> Any:
        """قراءة إعداد بصيغة JSON."""
        return await self.repos.settings.get_json(key, default)

    async def currency(self) -> tuple[str, str, int]:
        """
        بيانات العملة المعروضة.

        المخرجات: (رمز العملة النصي، الرمز المختصر للعرض، عدد الخانات العشرية).
        """
        code = await self.get_str("currency_code", "YER")
        symbol = await self.get_str("currency_symbol", code)
        decimals = await self.get_int("display_decimals", 2)
        return code, symbol, decimals

    async def money_symbol(self) -> str:
        """رمز العملة المستخدم في نصوص الإشعارات."""
        _, symbol, _ = await self.currency()
        return symbol

    async def usd_rate(self) -> Decimal | None:
        """
        سعر صرف الدولار للعرض فقط (ريال لكل $1) — لا يدخل في أي حساب مالي أو خصم.

        `None` إن كان الإعداد فارغاً/فاسداً: تُخفى أسطر «$» ويُسجَّل تحذير (لا قيمة احتياطية في الكود).
        """
        rate = parse_usd_rate(await self.get_str("usd_rate", ""))
        if rate is None and not self._warned_usd_rate:
            self._warned_usd_rate = True
            logger.warning("إعداد usd_rate فارغ أو غير صالح: يُخفى مقابل الدولار في العرض")
        return rate

    async def is_maintenance(self) -> bool:
        """هل النظام في وضع الصيانة؟"""
        return await self.get_bool("maintenance_mode", False)

    async def maintenance_message(self) -> str:
        """نص رسالة الصيانة المعروضة للمستخدمين."""
        return await self.get_str(
            "maintenance_message", "🚧 النظام في صيانة مؤقتة. نعتذر عن الإزعاج."
        )

    async def registration_enabled(self) -> bool:
        """هل التسجيل مفتوح للمستخدمين الجدد؟"""
        return await self.get_bool("registration_enabled", True)

    async def all_settings(self) -> list[Setting]:
        """كل الإعدادات بتفاصيلها (لعرضها في لوحة الأدمن)."""
        return await self.repos.settings.all()

    async def group(self, group_code: str) -> list[Setting]:
        """إعدادات مجموعة واحدة (عامة، طلبات، مدفوعات…)."""
        return await self.repos.settings.by_group(group_code)

    async def groups(self) -> list[str]:
        """أسماء مجموعات الإعدادات."""
        return await self.repos.settings.groups()

    # ------------------------------- الكتابة ------------------------------ #

    # ------------------------------ المراقبون ----------------------------- #

    def add_listener(self, listener: SettingListener) -> None:
        """
        تسجيل دالة تُستدعى بعد كل تعديل ناجح (مثلاً لإعادة جدولة المهام فوراً).

        المدخلات: دالة غير متزامنة بتوقيع `async def listener(key: str, value: str)`.
        أخطاء المراقب لا تُسقط عملية الحفظ (القيمة حُفظت فعلاً) بل تُسجَّل في اللوق.
        """
        self._listeners.append(listener)

    async def _notify_listeners(self, key: str, value: str) -> None:
        """إبلاغ المراقبين بالتعديل مع عزل أخطائهم عن عملية الحفظ."""
        for listener in self._listeners:
            try:
                await listener(key, value)
            except Exception:                                    # noqa: BLE001
                logger.exception("فشل مراقب الإعدادات بعد تعديل %s", key)

    # ------------------------------- الكتابة ------------------------------ #

    async def set(self, key: str, value: Any, *, admin_id: int | None = None) -> bool:
        """
        تعديل قيمة إعداد قابل للتعديل، مع التحقق من نوعها ونطاقها وتسجيل العملية.

        الترتيب: وجود المفتاح وقابليته للتعديل ← تطبيع القيمة والتحقق ← فحص الأزواج
        المرتبطة ← حفظ + تدقيق في معاملة واحدة ← إبطال الذاكرة ← إبلاغ المراقبين.

        المخرجات: True عند التعديل، False إذا كان الإعداد غير موجود أو محمياً من التعديل.

        الاستثناءات:
            ValidationError : القيمة لا تناسب نوع المفتاح أو خارج النطاق المسموح.
        """
        setting = await self.repos.settings.get(key)
        if setting is None or not setting.is_editable:
            logger.warning("رُفض تعديل الإعداد %s (غير موجود أو غير قابل للتعديل)", key)
            return False

        clean = normalize_setting_value(key, value, setting.value_type)

        before = setting.value
        async with self.db.transaction() as tx:
            # فحص الأزواج (أدنى ≤ أعلى) داخل المعاملة نفسها بقيم محقونة منها: تعديلان متزامنان لمفتاحين
            # مرتبطين كانا يمرّان كلٌّ على حدة ثم يتركان أدنى > أعلى
            current = {row["key"]: row["value"] for row in await tx.fetchall("SELECT key, value FROM settings")}
            check_ordered_pairs(key, clean, current)
            before = current.get(key, before)
            changed = await self.repos.settings.set(tx, key, clean, updated_by=admin_id)
            if changed:
                await self.repos.audit.log(
                    tx,
                    action="settings.update",
                    admin_id=admin_id,
                    target_type="setting",
                    target_id=key,
                    before={"value": before},
                    after={"value": clean},
                )
        if changed:
            self.invalidate()
            logger.info("تم تعديل الإعداد %s بواسطة الأدمن %s", key, admin_id)
            await self._notify_listeners(key, clean)
        return changed
