from django.core.management.base import BaseCommand
from isle.utils import refresh_events_data, update_event_entries, \
    update_run_enrollments, update_teams, update_metamodels


class Command(BaseCommand):
    help = 'Обновить список эвентов и активностей из LABS, а также трейсы'

    def handle(self, *args, **options):
        update_metamodels()
        refresh_events_data()
        update_event_entries()
        update_run_enrollments()
        update_teams()
