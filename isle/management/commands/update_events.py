from django.core.management.base import BaseCommand
from isle.utils import refresh_events_data, update_events_traces, update_contexts, update_event_entries, \
    update_run_enrollments


class Command(BaseCommand):
    help = 'Обновить список эвентов и активностей из LABS, а также трейсы'

    def handle(self, *args, **options):
        refresh_events_data()
        update_events_traces()
        update_contexts()
        update_event_entries()
        update_run_enrollments()
