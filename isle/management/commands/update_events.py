from django.conf import settings
from django.core.management.base import BaseCommand
from isle.utils import refresh_events_data, update_events_traces, refresh_events_data_v2


class Command(BaseCommand):
    help = 'Обновить список эвентов и ассайнментов из ILE, а также трейсы'

    def handle(self, *args, **options):
        if settings.USE_ILE_SNAPSHOT:
            refresh_events_data(force=True, refresh_participants=True)
        else:
            refresh_events_data_v2()
        update_events_traces()
