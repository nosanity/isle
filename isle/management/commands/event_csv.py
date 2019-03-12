import csv
import datetime
import os
from django.core.management.base import BaseCommand, CommandError
from isle.models import Event
from isle.utils import EventMaterialsCSV


class Command(BaseCommand):
    help = 'Сгенерировать csv по всем материалам мероприятия'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', type=str, default='/tmp', help='Куда сохранять результат')
        parser.add_argument('--uid', type=str, required=True, help='UUID мероприятия')

    def handle(self, *args, **options):
        event = Event.objects.filter(uid=options['uid']).first()
        if not event:
            raise CommandError('Event with uuid %s not found' % options['uuid'])
        filename = '{}_{}.csv'.format(event.uid, datetime.datetime.now().strftime('%d-%m-%Y_%H-%M-%S'))
        obj = EventMaterialsCSV(event)
        with open(os.path.join(options['output_dir'], filename), 'w') as f:
            c = csv.writer(f, delimiter=';')
            for line in obj.generate():
                c.writerow(list(map(str, line)))
