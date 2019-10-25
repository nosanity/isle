import csv
from django.core.management.base import BaseCommand
from django.db.models import Q
from isle.models import User


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--out', type=str, help='имя файла с результатом', required=True)
        parser.add_argument('-d', type=str, help='разделитель', default=';')

    def handle(self, *args, **options):
        headers = [
            'Система', 'Роль', 'Контекст', 'LeaderID', 'email', 'Фамилия', 'Имя', 'Отчество',
            'Дата выдачи', 'LeaderID выдавшего', 'email выдавшего', 'Фамилия', 'Имя', 'Отчество',
        ]
        with open(options['out'], 'w') as f:
            writer = csv.writer(f, delimiter=options['d'])
            writer.writerow(headers)
            for user in User.objects.filter(Q(is_staff=True) | Q(is_superuser=True)).iterator():
                writer.writerow([
                    'uploads',
                    'superuser' if user.is_superuser else 'staff',
                    '',
                    user.leader_id or '',
                    user.email,
                    user.last_name,
                    user.first_name,
                    user.second_name,
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                ])
