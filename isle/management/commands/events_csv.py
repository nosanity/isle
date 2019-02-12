import csv
import datetime
import os
from django.core.management.base import BaseCommand, CommandError
from isle.models import Event
from isle.utils import EventGroupMaterialsCSV


class Command(BaseCommand):
    help = 'Сгенерировать csv по всем материалам мероприятия из списка'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', type=str, default='/tmp', help='Куда сохранять результат')
        parser.add_argument('--in', type=str, required=True,
                            help='Файл со списком uuid мероприятий, каждое с новой строки')

    def handle(self, *args, **options):
        with open(options['in']) as f:
            uuids = [i.strip() for i in f.readlines() if i.strip()]
        events = Event.objects.filter(uid__in=uuids)
        missing = set(uuids) - set([i.uid for i in events])
        if missing:
            raise CommandError('Event(s) with uuid(s) not found: %s' % ', '.join(missing))
        filename = '{}_{}.csv'.format('events', datetime.datetime.now().strftime('%d-%m-%Y_%H-%M-%S'))
        obj = EventGroupMaterialsCSV(events, {})
        with open(os.path.join(options['output_dir'], filename), 'w') as f:
            c = csv.writer(f, delimiter=';')
            for line in obj.generate():
                c.writerow(list(map(str, line)))
