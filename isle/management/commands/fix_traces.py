import logging
from django.core.management.base import BaseCommand
from isle.models import EventType
from isle.utils import create_traces_for_event_type


class Command(BaseCommand):
    def handle(self, *args, **options):
        for et in EventType.objects.filter(trace__isnull=True):
            logging.info('creating traces for event type %s', et.uuid)
            create_traces_for_event_type(et)
