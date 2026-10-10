"""
حماية الاتصالات الخارجية: منع SSRF وتسريب مفاتيح المزودين (المرحلة 9).

المشكلة:
    رابط API للمزود يُدخله أدمن، والبوت يرسل إليه مفتاح المزود مع كل طلب.
    رابط خبيث أو خاطئ يعني أحد ثلاثة أخطار:
        1. **SSRF**: توجيه البوت إلى عنوان داخلي (127.0.0.1، 169.254.169.254،
           شبكة الخادم الخاصة) لقراءة خدمات لا يجوز الوصول إليها.
        2. **تسريب المفتاح**: رابط `http://` يرسل المفتاح نصاً صريحاً عبر الشبكة.
        3. **بيانات اعتماد داخل الرابط** (`https://user:pass@host`) تظهر في اللوقات.

الحل (طبقتان):
    • عند الحفظ: `validate_public_https_url` — فحص نصي سريع (بروتوكول، منفذ،
      اسم المضيف، عنوان IP حرفي).
    • عند الإرسال: `ensure_public_host` — يحلّ اسم النطاق ويرفض إن أشار إلى أي
      عنوان غير عام (يسدّ حيلة نطاق عام يشير إلى عنوان داخلي).

قيد معروف (موثَّق في تقرير المرحلة): بين فحص DNS وفتح الاتصال فجوة زمنية صغيرة
(DNS rebinding)؛ الحد منها كاملاً يتطلب تثبيت العنوان داخل الناقل، وهو خارج
نطاق هذه المرحلة. الفحص الحالي يسدّ الأخطاء الشائعة والهجمات المباشرة.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from core.exceptions import ProviderPermanentError, ValidationError

#: لواحق أسماء المضيفين المحلية/الداخلية المرفوضة دائماً
BLOCKED_HOST_SUFFIXES: tuple[str, ...] = (
    ".local", ".localhost", ".internal", ".lan", ".home", ".corp", ".intranet", ".private",
)

#: أسماء مضيفين محجوزة مرفوضة بالنص
BLOCKED_HOSTNAMES: frozenset[str] = frozenset({"localhost", "ip6-localhost", "metadata.google.internal"})

#: المنافذ المسموحة لواجهات المزودين (غير ذلك يُرفض: لا فحص منافذ داخلية)
ALLOWED_PORTS: frozenset[int] = frozenset({443, 8443})

#: مدة بقاء نتيجة فحص DNS الناجحة (ثانية) — لتفادي حلّ الاسم عند كل طلب
DNS_CACHE_TTL_SECONDS: float = 300.0

#: نوع دالة حلّ الأسماء (قابلة للحقن في الاختبارات): اسم المضيف ← قائمة عناوين IP
Resolver = Callable[[str], Awaitable[list[str]]]

_dns_cache: dict[str, float] = {}


def is_public_ip(value: str) -> bool:
    """
    هل العنوان عام قابل للوصول من الإنترنت؟

    يرفض: الحلقة المحلية، الخاص (RFC1918/ULA)، link-local (169.254.x.x)،
    المحجوز، البث المتعدد، وغير المحدد (0.0.0.0). العناوين IPv4 المضمَّنة في
    IPv6 (`::ffff:127.0.0.1`) تُفحص بعد فك التضمين حتى لا تلتف على القاعدة.
    """
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


def _reject(reason: str, *, field: str) -> ValidationError:
    """بناء خطأ تحقق موحّد برسالة عربية تذكر سبب الرفض."""
    return ValidationError(
        f"{field} مرفوض: {reason}",
        user_message=f"❌ {field} غير آمن: {reason}",
    )


def validate_public_https_url(url: str | None, *, field: str = "رابط API") -> str:
    """
    فحص نصي لرابط مزود: https فقط، منفذ مسموح، مضيف عام، بلا بيانات اعتماد.

    المخرجات: الرابط بعد إزالة الفراغات.

    الاستثناءات:
        ValidationError : أي مخالفة مع ذكر سببها بالعربية.
    """
    text = (url or "").strip()
    if not text:
        raise _reject("الرابط فارغ", field=field)
    if len(text) > 300:
        raise _reject("الرابط طويل جداً", field=field)
    if any(ch.isspace() or ord(ch) < 32 for ch in text):
        raise _reject("الرابط يحتوي مسافات أو محارف تحكم", field=field)

    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError as exc:
        raise _reject("صيغة الرابط غير صحيحة", field=field) from exc

    if parts.scheme.lower() != "https":
        raise _reject("يجب أن يبدأ بـ https:// (مفتاح المزود لا يُرسل بلا تشفير)", field=field)
    if parts.username or parts.password:
        raise _reject("لا يجوز وضع اسم مستخدم أو كلمة مرور داخل الرابط", field=field)

    host = (parts.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise _reject("لا يوجد اسم نطاق", field=field)
    if host in BLOCKED_HOSTNAMES or host.endswith(BLOCKED_HOST_SUFFIXES):
        raise _reject("النطاق محلي/داخلي", field=field)

    is_literal_ip = _looks_like_ip(host)
    if is_literal_ip:
        if not is_public_ip(host):
            raise _reject("عنوان IP غير عام (داخلي أو محجوز)", field=field)
    elif "." not in host:
        raise _reject("اسم النطاق غير مكتمل", field=field)

    if port is not None and port not in ALLOWED_PORTS:
        raise _reject(f"المنفذ {port} غير مسموح (المسموح: 443 أو 8443)", field=field)
    return text


def _looks_like_ip(host: str) -> bool:
    """هل النص عنوان IP حرفي (v4 أو v6)؟ — الأرقام المجرّدة (مثل 2130706433) تُعدّ IP أيضاً."""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        # صيغ قديمة يقبلها بعض المحللات: 2130706433 أو 0x7f000001 أو 017700000001
        return _is_numeric_notation(host)
    return True


def _is_numeric_notation(host: str) -> bool:
    """هل النص عدد صحيح بصيغة عشرية/سداسية/ثمانية (عنوان IP مموَّه بصيغة رقمية)؟"""
    try:
        int(host, 0)
    except ValueError:
        return False
    return True


async def _system_resolver(host: str) -> list[str]:
    """حلّ اسم المضيف عبر نظام التشغيل دون حجب حلقة الأحداث."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


