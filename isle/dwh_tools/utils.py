import logging
from django.conf import settings
from django.utils import timezone
import MySQLdb
from isle.models import UpdateTimes


def get_dwh_connect(database):
    return MySQLdb.connect(
        host=getattr(settings, "DWH_HOST"),
        port=int(getattr(settings, "DWH_PORT")),
        user=getattr(settings, "DWH_USER"),
        passwd=getattr(settings, "DWH_PASSWD"),
        db=settings.DWH_DATABASES[database],
        charset='UTF8',
    )


def format_dt(dt):
    return dt.astimezone(timezone.pytz.utc).strftime('%Y-%m-%d %H:%M:%S')


def parse_dt(dt, default=None):
    return timezone.pytz.utc.localize(dt) if dt else default


def change_update_time(update_key, pass_current_time=False):
    def wrapper(fn):
        def inner(*args, **kwargs):
            now = timezone.now()
            dt = UpdateTimes.get_last_update_for_event(update_key, iso=False)
            add_kwargs = {'dt': format_dt(dt) if dt else None}
            if pass_current_time:
                add_kwargs['now'] = now
            kwargs.update(add_kwargs)
            result = fn(*args, **kwargs)
            UpdateTimes.set_last_update_for_event(update_key, now)
            return result
        return inner
    return wrapper
