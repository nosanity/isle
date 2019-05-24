from isle.cache import UserAvailableContexts
from isle.models import Context


def context(request):
    contexts = []
    if request.user.is_authenticated:
        qs = Context.objects.filter(uuid__in=UserAvailableContexts.get(request.user) or [])\
            .values_list('id', 'title', 'guid', 'uuid')
        contexts = [(i[0], i[1] or i[2] or i[3]) for i in qs]
    return {
        'AVAILABLE_CONTEXTS': contexts,
    }
