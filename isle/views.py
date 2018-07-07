import os
from collections import defaultdict
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import logout as base_logout
from django.db.models import Sum
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.views.generic import TemplateView, View
from isle.forms import CreateTeamForm
from isle.models import Event, EventEntry, EventMaterial, User, Trace, Team, EventTeamMaterial
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
        return {'objects': self.get_events()}

    def get_events(self):
        if self.request.user.is_assistant:
            events = Event.objects.all()
        else:
            events = Event.objects.filter(id__in=EventEntry.objects.filter(user=self.request.user).
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


class GetEventMixin:
    @cached_property
    def event(self):
        return get_object_or_404(Event, uid=self.kwargs['uid'])

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


def get_event_participants(event):
    users = EventEntry.objects.filter(event=event).values_list('user_id')
    return User.objects.filter(id__in=users).order_by('last_name', 'first_name', 'second_name')


class EventView(GetEventMixin, TemplateView):
    """
    Просмотр статистики загрузок материалов по эвентам
    """
    template_name = 'event_view.html'

    def get_context_data(self, **kwargs):
        if not self.request.user.is_assistant:
            return HttpResponseForbidden()
        users = get_event_participants(self.event)
        num = dict(EventMaterial.objects.filter(event=self.event, user__in=users).
                   values_list('user_id').annotate(num=Sum('event_id')))
        for u in users:
            u.materials_num = num.get(u.id, 0)
        return {
            'students': users,
            'event': self.event,
            'teams': Team.objects.filter(event=self.event).order_by('name'),
        }


class BaseLoadMaterials(GetEventMixin, TemplateView):
    template_name = 'load_materials.html'

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update({
            'traces': self.get_traces_data(),
            'allow_file_upload': getattr(settings, 'ALLOW_FILE_UPLOAD', False),
            'max_size': settings.MAXIMUM_ALLOWED_FILE_SIZE,
        })
        return data

    def get_traces_data(self):
        traces = self.event.get_traces()
        result = []
        links = defaultdict(list)
        for item in self.get_materials():
            links[item.trace_id].append(item)
        for trace in traces:
            result.append({'trace': trace, 'links': links.get(trace.id, [])})
        return result

    def post(self, request, *args, **kwargs):
        resp = self.check_post_allowed(request)
        if resp is not None:
            return resp
        trace_id = request.POST.get('trace_name')
        if not trace_id or not self.event.get_traces().filter(id=trace_id).exists():
            return JsonResponse({}, status=400)
        if 'add_btn' in request.POST:
            return self.add_item(request)
        return self.delete_item(request)

    def delete_item(self, request):
        material_id = request.POST.get('material_id')
        if not material_id or not material_id.isdigit():
            return JsonResponse({}, status=400)
        trace = Trace.objects.filter(events=self.event, id=request.POST['trace_name']).first()
        if not trace:
            return JsonResponse({}, status=400)
        return self._delete_item(trace, material_id)


class LoadMaterials(BaseLoadMaterials):
    """
    Просмотр/загрузка материалов по эвенту
    """
    def dispatch(self, request, *args, **kwargs):
        self.user  # проверка того, что пользователь с unti_id из url существует
        # страницу может видеть ассистент или пользователь, указанный в урле
        if self.request.user.unti_id == self.kwargs['unti_id'] or self.event.is_author(self.request.user):
            return super().dispatch(request, *args, **kwargs)
        return HttpResponseForbidden()

    def get_materials(self):
        return EventMaterial.objects.filter(event=self.event, user=self.user)

    @cached_property
    def user(self):
        return get_object_or_404(User, unti_id=self.kwargs['unti_id'])

    def check_post_allowed(self, request):
        # загрузка и удаление файлов доступны только для эвентов, доступных для оцифровки, и по
        # пользователям, запись которых на этот эвент активна
        if not self.event.is_active or not (self.request.user.is_assistant or
                EventEntry.objects.filter(event=self.event, user=self.user, is_active=True).exists()):
            return JsonResponse({}, status=403)

    def _delete_item(self, trace, material_id):
        material = EventMaterial.objects.filter(
            event=self.event, user=self.user, trace=trace, id=material_id
        ).first()
        if not material:
            return JsonResponse({}, status=400)
        material.delete()
        return JsonResponse({})

    def add_item(self, request):
        if not EventEntry.objects.filter(event=self.event, user=self.user).exists():
            return JsonResponse({}, status=400)
        trace = Trace.objects.filter(events=self.event, id=request.POST['trace_name']).first()
        if not trace:
            return JsonResponse({}, status=400)
        data = dict(event=self.event, user=self.user, trace=trace)
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


class LoadTeamMaterials(BaseLoadMaterials):
    """
    Просмотр/загрузка командных материалов по эвенту
    """
    extra_context = {'team_upload': True}

    def dispatch(self, request, *args, **kwargs):
        self.team  # проверка того, что команда с team_id из url существует
        # страницу может видеть только ассистент
        if self.event.is_author(self.request.user):
            return super().dispatch(request, *args, **kwargs)
        return HttpResponseForbidden()

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        users = self.team.users.order_by('last_name', 'first_name', 'second_name')
        num = dict(EventMaterial.objects.filter(event=self.event, user__in=users).
                   values_list('user_id').annotate(num=Sum('event_id')))
        for u in users:
            u.materials_num = num.get(u.id, 0)
        data.update({'students': users, 'event': self.event})
        return data

    @cached_property
    def team(self):
        return get_object_or_404(Team, id=self.kwargs['team_id'])

    def get_materials(self):
        return EventTeamMaterial.objects.filter(event=self.event, team=self.team)

    def post(self, request, *args, **kwargs):
        # загрузка и удаление файлов доступны только для эвентов, доступных для оцифровки, и по
        # командам, сформированным в данном эвенте
        if not self.event.is_active or not (self.request.user.is_assistant or
                Team.objects.filter(event=self.event, id=self.kwargs['team_id']).exists()):
            return JsonResponse({}, status=403)
        trace_id = request.POST.get('trace_name')
        if not trace_id or not self.event.get_traces().filter(id=trace_id).exists():
            return JsonResponse({}, status=400)
        if 'add_btn' in request.POST:
            return self.add_item(request)
        return self.delete_item(request)

    def check_post_allowed(self, request):
        # загрузка и удаление файлов доступны только для эвентов, доступных для оцифровки, и по
        # командам, сформированным в данном эвенте
        if not self.event.is_active or not (self.request.user.is_assistant or
                Team.objects.filter(event=self.event, id=self.kwargs['team_id']).exists()):
            return JsonResponse({}, status=403)

    def _delete_item(self, trace, material_id):
        material = EventTeamMaterial.objects.filter(
            event=self.event, team=self.team, trace=trace, id=material_id
        ).first()
        if not material:
            return JsonResponse({}, status=400)
        material.delete()
        return JsonResponse({})

    def add_item(self, request):
        trace = Trace.objects.filter(events=self.event, id=request.POST['trace_name']).first()
        if not trace:
            return JsonResponse({}, status=400)
        data = dict(event=self.event, team=self.team, trace=trace, comment=request.POST.get('comment', ''))
        url = request.POST.get('url_field')
        file_ = request.FILES.get('file_field')
        if bool(file_) == bool(url):
            return JsonResponse({}, status=400)
        if url:
            data['url'] = url
        material = EventTeamMaterial.objects.create(**data)
        if file_:
            material.file.save(self.make_file_path(file_.name), file_)
        return JsonResponse({'material_id': material.id, 'url': material.get_url()})

    def make_file_path(self, fn):
        return os.path.join(self.event.uid, str(self.team.team_name), fn)


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


class CreateTeamView(GetEventMixin, TemplateView):
    template_name = 'create_team.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.is_assistant:
            return HttpResponseForbidden()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        users = self.get_available_users()
        return {'students': users, 'event': self.event}

    def get_available_users(self):
        return get_event_participants(self.event).exclude(
            id__in=Team.objects.filter(event=self.event).values_list('users', flat=True))

    def post(self, request, uid=None):
        form = CreateTeamForm(data=request.POST, event=self.event, users_qs=self.get_available_users())
        if not form.is_valid():
            return JsonResponse({}, status=400)
        form.save()
        return JsonResponse({'redirect': reverse('event-view', kwargs={'uid': self.event.uid})})
