import csv
import json
from django.core.management.base import BaseCommand, CommandError
from isle.models import EventEntry, User, Event


class Command(BaseCommand):
    delimiter = ','

    def add_arguments(self, parser):
        parser.add_argument('--dump', help='Сохранить текущее состояние', default=None, type=str)
        parser.add_argument('--load', help='Обновить данными из файла', default=None, type=str)
        parser.add_argument('--diff', help='Путь к diff файлу результата обновления', default=None, type=str)

    def handle(self, *args, **options):
        if options.get('dump'):
            self.save_current_state(options['dump'])
        elif options.get('load'):
            if not options.get('diff'):
                raise CommandError('--diff must be specified')
            self.load_data(options['load'], options['diff'])
        else:
            raise CommandError('--dump or --load must be specified')

    def save_current_state(self, filename):
        with open(filename, 'w') as f:
            writer = csv.writer(f, delimiter=self.delimiter)
            for i in EventEntry.all_objects.values_list('user__unti_id', 'event__ext_id', 'deleted').\
                    order_by('event__ext_id', 'user__unti_id').iterator():
                writer.writerow(i)

    def load_data(self, filename, diff_filename):
        unti_id_to_user_id = dict(User.objects.values_list('unti_id', 'id'))
        ext_id_to_event_id = dict(Event.objects.values_list('ext_id', 'id'))
        enrollments = set(EventEntry.objects.values_list('user__unti_id', 'event__ext_id'))
        bad_unti_ids, bad_ext_ids = [], []
        created_enrollments, restored_enrollments = [], []
        with open(filename) as f:
            reader = csv.reader(f, delimiter=self.delimiter)
            for n, line in enumerate(reader):
                if not n:
                    continue
                key = int(line[0]), int(line[1])
                if key in enrollments:
                    continue
                unti_id, ext_id = key
                user_id = unti_id_to_user_id.get(unti_id)
                if not user_id:
                    bad_unti_ids.append(unti_id)
                    continue
                event_id = ext_id_to_event_id.get(ext_id)
                if not event_id:
                    bad_ext_ids.append(ext_id)
                    continue
                e, created = EventEntry.all_objects.update_or_create(
                    event_id=event_id, user_id=user_id, defaults={'deleted': False}
                )
                if created:
                    created_enrollments.append(key)
                else:
                    restored_enrollments.append(key)
        with open(diff_filename, 'w') as f:
            json.dump({'created': created_enrollments, 'restored': restored_enrollments}, f, indent=4)
        if bad_unti_ids:
            print('User(s) for unti_id not found: %s' % ', '.join(str(i) for i in set(bad_unti_ids)))
        if bad_ext_ids:
            print('Event(s) for ext_id not found: %s' % ', '.join(str(i) for i in set(bad_ext_ids)))
