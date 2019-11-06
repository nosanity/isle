from django.core.cache import caches
from django.core.management.base import BaseCommand
from isle.cache import get_user_available_contexts, UserContextAssistantCache
from isle.models import CasbinData, User, Context


class Command(BaseCommand):
    help = 'Заполнение кэша пользовательских прав'

    def add_arguments(self, parser):
        parser.add_argument('-n', type=int, default=500)

    def handle(self, *args, **options):
        cache = caches['default']
        contexts = list(Context.objects.values_list('uuid', flat=True))
        casbin_data = CasbinData.objects.first()
        if not casbin_data:
            return
        policy = casbin_data.policy
        users_with_groups = set()
        for line in policy.splitlines():
            line = line.strip()
            if line and line.startswith('g'):
                unti_id = int(line.split(',')[1].strip())
                users_with_groups.add(unti_id)

        values = {}
        user_cache_cls = UserContextAssistantCache()
        for i, user in enumerate(User.objects.exclude(unti_id__in=users_with_groups).iterator(), 1):
            for ctx in contexts:
                values[user_cache_cls.get_cache_key(user, ctx)] = False
            if i % options['n'] == 0:
                cache.set_many(values)
                values = {}
        if values:
            cache.set_many(values)

        for user in User.objects.filter(unti_id__in=users_with_groups).iterator():
            get_user_available_contexts(user)
