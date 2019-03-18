from isle.models import Context


def context(request):
    contexts = []
    if request.user.is_authenticated and request.user.has_assistant_role():
        contexts = ((i[0], i[1] or i[2] or i[3]) for i in Context.objects.values_list('id', 'title', 'guid', 'uuid'))
    return {
        'AVAILABLE_CONTEXTS': contexts,
    }
