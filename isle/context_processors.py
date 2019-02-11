from isle.models import Context


def context(request):
    contexts = []
    if request.user.is_authenticated and request.user.is_assistant:
        contexts = Context.objects.values_list('id', 'title')
    return {
        'AVAILABLE_CONTEXTS': contexts,
    }
