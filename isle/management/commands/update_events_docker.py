from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from isle.models import UpdateTimes
from isle.utils import refresh_events_data, update_event_entries, \
    update_run_enrollments, update_teams, update_metamodels


class Command(BaseCommand):
    def handle(self, *args, **options):
        now = timezone.now()
        dt = now.replace(
            hour=getattr(settings, 'UPDATE_ALL_EVENTS_UTC_HOUR', 0), minute=0, second=0, microsecond=0
        )
        last_update = UpdateTimes.get_last_update_for_event(UpdateTimes.ALL_EVENTS, iso=False)
        update_all_events = now >= dt and (not last_update or last_update.date() < dt.date())
        update_metamodels()
        refresh_events_data(fast=not update_all_events)
        if update_all_events:
            UpdateTimes.set_last_update_for_event(UpdateTimes.ALL_EVENTS, now)
        update_event_entries()
        update_run_enrollments()
        update_teams()
