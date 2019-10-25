import logging
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from isle.api import Openapi
from isle.models import User
from isle.utils import pull_sso_user, update_token


class Command(BaseCommand):
    def handle(self, *args, **options):
        for data in Openapi().get_token_list():
            for result in data['results']:
                user = User.objects.filter(unti_id=result['user']).first()
                if not user:
                    user = pull_sso_user(result['user'])
                if not user:
                    logging.error('User with unit id %s does not exist', result['user'])
                    continue
                try:
                    update_token(user, result['key'])
                except IntegrityError:
                    logging.error('Failed to update token for user %s', user.unti_id)