async def ensure_public_host(url: str, *, resolver: Resolver | None = None) -> None:
    """
    التأكد وقت الإرسال أن اسم مضيف الرابط يشير إلى عناوين عامة فقط.

    المدخلات:
        url      : رابط المزود (سبق تحقق صيغته عند الحفظ).
        resolver : دالة حلّ بديلة (للاختبارات).

    الاستثناءات:
        ProviderPermanentError : النطاق لا يُحلّ، أو أحد عناوينه غير عام.
                                 (دائم لأن إعادة المحاولة لن تغيّر الحكم الأمني.)
    """
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    if not host:
        raise ProviderPermanentError("رابط المزود بلا اسم مضيف")

    now = time.monotonic()
    cached_until = _dns_cache.get(host, 0.0)
    if cached_until > now:
        return

    if _looks_like_ip(host):
        addresses = [host]
    else:
        try:
            addresses = await (resolver or _system_resolver)(host)
        except OSError as exc:
            raise ProviderPermanentError(f"تعذّر حلّ نطاق المزود {host}: {type(exc).__name__}") from exc

    if not addresses:
        raise ProviderPermanentError(f"النطاق {host} لا يشير إلى أي عنوان")
    for address in addresses:
        if not is_public_ip(address):
            raise ProviderPermanentError(
                f"النطاق {host} يشير إلى عنوان غير عام ({address}) — تم رفض الاتصال حمايةً من SSRF"
            )
    _dns_cache[host] = now + DNS_CACHE_TTL_SECONDS


def clear_dns_cache() -> None:
    """تفريغ ذاكرة نتائج DNS (للاختبارات وعند تغيير رابط مزود)."""
    _dns_cache.clear()
