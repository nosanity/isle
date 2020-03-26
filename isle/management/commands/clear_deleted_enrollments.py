from django.core.management.base import BaseCommand
from isle.utils import clear_run_enrollments


class Command(BaseCommand):
    help = 'Очистка удаленных записей на прогоны за последний день'

    def handle(self, *args, **options):
        clear_run_enrollments()
