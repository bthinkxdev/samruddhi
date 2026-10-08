"""
Self-hosted image CAPTCHA (scoped session tokens).

Scopes isolate answers across contact / customer login / vendor login / register
so concurrent forms do not overwrite each other.
"""

from __future__ import annotations

import io
import random
import secrets
import time
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, ImageDraw, ImageFont

from django.core.cache import cache

def cache_get_int(key: str) -> int:
    return int(cache.get(key) or 0)

def cache_incr(key: str, ttl_seconds: int) -> int:
    try:
        return int(cache.incr(key))
    except ValueError:
        cache.add(key, 1, ttl_seconds)
        return 1

def cache_delete(key: str) -> None:
    cache.delete(key)

def cache_set(key: str, value, ttl_seconds: int) -> None:
    cache.set(key, value, ttl_seconds)

if TYPE_CHECKING:
    from django.http import HttpRequest

SCOPES = frozenset({'customer_login', 'contact'})

CAPTCHA_LENGTH = 6
MIN_SUBMIT_SECONDS = 3
# Uppercase only; exclude ambiguous glyphs (0/O, 1/I/L).
CAPTCHA_CHARSET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'

MSG_CAPTCHA_INVALID = 'Incorrect CAPTCHA. Please try again.'
MSG_CAPTCHA_REQUIRED = 'Please enter the CAPTCHA code.'
MSG_CAPTCHA_EXPIRED = 'CAPTCHA expired. Please refresh and try again.'
MSG_TOO_FAST = 'Please wait a moment and try again.'
MSG_IP_LOCKED = 'Too many incorrect CAPTCHA attempts. Please try again in an hour.'
MSG_SCOPE_INVALID = 'Invalid CAPTCHA request.'

_FONT_CANDIDATES = (
    'C:/Windows/Fonts/arial.ttf',
    'C:/Windows/Fonts/segoeui.ttf',
    'C:/Windows/Fonts/calibri.ttf',
    'arial.ttf',
    'Arial.ttf',
    'DejaVuSans.ttf',
    'DejaVuSans-Bold.ttf',
    'LiberationSans-Regular.ttf',
    'segoeui.ttf',
    'calibri.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
)


def normalize_scope(scope: str | None) -> str:
    s = (scope or '').strip().lower()
    if s not in SCOPES:
        raise ValidationError(MSG_SCOPE_INVALID)
    return s


def _answer_key(scope: str) -> str:
    return f'image_captcha_{scope}'


def _issued_key(scope: str) -> str:
    return f'image_captcha_issued_at_{scope}'


def _ttl_seconds() -> int:
    return int(getattr(settings, 'IMAGE_CAPTCHA_TTL_SECONDS', getattr(settings, 'CONTACT_CAPTCHA_TTL_SECONDS', 300)))


def _fail_limit() -> int:
    return int(getattr(settings, 'IMAGE_CAPTCHA_FAIL_LIMIT', getattr(settings, 'CONTACT_CAPTCHA_FAIL_LIMIT', 10)))


def _fail_lock_seconds() -> int:
    return int(
        getattr(
            settings,
            'IMAGE_CAPTCHA_FAIL_LOCK_SECONDS',
            getattr(settings, 'CONTACT_CAPTCHA_FAIL_LOCK_SECONDS', 3600),
        )
    )


def _fail_key(scope: str, ip: str) -> str:
    return f'image_captcha_fail_{scope}_{ip}'


def _lock_key(scope: str, ip: str) -> str:
    return f'image_captcha_lock_{scope}_{ip}'


def generate_code(length: int = CAPTCHA_LENGTH) -> str:
    return ''.join(secrets.choice(CAPTCHA_CHARSET) for _ in range(length))


def _normalize_answer(value: str) -> str:
    """Case-sensitive compare; ignore spaces."""
    return ''.join((value or '').split())


