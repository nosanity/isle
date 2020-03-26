import datetime
from django.core.management.base import BaseCommand
from isle.utils import refresh_events_data


class Command(BaseCommand):
    help = 'Полная синхронизация мероприятий или за конкретную дату'

    def add_arguments(self, parser):
        parser.add_argument('--date', type=str, help='дата в формате %Y-%m-%d', required=False)

    def handle(self, *args, **options):
        if options.get('date'):
            datetime.datetime.strptime(options['date'], '%Y-%m-%d')
            refresh_events_data(date=options['date'])
        else:
            refresh_events_data(fast=False)
