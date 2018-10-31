from django.core.management.base import BaseCommand, CommandError
from isle.api import LabsApi, ApiError
from isle.models import EventType


class Command(BaseCommand):
    help = 'Команда добавляет uuid к типам мероприятий'

    def handle(self, *args, **options):
        try:
            name_to_uuid = {}
            for resp in LabsApi().get_types():
                for i in resp:
                    name_to_uuid[i['title'].lower()] = i['uuid']
            for et in EventType.objects.all():
                if et.title.lower() in name_to_uuid:
                    EventType.objects.filter(id=et.id).update(uuid=name_to_uuid[et.title.lower()])
        except ApiError:
            raise CommandError('Labs error')
