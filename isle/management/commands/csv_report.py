import csv
from collections import defaultdict
from urllib.parse import urlparse
from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import reverse
from isle.models import EventOnlyMaterial, EventTeamMaterial, EventMaterial

ALL = '__all__'


def get_type(m):
    s = urlparse(m.get_url()).path.rstrip().split('/')[-1]
    if '.' in s:
        return s.split('.')[-1]
    return ''


def get_row(event_id, data, all_types):
    event_data = data['event'].data or {}
    res = [
        '{}{}'.format(settings.BASE_URL, reverse('event-view', kwargs={'uid': data['event'].uid})),
        event_data.get('activity', {}).get('ext_id'),
        event_data.get('run', {}).get('ext_id'),
        data['event'].ext_id,
    ] + [data['types'].get(t, 0) for t in all_types] + [data['types'].get(ALL, 0)]
    return res


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--out', type=str, help='Имя файла результата', required=True)

    def handle(self, *args, **options):
        result = {}
        models = (EventOnlyMaterial, EventTeamMaterial, EventMaterial)
        all_types = set()
        for model in models:
            for m in model.objects.select_related('event').iterator():
                if m.event_id not in result:
                    result[m.event_id] = {
                        'event': m.event,
                        'types': defaultdict(int)
                    }
                ctype = get_type(m)
                all_types.add(ctype)
                result[m.event_id]['types'][ctype] += 1
                result[m.event_id]['types'][ALL] += 1

        all_types = sorted(all_types)
        headers = ['Ссылка на мероприятие', 'Activity ID', 'Run ID', 'Event ID'] + \
                  ['Количество %s файлов' % ('.{}'.format(i) if i else '?') for i in all_types] + \
                  ['Всего файлов']
        with open(options['out'], 'w') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(headers)
            for event_id, data in result.items():
                writer.writerow(get_row(event_id, data, all_types))
