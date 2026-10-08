"""Dashboard admin.

The custom dashboard UI (see dashboard/urls.py) is the primary staff surface.
Models not yet covered by a bespoke dashboard screen (gifting option catalogs,
corporate orders, recurring schedules, subscriptions, currencies, zones, etc.)
remain fully manageable through Django's built-in admin at /admin/, where each
owning app already registers them. No additional registration is required here.
"""
