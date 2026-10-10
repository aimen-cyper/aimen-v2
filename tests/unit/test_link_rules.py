"""قواعد الروابط حسب المنصة والنوع (المرحلة 13 — بند 10): روابط صحيحة وخاطئة لكل منصة."""

from __future__ import annotations

import pytest

from core.exceptions import InvalidLinkError
from utils.link_rules import LINK_RULES, check_link_rule, detect, detect_platform, infer_rule, rule_label
from utils.validators import validate_link

VALID = [
    ("instagram_profile", "https://instagram.com/username"),
    ("instagram_profile", "https://www.instagram.com/user.name_1/"),
    ("instagram_profile", "instagram.com/username?igsh=abc"),
    ("instagram_post", "https://www.instagram.com/p/AbCdEf123/"),
    ("instagram_post", "https://instagram.com/reel/AbCdEf123/?igsh=x"),
    ("instagram_post", "https://instagram.com/username/p/AbCdEf123/"),
    ("tiktok_profile", "https://www.tiktok.com/@some.user"),
    ("tiktok_video", "https://www.tiktok.com/@some.user/video/7234567890123456789"),
    ("tiktok_video", "https://vm.tiktok.com/ZMabc123/"),
    ("youtube_channel", "https://youtube.com/@channel"),
    ("youtube_channel", "https://www.youtube.com/channel/UCabcdefghijklmnop"),
    ("youtube_video", "https://www.youtube.com/watch?v=AbCdEfGhIjK&t=5"),
    ("youtube_video", "https://youtu.be/AbCdEfGhIjK"),
    ("youtube_video", "https://youtube.com/shorts/AbCdEfGhIjK"),
    ("telegram_channel", "https://t.me/channelname"),
    ("telegram_channel", "https://t.me/+AbCdEfGh123"),
    ("telegram_post", "https://t.me/channelname/123"),
    ("telegram_post", "https://t.me/c/1234567890/55"),
    ("facebook_page", "https://www.facebook.com/pagename"),
    ("facebook_page", "https://facebook.com/profile.php?id=1000123"),
    ("facebook_post", "https://facebook.com/pagename/posts/123456789"),
    ("facebook_post", "https://fb.watch/abcDEF/"),
    ("x_profile", "https://x.com/username"),
    ("x_profile", "https://twitter.com/user_1"),
    ("x_post", "https://x.com/username/status/1234567890"),
]

INVALID = [
    # منصة مختلفة
    ("instagram_profile", "https://tiktok.com/@username"),
    ("instagram_post", "https://youtube.com/watch?v=AbCdEfGhIjK"),
    ("tiktok_video", "https://instagram.com/p/AbCdEf123/"),
    ("youtube_video", "https://t.me/channelname/12"),
    ("x_post", "https://facebook.com/pagename/posts/123456789"),
    # رابط عام لا يخص منصة
    ("instagram_profile", "https://example.com/username"),
    ("telegram_channel", "https://google.com"),
    # منصة صحيحة ونوع خاطئ
    ("instagram_profile", "https://instagram.com/p/AbCdEf123/"),
    ("instagram_post", "https://instagram.com/username"),
    ("tiktok_profile", "https://tiktok.com/@user/video/123"),
    ("tiktok_video", "https://tiktok.com/@user"),
    ("youtube_channel", "https://youtube.com/watch?v=AbCdEfGhIjK"),
    ("youtube_video", "https://youtube.com/@channel"),
    ("telegram_channel", "https://t.me/channelname/123"),
    ("telegram_post", "https://t.me/channelname"),
    ("x_profile", "https://x.com/user/status/123"),
    ("x_post", "https://x.com/user"),
    # مشوّه
    ("instagram_profile", "https://instagram.com/"),
    ("instagram_profile", "https://instagram.com/explore/"),
    ("instagram_post", "https://instagram.com/p/"),
    ("youtube_video", "https://youtube.com/watch"),
    ("telegram_channel", "https://t.me/"),
    ("x_post", "https://x.com/user/status/notanumber"),
]


@pytest.mark.parametrize(("rule", "link"), VALID)
def test_valid_links_pass(rule: str, link: str) -> None:
    """الروابط الصحيحة تُقبل لقاعدتها."""
    check_link_rule(link, rule)
    assert validate_link(link, rule=rule)


@pytest.mark.parametrize(("rule", "link"), INVALID)
def test_invalid_links_are_rejected_with_example(rule: str, link: str) -> None:
    """الخاطئة تُرفض برسالة عربية فيها المثال الصحيح."""
    with pytest.raises(InvalidLinkError) as exc:
        validate_link(link, rule=rule)
    message = exc.value.user_message
    assert message.startswith("❌")
    assert LINK_RULES[rule].example in message


def test_messages_distinguish_platform_from_kind() -> None:
    """رسالة المنصة المختلفة غير رسالة النوع الخاطئ."""
    with pytest.raises(InvalidLinkError) as other:
        check_link_rule("https://tiktok.com/@a", "instagram_profile")
    assert "تيك توك" in other.value.user_message and "والخدمة خاصة بـانستغرام" in other.value.user_message
    with pytest.raises(InvalidLinkError) as kind:
        check_link_rule("https://instagram.com/p/AbC123/", "instagram_profile")
    assert "منشور/فيديو" in kind.value.user_message and "حساب/قناة" in kind.value.user_message


def test_no_rule_or_unknown_rule_changes_nothing() -> None:
    """بلا قاعدة (أو مفتاح غير معروف) يبقى التحقق العام فقط."""
    assert validate_link("https://example.com/x") == "https://example.com/x"
    assert validate_link("https://example.com/x", rule="nope") == "https://example.com/x"
    assert rule_label(None).startswith("بلا قيد")
    assert rule_label("instagram_profile") == "حساب انستغرام"


def test_general_validation_still_runs_before_rule() -> None:
    """الفراغات/البروتوكول يُرفضان قبل القاعدة كما كان."""
    with pytest.raises(InvalidLinkError):
        validate_link("https://instagram.com/user name", rule="instagram_profile")
    with pytest.raises(InvalidLinkError):
        validate_link("ftp://instagram.com/user", rule="instagram_profile")


def test_detect() -> None:
    """تصنيف الرابط (منصة، نوع)."""
    assert detect("https://instagram.com/p/x1/") == ("instagram", "post")
    assert detect("https://m.facebook.com/pagename") == ("facebook", "profile")
    assert detect("https://example.com") is None
    assert detect_platform("https://evil-instagram.com/user") is None
    assert detect_platform("https://notinstagram.com/user") is None


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("متابعين انستغرام عرب", "instagram_profile"),
        ("Instagram Followers [Real]", "instagram_profile"),
        ("لايكات انستغرام", "instagram_post"),
        ("TikTok Views Fast", "tiktok_video"),
        ("مشاهدات يوتيوب", "youtube_video"),
        ("أعضاء قناة تيليجرام", "telegram_channel"),
        ("خدمة عامة", None),
        ("متابعين انستغرام وتيك توك", None),
        ("Instagram Followers + Likes", None),
    ],
)
def test_infer_rule_is_conservative(name: str, expected: str | None) -> None:
    """الاستنتاج يحدد القاعدة فقط عند وضوح المنصة والنوع."""
    assert infer_rule(name) == expected
