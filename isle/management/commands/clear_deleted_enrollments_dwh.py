from django.core.management.base import BaseCommand
from isle.dwh_tools.xle import clear_deleted_run_enrollments


class Command(BaseCommand):
    help = 'Очистка удаленных записей на прогоны'

    def handle(self, *args, **options):
        clear_deleted_run_enrollments()
