"""اختبارات حماية SSRF لروابط المزودين (المرحلة 9)."""

from __future__ import annotations

import pytest

from core.exceptions import ProviderPermanentError, ValidationError
from utils import net_security
from utils.net_security import ensure_public_host, is_public_ip, validate_public_https_url


@pytest.mark.parametrize(
    "url",
    [
        "https://api.provider.com/api/v2",
        "https://provider.example.org:8443/api",
        "https://8.8.8.8/api",
        "  https://api.provider.com/api/v2  ",
    ],
)
def test_valid_public_https_urls_are_accepted(url: str) -> None:
    """الروابط العامة عبر https وعلى المنافذ المسموحة تُقبل (مع قصّ الفراغات)."""
    assert validate_public_https_url(url) == url.strip()


@pytest.mark.parametrize(
    "url",
    [
        "",
        None,
        "http://api.provider.com/api",                 # بلا تشفير
        "ftp://api.provider.com/api",
        "https://localhost/api",
        "https://service.localhost/api",
        "https://127.0.0.1/api",
        "https://10.0.0.5/api",
        "https://192.168.1.10/api",
        "https://169.254.169.254/latest/meta-data",   # بيانات السحابة
        "https://[::1]/api",
        "https://[::ffff:127.0.0.1]/api",             # IPv4 مضمَّن في IPv6
        "https://0.0.0.0/api",
        "https://metadata.google.internal/x",
        "https://intranet/api",                       # اسم بلا نقطة
        "https://user:pass@api.provider.com/api",     # بيانات اعتماد في الرابط
        "https://api.provider.com:8080/api",          # منفذ غير مسموح
        "https://api.provider.com:22/api",
        "https://api.provider.com/a b",
        "https://" + "a" * 320 + ".com",
    ],
)
def test_unsafe_urls_are_rejected(url: str | None) -> None:
    """أي رابط داخلي/غير مشفّر/بمنفذ غريب يُرفض برسالة عربية."""
    with pytest.raises(ValidationError):
        validate_public_https_url(url)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("8.8.8.8", True),
        ("1.1.1.1", True),
        ("127.0.0.1", False),
        ("10.1.2.3", False),
        ("172.16.0.1", False),
        ("192.168.0.1", False),
        ("169.254.1.1", False),
        ("224.0.0.1", False),
        ("::1", False),
        ("fe80::1", False),
        ("fc00::1", False),
        ("::ffff:10.0.0.1", False),
        ("not-an-ip", False),
    ],
)
def test_is_public_ip(value: str, expected: bool) -> None:
    """التصنيف الصحيح للعناوين العامة والخاصة بما فيها IPv6 المضمَّن."""
    assert is_public_ip(value) is expected


@pytest.mark.asyncio
async def test_ensure_public_host_accepts_public_resolution() -> None:
    """مضيف يُحلّ لعنوان عام يمر ويُخزَّن في ذاكرة DNS (حلّ واحد فقط)."""
    calls: list[str] = []

    async def resolver(host: str) -> list[str]:
        calls.append(host)
        return ["93.184.216.34"]

    await ensure_public_host("https://api.provider.com/x", resolver=resolver)
    await ensure_public_host("https://api.provider.com/y", resolver=resolver)
    assert calls == ["api.provider.com"], "لم تُستخدم ذاكرة DNS"


@pytest.mark.asyncio
async def test_ensure_public_host_rejects_private_resolution() -> None:
    """نطاق عام الاسم يشير لعنوان داخلي (هجوم SSRF بالنطاق) يُرفض كخطأ دائم."""

    async def resolver(host: str) -> list[str]:
        return ["93.184.216.34", "10.0.0.7"]        # عنوان واحد خاص يكفي للرفض

    with pytest.raises(ProviderPermanentError):
        await ensure_public_host("https://evil.example.com/x", resolver=resolver)


@pytest.mark.asyncio
async def test_ensure_public_host_failed_resolution_is_permanent_and_not_cached() -> None:
    """فشل الحلّ خطأ دائم، ولا يُخزَّن نجاحاً كاذباً."""

    async def broken(host: str) -> list[str]:
        raise OSError("dns down")

    with pytest.raises(ProviderPermanentError):
        await ensure_public_host("https://api.provider.com/x", resolver=broken)

    async def good(host: str) -> list[str]:
        return ["93.184.216.34"]

    await ensure_public_host("https://api.provider.com/x", resolver=good)   # لا يزال قابلاً للنجاح


@pytest.mark.asyncio
async def test_literal_private_ip_rejected_at_send_time() -> None:
    """عنوان IP حرفي داخلي يُرفض وقت الإرسال أيضاً (دفاع ثانٍ لما خُزّن قبل التحقق)."""
    with pytest.raises(ProviderPermanentError):
        await ensure_public_host("https://192.168.0.9/x")


def test_clear_dns_cache_is_idempotent() -> None:
    """تفريغ الذاكرة آمن بلا استدعاء سابق."""
    net_security.clear_dns_cache()
    net_security.clear_dns_cache()
