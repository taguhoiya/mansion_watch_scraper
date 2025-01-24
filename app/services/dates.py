from datetime import datetime, timedelta, timezone


def get_current_time():
    return datetime.now(timezone.utc) + timedelta(hours=9)