def _load_font(size: int) -> ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_png(code: str, *, width: int = 200, height: int = 56) -> bytes:
    """Clear, readable CAPTCHA — light noise, mild rotation, high contrast."""
    image = Image.new('RGB', (width, height), (248, 250, 252))
    draw = ImageDraw.Draw(image)

    for _ in range(28):
        x, y = random.randint(0, width - 1), random.randint(0, height - 1)
        draw.point((x, y), fill=(200, 205, 215))

    for _ in range(2):
        draw.line(
            (
                random.randint(0, width // 4),
                random.randint(8, height - 8),
                random.randint(3 * width // 4, width),
                random.randint(8, height - 8),
            ),
            fill=(190, 196, 210),
            width=1,
        )

    font = _load_font(28)
    char_width = width // max(len(code), 1)
    for i, char in enumerate(code):
        glyph = Image.new('RGBA', (char_width + 8, height), (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(glyph)
        bbox = gdraw.textbbox((0, 0), char, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = max(0, (char_width - tw) // 2)
        ty = max(0, (height - th) // 2 + random.randint(-2, 2))
        gdraw.text((tx, ty), char, font=font, fill=(30, 41, 59, 255))
        rotated = glyph.rotate(random.randint(-10, 10), resample=Image.Resampling.BICUBIC, expand=0)
        image.paste(rotated, (i * char_width, 0), rotated)

    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return buf.getvalue()


def _mark_session_modified(request: HttpRequest) -> None:
    if hasattr(request.session, 'modified'):
        request.session.modified = True


def issue_captcha(request: HttpRequest, scope: str) -> str:
    scope = normalize_scope(scope)
    code = generate_code()
    request.session[_answer_key(scope)] = code
    request.session[_issued_key(scope)] = time.time()
    _mark_session_modified(request)
    return code


def clear_captcha(request: HttpRequest, scope: str) -> None:
    scope = normalize_scope(scope)
    request.session.pop(_answer_key(scope), None)
    request.session.pop(_issued_key(scope), None)
    _mark_session_modified(request)


def is_ip_locked(ip_address: str | None, scope: str) -> bool:
    scope = normalize_scope(scope)
    ip = (ip_address or '').strip()
    if not ip:
        return False
    return cache_get_int(_lock_key(scope, ip)) > 0


def ensure_ip_not_locked(ip_address: str | None, scope: str) -> None:
    if is_ip_locked(ip_address, scope):
        raise ValidationError(MSG_IP_LOCKED)


def record_captcha_failure(ip_address: str | None, scope: str) -> None:
    scope = normalize_scope(scope)
    ip = (ip_address or '').strip()
    if not ip:
        return
    count = cache_incr(_fail_key(scope, ip), _fail_lock_seconds())
    if count >= _fail_limit():
        cache_set(_lock_key(scope, ip), 1, _fail_lock_seconds())
        cache_delete(_fail_key(scope, ip))


def record_captcha_success(ip_address: str | None, scope: str) -> None:
    scope = normalize_scope(scope)
    ip = (ip_address or '').strip()
    if not ip:
        return
    cache_delete(_fail_key(scope, ip))


def _issued_at(request: HttpRequest, scope: str) -> float | None:
    raw = request.session.get(_issued_key(scope))
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _expected_answer(request: HttpRequest, scope: str) -> str:
    value = (request.session.get(_answer_key(scope)) or '').strip()
    return value


def verify_submission_window(request: HttpRequest, scope: str) -> None:
    scope = normalize_scope(scope)
    issued = _issued_at(request, scope)
    if issued is None:
        raise ValidationError(MSG_TOO_FAST)
    elapsed = time.time() - issued
    if elapsed < MIN_SUBMIT_SECONDS:
        raise ValidationError(MSG_TOO_FAST)
    if elapsed > _ttl_seconds():
        raise ValidationError(MSG_CAPTCHA_EXPIRED)


def verify_answer(
    request: HttpRequest,
    submitted: str,
    *,
    scope: str,
    ip_address: str | None = None,
) -> None:
    scope = normalize_scope(scope)
    ensure_ip_not_locked(ip_address, scope)
    expected = _normalize_answer(_expected_answer(request, scope))
    given = _normalize_answer(submitted)

    try:
        verify_submission_window(request, scope)
    except ValidationError:
        clear_captcha(request, scope)
        record_captcha_failure(ip_address, scope)
        raise

    clear_captcha(request, scope)

    if not given:
        record_captcha_failure(ip_address, scope)
        raise ValidationError(MSG_CAPTCHA_REQUIRED)
    if not expected or given != expected:
        record_captcha_failure(ip_address, scope)
        raise ValidationError(MSG_CAPTCHA_INVALID)

    record_captcha_success(ip_address, scope)


def extract_image_captcha_value(request: HttpRequest) -> str:
    """Read image CAPTCHA from POST (supports legacy `captcha` name)."""
    if request is None:
        return ''
    for key in ('image_captcha', 'captcha'):
        value = ''
        if hasattr(request, 'POST'):
            value = (request.POST.get(key) or '').strip()
        if value:
            return value
    return ''
