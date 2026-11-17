"""Explicit coordinated cutover switch; never inferred from a partial copy."""

import os


def enabled():
    return os.environ.get("CRM_BASE_ADOPTION", "").strip().lower() in {"1", "true", "yes"}
