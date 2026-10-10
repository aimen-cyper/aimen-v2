"""
قواعد التحقق من رابط الطلب حسب المنصة ونوع الهدف (حساب مقابل منشور...).

لماذا؟ رابط خاطئ يعني طلباً مدفوعاً يُرسَل للمزود ثم يفشل أو يُنفَّذ على هدف غير مقصود. لذلك
يُرفض الرابط **قبل** إنشاء الطلب وقبل أي خصم، مع رسالة عربية تقول ما المطلوب بالضبط ومثال صحيح.

المبدأ: كل خدمة تحمل `link_rule` اختيارياً (مفتاح من `LINK_RULES`)؛ بلا قاعدة ⇒ يبقى التحقق
العام فقط (بروتوكول/نطاق/طول) كما كان. تُحدَّد القاعدة تلقائياً عند الاستيراد (`infer_rule`)
ويمكن للأدمن تعديلها من بطاقة الخدمة.

الملف نقيّ: لا قاعدة بيانات ولا شبكة؛ كل الدوال حتمية وقابلة للاختبار.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from core.exceptions import InvalidLinkError

# ========================================================================= #
#                               تعريف القواعد                               #
# ========================================================================= #

#: أنواع الأهداف
KIND_PROFILE = "profile"
KIND_POST = "post"


@dataclass(frozen=True)
class Platform:
    """منصة: نطاقاتها المقبولة واسمها العربي."""

    key: str
    label: str
    hosts: frozenset[str]


@dataclass(frozen=True)
class LinkRule:
    """قاعدة رابط: منصة + نوع هدف + مثال صحيح يُعرض للمستخدم."""

    key: str
    platform: str
    kind: str
    label: str
    example: str


PLATFORMS: dict[str, Platform] = {
    "instagram": Platform("instagram", "انستغرام", frozenset({"instagram.com", "instagr.am"})),
    "tiktok": Platform("tiktok", "تيك توك", frozenset({"tiktok.com", "vm.tiktok.com", "vt.tiktok.com"})),
    "youtube": Platform("youtube", "يوتيوب", frozenset({"youtube.com", "youtu.be"})),
    "telegram": Platform("telegram", "تيليجرام", frozenset({"t.me", "telegram.me"})),
    "facebook": Platform("facebook", "فيسبوك", frozenset({"facebook.com", "fb.com", "fb.watch"})),
    "x": Platform("x", "إكس (تويتر)", frozenset({"x.com", "twitter.com"})),
}

_RULES = (
    LinkRule("instagram_profile", "instagram", KIND_PROFILE, "حساب انستغرام", "https://instagram.com/username"),
    LinkRule("instagram_post", "instagram", KIND_POST, "منشور/ريلز انستغرام", "https://instagram.com/p/AbCdEf123/"),
    LinkRule("tiktok_profile", "tiktok", KIND_PROFILE, "حساب تيك توك", "https://tiktok.com/@username"),
    LinkRule("tiktok_video", "tiktok", KIND_POST, "فيديو تيك توك", "https://tiktok.com/@username/video/1234567890"),
    LinkRule("youtube_channel", "youtube", KIND_PROFILE, "قناة يوتيوب", "https://youtube.com/@channel"),
    LinkRule("youtube_video", "youtube", KIND_POST, "فيديو يوتيوب", "https://youtube.com/watch?v=AbCdEfGhIjK"),
    LinkRule("telegram_channel", "telegram", KIND_PROFILE, "قناة/مجموعة تيليجرام", "https://t.me/channelname"),
    LinkRule("telegram_post", "telegram", KIND_POST, "منشور تيليجرام", "https://t.me/channelname/123"),
    LinkRule("facebook_page", "facebook", KIND_PROFILE, "صفحة/حساب فيسبوك", "https://facebook.com/pagename"),
    LinkRule("facebook_post", "facebook", KIND_POST, "منشور فيسبوك", "https://facebook.com/pagename/posts/1234567890"),
    LinkRule("x_profile", "x", KIND_PROFILE, "حساب إكس", "https://x.com/username"),
    LinkRule("x_post", "x", KIND_POST, "تغريدة إكس", "https://x.com/username/status/1234567890"),
)

#: القواعد بحسب مفتاحها (الترتيب هو ترتيب العرض للأدمن)
LINK_RULES: dict[str, LinkRule] = {rule.key: rule for rule in _RULES}

#: الأجزاء الأولى المحجوزة في روابط انستغرام (ليست أسماء مستخدمين)
_IG_RESERVED = frozenset(
    {"p", "reel", "reels", "tv", "stories", "explore", "accounts", "direct", "about", "legal", "web", "developer", "challenge"}
)
_USER = r"[A-Za-z0-9._]{1,30}"
_FB_RESERVED = frozenset(
    {"watch", "groups", "events", "marketplace", "gaming", "login", "help", "policies", "privacy", "reel", "share", "story.php", "permalink.php", "photo", "photo.php", "video.php", "sharer", "sharer.php", "dialog", "plugins", "tr"}
)


# ========================================================================= #
#                               تحليل الرابط                                #
# ========================================================================= #


@dataclass(frozen=True)
class _Parsed:
    """الرابط بعد التفكيك: نطاق مبسّط (بلا www/m)، المسار، الاستعلام."""

    host: str
    path: str
    query: dict[str, list[str]]


def _parse(link: str) -> _Parsed | None:
    """تفكيك الرابط إلى (نطاق، مسار، استعلام)؛ None إن تعذّر."""
    text = (link or "").strip()
    try:
        parsed = urlparse(text if "://" in text else f"https://{text}")
        host = (parsed.hostname or "").lower()
    except ValueError:
        return None
    for prefix in ("www.", "m.", "mobile.", "web."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    if not host:
        return None
    path = parsed.path or "/"
    return _Parsed(host=host, path=path, query=parse_qs(parsed.query))


def detect_platform(link: str) -> str | None:
    """المنصة التي ينتمي إليها الرابط (من نطاقه) أو None إن لم تكن منصة معروفة."""
    parsed = _parse(link)
    if parsed is None:
        return None
    for key, platform in PLATFORMS.items():
        if parsed.host in platform.hosts or any(parsed.host.endswith("." + h) for h in platform.hosts):
            return key
    return None


def _segments(path: str) -> list[str]:
    """أجزاء المسار غير الفارغة."""
    return [part for part in path.split("/") if part]


# ------------------------------ مطابقات الأنواع ------------------------------ #


def _instagram_kind(p: _Parsed) -> str | None:
    """نوع رابط انستغرام: post (p/reel/tv) أو profile أو None."""
    seg = _segments(p.path)
    if not seg:
        return None
    if seg[0].lower() in {"p", "reel", "reels", "tv"} and len(seg) >= 2:
        return KIND_POST
    if len(seg) >= 3 and seg[1].lower() in {"p", "reel", "tv"} and re.fullmatch(_USER, seg[0]):
        return KIND_POST
    if seg[0].lower() in _IG_RESERVED:
        return None
    if len(seg) == 1 and re.fullmatch(_USER, seg[0]):
        return KIND_PROFILE
    return None


def _tiktok_kind(p: _Parsed) -> str | None:
    """نوع رابط تيك توك: الفيديو `/@user/video/ID` أو الرابط المختصر، والحساب `/@user`."""
    seg = _segments(p.path)
    if p.host in {"vm.tiktok.com", "vt.tiktok.com"}:
        return KIND_POST if len(seg) == 1 else None
    if not seg or not seg[0].startswith("@") or not re.fullmatch(r"@[A-Za-z0-9._]{2,30}", seg[0]):
        if len(seg) == 2 and seg[0] == "t":  # tiktok.com/t/CODE (مختصر)
            return KIND_POST
        return None
    if len(seg) == 1:
        return KIND_PROFILE
    if len(seg) >= 3 and seg[1] in {"video", "photo"} and seg[2].isdigit():
        return KIND_POST
    return None


def _youtube_kind(p: _Parsed) -> str | None:
    """نوع رابط يوتيوب: فيديو (watch/shorts/live/youtu.be) أو قناة (@/channel/c/user)."""
    seg = _segments(p.path)
    if p.host == "youtu.be":
        return KIND_POST if len(seg) == 1 else None
    if not seg:
        return None
    if seg[0] == "watch":
        return KIND_POST if p.query.get("v") and re.fullmatch(r"[\w-]{6,20}", p.query["v"][0]) else None
    if seg[0] in {"shorts", "live", "embed"} and len(seg) == 2:
        return KIND_POST
    if seg[0].startswith("@") and len(seg[0]) > 1 and len(seg) <= 2:
        return KIND_PROFILE
    if seg[0] in {"channel", "c", "user"} and len(seg) >= 2:
        return KIND_PROFILE
    return None


def _telegram_kind(p: _Parsed) -> str | None:
    """نوع رابط تيليجرام: قناة/مجموعة (اسم أو دعوة) أو منشور (اسم/رقم، c/ID/رقم)."""
    seg = _segments(p.path)
    if not seg:
        return None
    first = seg[0]
    if first.startswith("+") and len(first) > 4 and len(seg) == 1:
        return KIND_PROFILE
    if first == "joinchat" and len(seg) == 2:
        return KIND_PROFILE
    if first == "c" and len(seg) == 3 and seg[1].isdigit() and seg[2].isdigit():
        return KIND_POST
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", first):
        return None
    if len(seg) == 1:
        return KIND_PROFILE
    if len(seg) == 2 and seg[1].isdigit():
        return KIND_POST
    return None


def _facebook_kind(p: _Parsed) -> str | None:
    """نوع رابط فيسبوك: منشور/فيديو/مشاركة أو صفحة/حساب (تساهل مقصود لتنوع الروابط)."""
    seg = _segments(p.path)
    if p.host == "fb.watch":
        return KIND_POST if seg else None
    if not seg:
        return None
    first = seg[0].lower()
    if first in {"permalink.php", "story.php", "photo.php", "photo", "video.php", "watch", "reel"}:
        return KIND_POST
    if first == "share" and len(seg) >= 2:
        return KIND_POST
    if first == "profile.php":
        return KIND_PROFILE if p.query.get("id") else None
    if first == "pages" and len(seg) >= 2:
        return KIND_PROFILE
    if first in _FB_RESERVED or first == "groups":
        return None
    if not re.fullmatch(r"[A-Za-z0-9.\-]{3,60}", seg[0]):
        return None
    if len(seg) == 1:
        return KIND_PROFILE
    if len(seg) >= 3 and seg[1].lower() in {"posts", "videos", "photos", "reel"}:
        return KIND_POST
    return None


def _x_kind(p: _Parsed) -> str | None:
    """نوع رابط إكس: تغريدة `/user/status/ID` أو حساب `/user`."""
    seg = _segments(p.path)
    if not seg:
        return None
    if len(seg) >= 3 and seg[1] == "status" and seg[2].isdigit() and re.fullmatch(r"[A-Za-z0-9_]{1,15}", seg[0]):
        return KIND_POST
    if len(seg) == 1 and re.fullmatch(r"[A-Za-z0-9_]{1,15}", seg[0]) and seg[0].lower() not in {"home", "explore", "i", "search", "settings", "login", "share", "intent", "hashtag", "messages", "notifications"}:
        return KIND_PROFILE
    return None


_KIND_DETECTORS = {
    "instagram": _instagram_kind,
    "tiktok": _tiktok_kind,
    "youtube": _youtube_kind,
    "telegram": _telegram_kind,
    "facebook": _facebook_kind,
    "x": _x_kind,
}

_KIND_LABELS = {KIND_PROFILE: "حساب/قناة", KIND_POST: "منشور/فيديو"}


def detect(link: str) -> tuple[str, str | None] | None:
    """
    تصنيف رابط: (المنصة، نوع الهدف أو None إن لم يُعرف النوع)، أو None إن لم تُعرف المنصة.
    """
    platform = detect_platform(link)
    if platform is None:
        return None
    parsed = _parse(link)
    assert parsed is not None
    return platform, _KIND_DETECTORS[platform](parsed)


# ========================================================================= #
#                                 التحقق                                    #
# ========================================================================= #


def rule_of(key: str | None) -> LinkRule | None:
    """القاعدة من مفتاحها؛ None للمفتاح الفارغ أو غير المعروف."""
    return LINK_RULES.get(key or "")


def check_link_rule(link: str, rule_key: str | None) -> None:
    """
    التحقق من أن الرابط يطابق قاعدة الخدمة، وإلا `InvalidLinkError` برسالة عربية دقيقة.

    ثلاث حالات رفض بثلاث رسائل مختلفة كي يعرف العميل ما الخطأ:
        1. منصة مختلفة (رابط تيك توك لخدمة انستغرام).
        2. المنصة صحيحة لكن النوع خاطئ (رابط منشور لخدمة تتطلب حساباً، والعكس).
        3. رابط مشوّه/غير مدعوم (لا يشبه أي رابط للمنصة).

    مفتاح فارغ ⇒ لا قيد إضافي. مفتاح غير معروف (قاعدة تالفة في القاعدة) ⇒ نتجاهله ونسمح بالطلب
    بدل إسقاطه بخطأ إعدادي غامض — التحقق العام قد جرى مسبقاً.
    """
    rule = rule_of(rule_key)
    if rule is None:
        return
    platform = PLATFORMS[rule.platform]
    example = f"\nمثال صحيح: {rule.example}"
    expected = f"{_KIND_LABELS[rule.kind]} {platform.label}"

    found = detect(link)
    if found is None or found[0] != rule.platform:
        other = PLATFORMS[found[0]].label if found else None
        reason = (
            f"❌ هذا رابط {other} والخدمة خاصة بـ{platform.label}."
            if other
            else f"❌ الرابط لا يبدو رابط {platform.label}."
        )
        raise InvalidLinkError(
            f"رابط من منصة مختلفة: المطلوب {rule.platform} والمُدخل {found[0] if found else 'غير معروف'}",
            user_message=f"{reason}\nهذه الخدمة تتطلب رابط {expected}.{example}",
        )

    kind = found[1]
    if kind == rule.kind:
        return
    if kind is None:
        raise InvalidLinkError(
            f"رابط {rule.platform} غير مفهوم (المطلوب {rule.kind})",
            user_message=f"❌ الرابط غير صحيح. هذه الخدمة تتطلب رابط {expected}.{example}",
        )
    given = _KIND_LABELS[kind]
    raise InvalidLinkError(
        f"نوع رابط خاطئ: المطلوب {rule.kind} والمُدخل {kind}",
        user_message=f"❌ هذا رابط {given} والخدمة تتطلب رابط {expected}.{example}",
    )


# ========================================================================= #
#                          استنتاج القاعدة عند الاستيراد                     #
# ========================================================================= #

_PLATFORM_WORDS = {
    "instagram": ("instagram", "insta", "انستغرام", "انستجرام", "انستا", "إنستغرام", "إنستجرام"),
    "tiktok": ("tiktok", "tik tok", "تيك توك", "تيكتوك"),
    "youtube": ("youtube", "يوتيوب"),
    "telegram": ("telegram", "تيليجرام", "تلغرام", "تليجرام", "تلجرام"),
    "facebook": ("facebook", "فيسبوك", "فيس بوك"),
    "x": ("twitter", "تويتر", "إكس", " x "),
}
_PROFILE_WORDS = ("follower", "subscriber", "member", "متابع", "مشترك", "اعضاء", "أعضاء", "عضو", "page like", "لايكات صفحة")
_POST_WORDS = (
    "like", "view", "comment", "share", "save", "impression", "reach", "repost", "retweet", "watch",
    "لايك", "اعجاب", "إعجاب", "مشاهد", "تعليق", "مشاركة", "حفظ", "ريتويت", "وصول", "ظهور",
)


def infer_rule(*texts: str | None) -> str | None:
    """
    استنتاج `link_rule` من اسم الخدمة (وتصنيفها) عند الاستيراد؛ None إن لم يتضح.

    متحفظ عمداً: لا نُرجع قاعدة إلا إذا ظهرت **منصة واحدة فقط** و**نوع واحد واضح** (حساب أو منشور)
    كي لا نمنع طلبات صحيحة بسبب تخمين. وفي الحالة الملتبسة يبقى بلا قاعدة ويضبطها الأدمن يدوياً.
    """
    haystack = " " + " ".join((t or "") for t in texts).lower() + " "
    platforms = [k for k, words in _PLATFORM_WORDS.items() if any(w in haystack for w in words)]
    if len(platforms) != 1:
        return None
    # الأسماء تُفحص أولاً: «likes» منشور حتى لو ورد «followers» في وصف التصنيف
    name = " " + (texts[0] or "").lower() + " "
    is_profile = any(w in name for w in _PROFILE_WORDS)
    is_post = any(w in name for w in _POST_WORDS)
    if is_profile == is_post:
        return None
    platform = platforms[0]
    kind = KIND_PROFILE if is_profile else KIND_POST
    for rule in _RULES:
        if rule.platform == platform and rule.kind == kind:
            return rule.key
    return None


def rule_label(key: str | None) -> str:
    """وصف عربي للقاعدة لبطاقة الأدمن: «حساب انستغرام» أو «بلا قيد»."""
    rule = rule_of(key)
    return rule.label if rule else "بلا قيد (تحقق عام فقط)"
