from django.core.management.base import BaseCommand
from isle.utils import update_casbin_data


class Command(BaseCommand):
    help = 'Ручная синхронизация ролей с sso'

    def handle(self, *args, **options):
        update_casbin_data()
