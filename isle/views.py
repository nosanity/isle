import os
from collections import defaultdict
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import logout as base_logout
from django.db.models import Sum
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.views.generic import TemplateView, View
from isle.models import Event, EventEntry, EventMaterial, User
from isle.utils import refresh_events_data


def logout(request):
    return base_logout(request, next_page='index')


@method_decorator(login_required, name='dispatch')
class Index(TemplateView):
    """
    все эвенты (доступные пользователю)
    """
    template_name = 'index.html'

    def get_context_data(self, **kwargs):
        self.fetch_events()
        return {'objects': self.get_events()}

    def get_events(self):
        if self.request.user.is_assistant:
            events = Event.objects.all()
        else:
            events = Event.objects.filter(id__in=EventEntry.objects.filter(user=self.request.user, is_active=True).
                                          values_list('event_id', flat=True))
        events = events.order_by('-dt_end')
        inactive_events, active_events, current_events = [], [], []
        delta = settings.CURRENT_EVENT_DELTA
        for e in events:
            if not e.is_active:
                inactive_events.append(e)
            elif e.dt_end and timezone.now() - timezone.timedelta(seconds=delta) < e.dt_end < timezone.now() \
                    + timezone.timedelta(seconds=delta):
                current_events.append(e)
            else:
                active_events.append(e)
        current_events.reverse()
        return current_events + active_events + inactive_events

    def fetch_events(self):
        refresh_events_data()


class GetEventMixin:
    @cached_property
    def event(self):
        return get_object_or_404(Event, uid=self.kwargs['uid'])

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class EventView(GetEventMixin, TemplateView):
    """
    Просмотр статистики загрузок материалов по эвентам
    """
    template_name = 'event_view.html'

    def get_context_data(self, **kwargs):
        users = EventEntry.objects.filter(event=self.event).values_list('user_id')
        users = User.objects.filter(id__in=users).order_by('last_name', 'first_name', 'second_name')
        num = dict(EventMaterial.objects.filter(event=self.event, user__in=users).
                   values_list('user_id').annotate(num=Sum('event_id')))
        for u in users:
            u.materials_num = num.get(u.id, 0)
        return {
            'students': users,
            'event': self.event,
        }

    def fetch_users(self):
        refresh_events_data(refresh_participants=True, refresh_for_events=[self.event.uid])


class LoadMaterials(GetEventMixin, TemplateView):
    """
    Просмотр/загрузка материалов по эвенту
    """
    template_name = 'load_materials.html'

    def dispatch(self, request, *args, **kwargs):
        self.user  # проверка того, что пользователь с unti_id из url существует
        # страницу может видеть ассистент или пользователь, указанный в урле
        if self.request.user.unti_id == self.kwargs['unti_id'] or self.event.is_author(self.request.user):
            return super().dispatch(request, *args, **kwargs)
        return HttpResponseForbidden()

    def get_context_data(self, **kwargs):
        return {
            'traces': self.get_traces_data(),
            'allow_file_upload': getattr(settings, 'ALLOW_FILE_UPLOAD', False),
            'max_size': settings.MAXIMUM_ALLOWED_FILE_SIZE,
        }

    @cached_property
    def user(self):
        return get_object_or_404(User, unti_id=self.kwargs['unti_id'])

    def get_traces_data(self):
        traces = self.event.get_traces()
        result = []
        links = defaultdict(list)
        for item in EventMaterial.objects.filter(event=self.event, user=self.user):
            links[item.trace].append(item)
        for name in traces:
            result.append({'name': name, 'links': links.get(name, [])})
        return result

    def post(self, request, *args, **kwargs):
        # загрузка и удаление файлов доступны только для эвентов, доступных для оцифровки, и по
        # пользователям, запись которых на этот эвент активна
        if not self.event.is_active or not (self.request.user.is_assistant or
                EventEntry.objects.filter(event=self.event, user=self.user, is_active=True).exists()):
            return JsonResponse({}, status=403)
        name = request.POST.get('trace_name')
        if not name or name not in self.event.get_traces():
            return JsonResponse({}, status=400)
        if 'add_btn' in request.POST:
            return self.add_item(request)
        return self.delete_item(request)

    def delete_item(self, request):
        material_id = request.POST.get('material_id')
        if not material_id or not material_id.isdigit():
            return JsonResponse({}, status=400)
        material = EventMaterial.objects.filter(
            event=self.event, user=self.user, trace=request.POST['trace_name'], id=material_id
        ).first()
        if not material:
            return JsonResponse({}, status=400)
        material.delete()
        return JsonResponse({})

    def add_item(self, request):
        if not EventEntry.objects.filter(event=self.event, user=self.user).exists():
            return JsonResponse({}, status=400)
        data = dict(event=self.event, user=self.user, trace=request.POST['trace_name'])
        url = request.POST.get('url_field')
        file_ = request.FILES.get('file_field')
        if bool(file_) == bool(url):
            return JsonResponse({}, status=400)
        if url:
            data['url'] = url
        material = EventMaterial.objects.create(**data)
        if file_:
            material.file.save(self.make_file_path(file_.name), file_)
        return JsonResponse({'material_id': material.id, 'url': material.get_url()})

    def make_file_path(self, fn):
        return os.path.join(self.event.uid, str(self.user.unti_id), fn)


class RefreshDataView(View):
    def get(self, request, uid=None):
        if not request.user.is_assistant:
            success = False
        else:
            if uid:
                if not Event.objects.filter(uid=uid).exists():
                    success = False
                else:
                    success = refresh_events_data(force=True, refresh_participants=True, refresh_for_events=[uid])
            else:
                success = refresh_events_data(force=True)
        return JsonResponse({'success': bool(success)})
