"""slugify — URL slug generation module (core logic + schemas + FastAPI router)."""
from .slugify import slug, slug_async, slugify
from .schemas import SlugifyRequest, SlugifyResponse
from .main import app, router

__all__ = [
    "slug",
    "slug_async",
    "slugify",
    "SlugifyRequest",
    "SlugifyResponse",
    "app",
    "router",
]