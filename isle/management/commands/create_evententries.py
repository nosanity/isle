import logging
from django.core.management.base import BaseCommand
from isle.models import EventEntry, Attendance


class Command(BaseCommand):
    help = 'Создать EventEntry для пользователей с Attendance, если их до этого не было'

    def handle(self, *args, **options):
        existing = set(EventEntry.objects.values_list('event_id', 'user_id'))
        for e_id, u_id in Attendance.objects.values_list('event_id', 'user_id'):
            if (e_id, u_id) not in existing:
                EventEntry.objects.create(event_id=e_id, user_id=u_id)
                logging.info('Created EventEntry for event_id %s user_id %s' % (e_id, u_id))
