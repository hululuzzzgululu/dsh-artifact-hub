from datetime import datetime, timezone

from ..domain.errors import ValidationError


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        raise ValidationError("expires_at must be an ISO-8601 timestamp")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
