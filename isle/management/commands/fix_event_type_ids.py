from django.core.management.base import BaseCommand, CommandError
from django.db.utils import IntegrityError
from isle.api import LabsApi, ApiError
from isle.models import EventType


class Command(BaseCommand):
    help = 'Команда изменяет параметр ext_id в типах мероприятий так, чтобы это был их id в labs, а не в ile'

    def handle(self, *args, **options):
        old = dict(EventType.objects.values_list('title', 'ext_id'))
        max_id = EventType.objects.order_by('-ext_id').first().ext_id + 1
        transitions = {}
        try:
            resp = LabsApi().get_types()
            new = {i['title']: i['id'] for i in resp}
            for t in resp:
                try:
                    EventType.objects.filter(title=t['title']).update(ext_id=t['id'])
                except IntegrityError:
                    EventType.objects.filter(ext_id=t['id']).update(ext_id=max_id)
                    transitions[max_id] = t['id']
                    max_id += 1
                    EventType.objects.filter(title=t['title']).update(ext_id=t['id'])
            for title in (set(old.keys()) - set(new.keys())):
                EventType.objects.filter(title=title).update(ext_id=old[title])
        except ApiError:
            raise CommandError('Labs error')
