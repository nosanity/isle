from django.core.management.base import BaseCommand
from isle.utils import refresh_events_data


class Command(BaseCommand):
    help = 'Полная синхронизация мероприятий'

    def handle(self, *args, **options):
        refresh_events_data(fast=False)
