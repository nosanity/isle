import logging
from django.conf import settings
from django.core.management.base import BaseCommand
import requests
from isle.models import EventMaterial, EventTeamMaterial, EventOnlyMaterial


class Command(BaseCommand):
    help = 'Сделать head запросы для всех материалов и сохранить их content-type'

    def handle(self, *args, **options):
        for model in (EventMaterial, EventTeamMaterial, EventOnlyMaterial):
            print('Processing %s' % model._meta.model_name)
            self.process_queryset(model.objects.all())

    def process_queryset(self, qs):
        count = qs.count()
        for num, item in enumerate(qs.iterator(), 1):
            try:
                r = requests.head(item.get_url(), timeout=settings.HEAD_REQUEST_CONNECTION_TIMEOUT)
                assert r.ok, 'status code %s' % r.status_code
                content_type = r.headers.get('content-type', '')
                file_size = r.headers.get('Content-Length')
                item._meta.model.objects.filter(id=item.id).update(file_type=content_type, file_size=file_size)
            except Exception as e:
                logging.error('Failed to get metadata for link %s (%s #%s): %s' %
                              (item.get_url(), item._meta.model_name, item.id, e))
            if num % 100 == 0:
                print('%s %s/%s' % (item._meta.model_name, num, count))
