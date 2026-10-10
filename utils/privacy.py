"""
إخفاء البيانات الحساسة قبل نشرها في القنوات (توثيق الطلبات، إشعارات الإدارة).

القناة قد يراها عدد كبير من الناس، لذلك: المعرّف الرقمي يُقنَّع، والرابط يُظهر المنصة فقط بلا الحساب/المنشور.
"""

from __future__ import annotations

from urllib.parse import urlparse

#: الرمز الذي يحل محل الأجزاء المخفية
MASK_CHAR = "•"


def mask_telegram_id(telegram_id: int | str) -> str:
    """إظهار أول رقمين فقط من معرّف تيليجرام: `1712345678` ⇒ `17••••••••`."""
    text = str(telegram_id).strip().lstrip("-")
    if len(text) <= 2:
        return MASK_CHAR * 4
    return text[:2] + MASK_CHAR * (len(text) - 2)


def mask_link(link: str | None) -> str:
    """
    إخفاء مسار الرابط وإبقاء النطاق: `https://instagram.com/user/p/xyz` ⇒ `https://instagram.com/••••`.

    الرابط الذي يتعذر تحليله يُعاد مقنّعاً كلياً (لا نكشف نصاً لا نفهمه).
    """
    text = (link or "").strip()
    if not text:
        return MASK_CHAR * 4
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        return f"https://{MASK_CHAR * 4}"
    has_path = bool((parsed.path or "").strip("/")) or bool(parsed.query)
    return f"https://{host}/{MASK_CHAR * 4}" if has_path else f"https://{host}"


def mask_username(username: str | None) -> str:
    """اسم المستخدم كما هو (معلومة عامة في تيليجرام) أو «—» إن لم يوجد."""
    clean = (username or "").strip().lstrip("@")
    return f"@{clean}" if clean else "—"
