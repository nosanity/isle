import logging
from django.core.management.base import BaseCommand
from isle.models import EventEntry
from isle.utils import set_check_in


class Command(BaseCommand):
    help = 'Проставить в ILE чекины пользователей, добавленных вручную'

    def handle(self, *args, **options):
        for e in EventEntry.objects.select_related('user', 'event').filter(
                added_by_assistant=True, check_in_pushed=False).iterator():
            if set_check_in(e.event, e.user, True):
                EventEntry.objects.filter(id=e.id).update(check_in_pushed=True)
                logging.info('Check in for user %s on event %s has been successfully pushed' %
                             (e.user.username, e.event_id))
            else:
                logging.info('Failed to push check in for user %s on event %s' %
                             (e.user.username, e.event_id))
