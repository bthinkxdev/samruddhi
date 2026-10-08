"""Staging settings — production-like with debug off and strict hosts."""

from .base import *  # noqa: F401, F403
from .base import env

DEBUG = env.bool("DEBUG", default=False)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
