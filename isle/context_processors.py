from django.conf import settings
from isle.cache import UserAvailableContexts
from isle.models import Context, ZendeskData


def context(request):
    contexts = []
    if request.user.is_authenticated:
        qs = Context.objects.filter(uuid__in=UserAvailableContexts.get(request.user) or [])\
            .values_list('id', 'title', 'guid', 'uuid')
        contexts = [(i[0], i[1] or i[2] or i[3]) for i in qs]
    return {
        'AVAILABLE_CONTEXTS': contexts,
        'ZENDESK_DATA': ZendeskData.objects.first(),
        'NOW_URL': settings.NOW_URL,
    }
