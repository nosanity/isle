import functools
import logging
import os
from itertools import permutations, combinations
from collections import defaultdict, Counter
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import logout as base_logout
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.db.models import Count, Q
from django.http import HttpResponseForbidden, JsonResponse, HttpResponseRedirect, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.views.generic import TemplateView, View
import requests
from dal import autocomplete
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from social_django.models import UserSocialAuth
from isle.forms import CreateTeamForm, AddUserForm, EventBlockFormset, UserResultForm, TeamResultForm, UserRoleFormset
from isle.models import Event, EventEntry, EventMaterial, User, Trace, Team, EventTeamMaterial, EventOnlyMaterial, \
    Attendance, Activity, ActivityEnrollment, EventBlock, BlockType, UserResult, TeamResult, UserRole
from isle.serializers import AttendanceSerializer
from isle.utils import refresh_events_data, get_allowed_event_type_ids, update_check_ins_for_event, set_check_in


def login(request):
    return render(request, 'login.html', {'next': request.GET.get('next', reverse('index'))})


def logout(request):
    return base_logout(request, next_page='index')


@method_decorator(login_required, name='dispatch')
class Index(TemplateView):
    """
    все эвенты (доступные пользователю)
    """
    template_name = 'index.html'
    DATE_FORMAT = '%Y-%m-%d'

    def get_context_data(self, **kwargs):
        date = self.get_date()
        objects = self.get_events()
        ctx = {
            'objects': objects,
            'date': date.strftime(self.DATE_FORMAT) if date else None,
            'sort_asc': self.is_asc_sort(),
            'activity_filter': self.activity_filter,
        }
        if self.request.user.is_assistant:
            fdict = {
                'initiator__in': User.objects.filter(is_assistant=True).values_list('unti_id', flat=True)
            }
            ctx.update({
                'total_elements': EventMaterial.objects.count() +
                                  EventTeamMaterial.objects.count() +
                                  EventOnlyMaterial.objects.count(),
                'today_elements': EventMaterial.objects.filter(event__in=objects).count() +
                                  EventTeamMaterial.objects.filter(event__in=objects).count() +
                                  EventOnlyMaterial.objects.filter(event__in=objects).count(),
                'total_elements_user': EventMaterial.objects.exclude(initiator__isnull=True).exclude(**fdict).count() +
                                       EventTeamMaterial.objects.exclude(initiator__isnull=True).exclude(**fdict).count(),
                'today_elements_user': EventMaterial.objects.exclude(initiator__isnull=True).exclude(**fdict).filter(event__in=objects).count() +
                                       EventTeamMaterial.objects.exclude(initiator__isnull=True).exclude(**fdict).filter(event__in=objects).count(),
            })
            if self.request.user.is_assistant:
                enrollments = dict(EventEntry.objects.values_list('event_id').annotate(cnt=Count('user_id')))
                check_ins = dict(EventEntry.objects.filter(is_active=True).values_list('event_id')
                                 .annotate(cnt=Count('user_id')))
                for obj in objects:
                    obj.prop_enrollments = enrollments.get(obj.id, 0)
                    obj.prop_checkins = check_ins.get(obj.id, 0)
        else:
            user_materials_num = dict(EventMaterial.objects.filter(event__in=objects, user=self.request.user)
                                      .values_list('event_id').annotate(cnt=Count('user_id')))
            teams = Team.objects.filter(event__in=objects, users=self.request.user).values_list('id', flat=True)
            team_materials_num = dict(EventTeamMaterial.objects.filter(event__in=objects, team_id__in=teams)
                                      .values_list('event_id').annotate(cnt=Count('team_id')))
            event_num, trace_num = 0, 0
            for obj in objects:
                obj.user_materials_num = user_materials_num.get(obj.id, 0)
                obj.team_materials_num = team_materials_num.get(obj.id, 0)
                if obj.user_materials_num or obj.team_materials_num:
                    event_num += 1
                trace_num += (obj.user_materials_num + obj.team_materials_num)
            ctx.update({'event_num': event_num, 'trace_num': trace_num})
        return ctx

    def get_date(self):
        try:
            date = timezone.datetime.strptime(self.request.GET.get('date'), self.DATE_FORMAT).date()
        except:
            if not self.request.user.is_assistant or self.activity_filter:
                return
            date = timezone.localtime(timezone.now()).date()
        return date

    @cached_property
    def activity_filter(self):
        try:
            return Activity.objects.get(ext_id=self.request.GET.get('activity'))
        except (ValueError, TypeError, Activity.DoesNotExist):
            return

    def get_events(self):
        if self.request.user.is_assistant:
            events = Event.objects.filter(is_active=True)
        else:
            events = Event.objects.filter(id__in=EventEntry.objects.filter(user=self.request.user).
                                          values_list('event_id', flat=True))
        if settings.VISIBLE_EVENT_TYPES:
            events = events.filter(event_type_id__in=get_allowed_event_type_ids())
        date = self.get_date()
        if date:
            min_dt = timezone.make_aware(timezone.datetime.combine(date, timezone.datetime.min.time()))
            max_dt = min_dt + timezone.timedelta(days=1)
            events = events.filter(dt_start__gte=min_dt, dt_start__lt=max_dt)
        if self.activity_filter:
            events = events.filter(activity=self.activity_filter)
        events = events.order_by('{}dt_start'.format('' if self.is_asc_sort() else '-'))
        return events

    def is_asc_sort(self):
        return self.request.GET.get('sort') != 'desc'


class GetEventMixin:
    @cached_property
    def event(self):
        return get_object_or_404(Event, uid=self.kwargs['uid'])

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class GetEventMixinWithAccessCheck(GetEventMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseRedirect('{}?next={}'.format(reverse('login'), request.get_full_path()))
        if request.user.is_assistant or EventEntry.objects.filter(user=request.user, event=self.event).exists():
            return super().dispatch(request, *args, **kwargs)
        return render(request, 'to_xle.html', {
            'link': getattr(settings, 'XLE_URL', 'https://xle.2035.university/feedback'),
            'event': self.event,
        })


def get_event_participants(event):
    users = EventEntry.objects.filter(event=event).values_list('user_id')
    return User.objects.filter(id__in=users).order_by('last_name', 'first_name', 'second_name')


class EventView(GetEventMixinWithAccessCheck, TemplateView):
    """
    Просмотр статистики загрузок материалов по эвентам
    """
    template_name = 'event_view.html'

    def get_context_data(self, **kwargs):
        users = list(get_event_participants(self.event))
        user_entry = [i for i in users if i.id == self.request.user.id]
        if user_entry:
            users = user_entry + [i for i in users if i.id != self.request.user.id]
        check_ins = set(EventEntry.objects.filter(event=self.event, is_active=True).values_list('user_id', flat=True))
        attends = set(Attendance.objects.filter(event=self.event, is_confirmed=True).values_list('user_id', flat=True))
        chat_bot_added = set(Attendance.objects.filter(event=self.event, confirmed_by_system=Attendance.SYSTEM_CHAT_BOT)
                             .values_list('user_id', flat=True))
        user_teams = []
        if not self.request.user.is_assistant:
            num = dict(EventMaterial.objects.filter(event=self.event, user__in=users, is_public=True).
                       values_list('user_id').annotate(num=Count('event_id')))
            num[self.request.user.id] = EventMaterial.objects.filter(event=self.event, user=self.request.user).count()
            user_teams = list(Team.objects.filter(event=self.event, users=self.request.user).values_list('id', flat=True))
        else:
            num = dict(EventMaterial.objects.filter(event=self.event, user__in=users).
                       values_list('user_id').annotate(num=Count('event_id')))
        can_delete = set(EventEntry.objects.filter(event=self.event, added_by_assistant=True).
                         values_list('user_id', flat=True))
        for u in users:
            u.materials_num = num.get(u.id, 0)
            u.checked_in = u.id in check_ins
            u.attend = u.id in attends
            u.can_delete = u.id in can_delete
            u.added_by_chat_bot = u.id in chat_bot_added
        event_entry = EventEntry.objects.filter(event=self.event, user=self.request.user).first()
        return {
            'students': users,
            'event': self.event,
            'teams': Team.objects.filter(event=self.event).select_related('creator').order_by('name'),
            'user_teams': user_teams,
            'event_entry': event_entry,
            'event_entry_id': getattr(event_entry, 'id', 0),
        }


class BaseLoadMaterials(GetEventMixinWithAccessCheck, TemplateView):
    template_name = 'load_materials.html'
    material_model = None

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update({
            'traces': self.get_traces_data(),
            'allow_file_upload': getattr(settings, 'ALLOW_FILE_UPLOAD', True),
            'max_size': settings.MAXIMUM_ALLOWED_FILE_SIZE,
            'max_uploads': settings.MAX_PARALLEL_UPLOADS,
            'event': self.event,
            'can_upload': self.can_upload(),
            'can_set_public': self._can_set_public(),
        })
        return data

    def can_upload(self):
        return self.request.user.is_assistant

    def _can_set_public(self):
        return False

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
        try:
            trace_id = int(request.POST.get('trace_name'))
        except (ValueError, TypeError):
            return JsonResponse({}, status=400)
        if not trace_id or not trace_id in [i.id for i in self.event.get_traces()]:
            return JsonResponse({}, status=400)
        if 'add_btn' in request.POST:
            return self.add_item(request)
        return self.delete_item(request)

    def check_post_allowed(self, request):
        if not self.event.is_active or not self.can_upload():
            return JsonResponse({}, status=403)

    def delete_item(self, request):
        material_id = request.POST.get('material_id')
        if not material_id or not material_id.isdigit():
            return JsonResponse({}, status=400)
        trace = Trace.objects.filter(id=request.POST['trace_name']).first()
        if not trace:
            return JsonResponse({}, status=400)
        return self._delete_item(trace, material_id)

    def add_item(self, request, block_upload=False):
        trace, result = None, None
        if not block_upload:
            trace = Trace.objects.filter(id=request.POST['trace_name']).first()
        else:
            result = self.get_result_for_request(request)
        if (block_upload and not result) or (not block_upload and not trace):
            return JsonResponse({}, status=400)
        data = self.get_material_fields(request)
        if not block_upload:
            data['trace'] = trace
        else:
            data['result'] = result
        url = request.POST.get('url_field')
        file_ = request.FILES.get('file_field')
        if bool(file_) == bool(url):
            return JsonResponse({}, status=400)
        if url:
            try:
                r = requests.head(url, timeout=settings.HEAD_REQUEST_CONNECTION_TIMEOUT)
                assert r.ok
                file_type = r.headers.get('content-type', '')
                file_size = r.headers.get('Content-Length')
            except:
                file_type, file_size = '', None
            data.update({'url': url, 'file_type': file_type, 'file_size': file_size})
        else:
            data.update({'file_type': file_.content_type, 'file_size': file_.size})
        data['initiator'] = request.user.unti_id
        material = self.material_model.objects.create(**data)
        if file_:
            material.file.save(self.make_file_path(file_.name), file_)
        resp = {
            'material_id': material.id,
            'url': material.get_url(),
            'name': material.get_name(),
            'comment': getattr(material, 'comment', ''),
            'is_public': getattr(material, 'is_public', True),
            'data_attrs': material.render_metadata(),
            'can_set_public': self._can_set_public()
        }
        if self.extra_context and self.extra_context.get('team_upload'):
            resp['uploader_name'] = request.user.fio
        return JsonResponse(resp)

    def get_material_fields(self, request):
        return {}

    def make_file_path(self, fn):
        return fn

    def set_initiator_users_to_qs(self, qs):
        users = {i.unti_id: i for i in User.objects.filter(unti_id__in=filter(None, [j.initiator for j in qs]))}
        for item in qs:
            item.initiator_user = users.get(item.initiator)


class BaseLoadMaterialsResults(object):
    """
    для загрузки "результатоориентированных" файлов
    """
    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        traces = data['traces']
        # складываем все старые файлы (привязанные к трейсам) в один список, т.к. на странице в
        # разделе отдельных файлов для них нет никакого разделения
        links = functools.reduce(lambda x, y: x + y, [i.get('links', []) for i in traces], [])
        data.update({
            'results': self.get_results(),
            'links': links,
        })
        return data

    def post(self, request, *args, **kwargs):
        resp = self.check_post_allowed(request)
        if resp is not None:
            return resp
        if not request.user.is_assistant:
            raise PermissionDenied
        if 'add_btn' not in request.POST:
            return self.delete_item(request)
        try:
            result_id = int(request.POST.get('result_id'))
        except (ValueError, TypeError):
            return JsonResponse({}, status=400)
        if not result_id or not self.check_event_has_result(result_id):
            return JsonResponse({}, status=400)
        return self.add_item(request, block_upload=True)

    def check_event_has_result(self, result_id):
        pass

    def delete_item(self, request):
        material_id = request.POST.get('material_id')
        if not material_id or not material_id.isdigit():
            return JsonResponse({}, status=400)
        return self._delete_item(material_id)


class LoadMaterials(BaseLoadMaterials):
    """
    Просмотр/загрузка материалов по эвенту
    """
    material_model = EventMaterial
    extra_context = {'with_public_checkbox': True, 'user_upload': True}

    def _can_set_public(self):
        return self.request.user.unti_id == int(self.kwargs['unti_id'])

    def can_upload(self):
        return self.request.user.is_assistant or int(self.kwargs['unti_id']) == self.request.user.unti_id

    def get_materials(self):
        if self.can_upload():
            qs = EventMaterial.objects.filter(event=self.event, user=self.user, trace__isnull=False)
        else:
            qs = EventMaterial.objects.filter(event=self.event, user=self.user, trace__isnull=False, is_public=True)
        self.set_initiator_users_to_qs(qs)
        return qs

    @cached_property
    def user(self):
        return get_object_or_404(User, unti_id=self.kwargs['unti_id'])

    def _delete_item(self, trace, material_id):
        material = EventMaterial.objects.filter(
            event=self.event, user=self.user, trace=trace, id=material_id
        ).first()
        if not material:
            return JsonResponse({}, status=400)
        material.delete()
        logging.warning('User %s has deleted file %s for user %s' %
                        (self.request.user.username, material.get_url(), self.user.username))
        return JsonResponse({})

    def add_item(self, request, **kwargs):
        if not EventEntry.objects.filter(event=self.event, user=self.user).exists():
            return JsonResponse({}, status=400)
        return super().add_item(request, **kwargs)

    def get_material_fields(self, request):
        public = self._can_set_public() and request.POST.get('is_public') in ['on']
        return dict(event=self.event, user=self.user, is_public=public,
                    comment=request.POST.get('comment', ''))

    def make_file_path(self, fn):
        return os.path.join(self.event.uid, str(self.user.unti_id), fn)


class LoadMaterialsAssistant(BaseLoadMaterialsResults, LoadMaterials):
    template_name = 'load_user_materials.html'

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update({
            'user': self.user,
            'result_form': UserResultForm(initial={'event': self.event, 'user': self.user}),
        })
        return data

    def get_result_for_request(self, request):
        return UserResult.objects.filter(id=request.POST.get('result_id')).first()

    def get_result_objects(self):
        qs = self.material_model.objects.filter(user=self.user, trace__isnull=True)
        self.set_initiator_users_to_qs(qs)
        return qs

    def get_results(self):
        results = UserResult.objects.filter(event=self.event, user=self.user).order_by('id')
        data = defaultdict(list)
        for item in self.get_result_objects():
            data[item.result_id].append(item)
        res = []
        for result in results:
            res.append({'result': result, 'links': data.get(result.id, [])})
        return res

    def check_event_has_result(self, result_id):
        return UserResult.objects.filter(event=self.event, user=self.user, id=result_id).exists()

    def _delete_item(self, material_id):
        material = EventMaterial.objects.filter(
            event=self.event, user=self.user, id=material_id
        ).first()
        if not material:
            return JsonResponse({}, status=400)
        material.delete()
        logging.warning('User %s has deleted file %s for user %s' %
                        (self.request.user.username, material.get_url(), self.user.username))
        return JsonResponse({})


def choose_view(assistant_view, user_view):
    def wrapped(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_assistant:
            return assistant_view.as_view()(request, *args, **kwargs)
        return user_view.as_view()(request, *args, **kwargs)
    return wrapped


class LoadTeamMaterials(BaseLoadMaterials):
    """
    Просмотр/загрузка командных материалов по эвенту
    """
    extra_context = {'with_comment_input': True, 'team_upload': True, 'show_owners': True}
    material_model = EventTeamMaterial

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        users = self.team.users.order_by('last_name', 'first_name', 'second_name')
        num = dict(EventMaterial.objects.filter(event=self.event, user__in=users).
                   values_list('user_id').annotate(num=Count('event_id')))
        for u in users:
            u.materials_num = num.get(u.id, 0)
        data.update({'students': users, 'event': self.event, 'team_name': getattr(self.team, 'name', ''),
                     'team': self.team})
        return data

    @cached_property
    def team(self):
        return get_object_or_404(Team, id=self.kwargs['team_id'])

    def get_materials(self):
        qs = EventTeamMaterial.objects.filter(event=self.event, team=self.team).prefetch_related('owners')
        users = {i.unti_id: i for i in User.objects.filter(unti_id__in=filter(None, [j.initiator for j in qs]))}
        for item in qs:
            item.initiator_user = users.get(item.initiator)
            if not self.request.user.is_assistant:
                item.is_owner = self.request.user in item.owners.all()
                item.ownership_url = reverse('team-material-owner', kwargs={
                    'uid': self.event.uid, 'material_id': item.id, 'team_id': self.team.id})
        return qs

    def can_upload(self):
        # командные файлы загружает ассистент или участники этой команды
        return self.request.user.is_assistant or self.team.users.filter(id=self.request.user.id).exists()

    def post(self, request, *args, **kwargs):
        # загрузка и удаление файлов доступны только для эвентов, доступных для оцифровки, и по
        # командам, сформированным в данном эвенте
        if not self.event.is_active or not (self.request.user.is_assistant or
                Team.objects.filter(event=self.event, id=self.kwargs['team_id']).exists()):
            return JsonResponse({}, status=403)
        try:
            trace_id = int(request.POST.get('trace_name'))
        except (ValueError, TypeError):
            return JsonResponse({}, status=400)
        if not trace_id or not trace_id in [i.id for i in self.event.get_traces()]:
            return JsonResponse({}, status=400)
        if 'add_btn' in request.POST:
            return self.add_item(request)
        return self.delete_item(request)

    def check_post_allowed(self, request):
        # загрузка и удаление файлов доступны только для эвентов, доступных для оцифровки, и по
        # командам, сформированным в данном эвенте
        if super().check_post_allowed(request) is not None or not \
                Team.objects.filter(event=self.event, id=self.kwargs['team_id']).exists():
            return JsonResponse({}, status=403)

    def _delete_item(self, trace, material_id):
        material = EventTeamMaterial.objects.filter(
            event=self.event, team=self.team, trace=trace, id=material_id
        ).first()
        if not material:
            return JsonResponse({}, status=400)
        material.delete()
        logging.warning('User %s has deleted file %s for team %s' %
                        (self.request.user.username, material.get_url(), self.team.id))
        return JsonResponse({})

    def make_file_path(self, fn):
        return os.path.join(self.event.uid, str(self.team.team_name), fn)

    def get_material_fields(self, request):
        return dict(event=self.event, team=self.team, comment=request.POST.get('comment', ''),
                    confirmed=self.request.user.is_assistant)


class LoadTeamMaterialsAssistant(BaseLoadMaterialsResults, LoadTeamMaterials):
    template_name = 'load_team_materials.html'

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        roles_formset = UserRoleFormset(initial=UserRole.get_initial_data_for_team_result(self.team, serializable=False))
        data.update({
            'team': self.team,
            'result_form': TeamResultForm(initial={'event': self.event, 'team': self.team}),
            'roles_formset': roles_formset,
        })
        return data

    def get_result_for_request(self, request):
        return TeamResult.objects.filter(id=request.POST.get('result_id')).first()

    def get_result_objects(self):
        qs = self.material_model.objects.filter(team=self.team, trace__isnull=True)
        self.set_initiator_users_to_qs(qs)
        return qs

    def get_results(self):
        results = TeamResult.objects.filter(event=self.event, team=self.team).order_by('id')
        data = defaultdict(list)
        for item in self.get_result_objects():
            data[item.result_id].append(item)
        res = []
        for result in results:
            res.append({'result': result, 'links': data.get(result.id, [])})
        return res

    def check_event_has_result(self, result_id):
        return TeamResult.objects.filter(event=self.event, team=self.team, id=result_id).exists()

    def _delete_item(self, material_id):
        material = EventTeamMaterial.objects.filter(
            event=self.event, team=self.team, id=material_id
        ).first()
        if not material:
            return JsonResponse({}, status=400)
        material.delete()
        logging.warning('User %s has deleted file %s for team %s' %
                        (self.request.user.username, material.get_url(), self.team.id))
        return JsonResponse({})


class LoadEventMaterials(BaseLoadMaterials):
    """
    Загрузка материалов мероприятия
    """
    material_model = EventOnlyMaterial
    extra_context = {'with_comment_input': True, 'show_owners': True, 'event_upload': True}

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update({
            'event_users': get_event_participants(self.event),
            'event_teams': Team.objects.filter(event=self.event).order_by('name'),
        })
        return data

    def get_materials(self):
        qs = EventOnlyMaterial.objects.filter(event=self.event).prefetch_related('owners')
        for item in qs:
            if not self.request.user.is_assistant:
                item.is_owner = self.request.user in item.owners.all()
                item.ownership_url = reverse('event-material-owner', kwargs={
                    'uid': self.event.uid, 'material_id': item.id})
        self.set_initiator_users_to_qs(qs)
        return qs

    def _delete_item(self, trace, material_id):
        material = EventOnlyMaterial.objects.filter(
            event=self.event, trace=trace, id=material_id
        ).first()
        if not material:
            return JsonResponse({}, status=400)
        material.delete()
        logging.warning('User %s has deleted file %s for event %s' %
                        (self.request.user.username, material.get_url(), self.event.uid))
        return JsonResponse({})

    def make_file_path(self, fn):
        return os.path.join(self.event.uid, fn)

    def get_material_fields(self, request):
        return dict(event=self.event, comment=request.POST.get('comment', ''))


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
        if not request.user.is_authenticated or not (request.user.is_assistant or
                EventEntry.objects.filter(event=self.event, user=request.user).exists()):
            return HttpResponseForbidden()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        users = self.get_available_users()
        return {'students': users, 'event': self.event}

    def get_available_users(self):
        return get_event_participants(self.event)

    def post(self, request, uid=None):
        form = CreateTeamForm(data=request.POST, event=self.event, users_qs=self.get_available_users(),
                              creator=request.user)
        if not form.is_valid():
            return JsonResponse({}, status=400)
        form.save()
        return JsonResponse({'redirect': reverse('event-view', kwargs={'uid': self.event.uid})})


class RefreshCheckInView(GetEventMixin, View):
    """
    Обновление чекинов всех пользователей определенного мероприятия из ILE
    или обновление чекина одного пользователя в ILE
    """
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_assistant:
            return super().dispatch(request, *args, **kwargs)
        return HttpResponseForbidden()

    def get(self, request, uid=None):
        if not self.event.ext_id:
            return JsonResponse({'success': False})
        return JsonResponse({'success': bool(update_check_ins_for_event(self.event))})

    # def post(self, request, uid=None):
    #     if not self.event.ext_id:
    #         return JsonResponse({'success': False})
    #     user_id = request.POST.get('user_id')
    #     if not user_id or 'status' not in request.POST:
    #         return JsonResponse({}, status=400)
    #     user = User.objects.filter(id=user_id).first()
    #     if not user or not EventEntry.objects.filter(event=self.event, user=user).exists():
    #         return JsonResponse({}, status=400)
    #     status = request.POST['status'] in ['true', '1', True]
    #     result = set_check_in(self.event, user, status)
    #     if result:
    #         EventEntry.objects.filter(event=self.event, user=user).update(is_active=True)
    #         Attendance.objects.update_or_create(
    #             event=self.event, user=user,
    #             defaults={
    #                 'confirmed_by_user': request.user,
    #                 'is_confirmed': True,
    #                 'confirmed_by_system': Attendance.SYSTEM_UPLOADS,
    #             }
    #         )
    #         logging.info('User %s has checked in user %s on event %s' %
    #                      (request.user.username, user.username, self.event.id))
    #     return JsonResponse({'success': result})


class AddUserToEvent(GetEventMixin, TemplateView):
    """
    Добавить пользователя на мероприятие вручную
    """
    template_name = 'add_user.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_assistant:
            return super().dispatch(request, *args, **kwargs)
        return HttpResponseForbidden()

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update({'event': self.event, 'form': AddUserForm(event=self.event)})
        return data

    def post(self, request, uid=None):
        form = AddUserForm(data=request.POST, event=self.event)
        if form.is_valid():
            user = form.cleaned_data['user']
            EventEntry.all_objects.update_or_create(
                user=user, event=self.event,
                defaults={'added_by_assistant': True, 'check_in_pushed': False, 'deleted': False}
            )
            Attendance.objects.update_or_create(
                event=self.event, user=user,
                defaults={
                    'confirmed_by_user': request.user,
                    'is_confirmed': True,
                    'confirmed_by_system': Attendance.SYSTEM_UPLOADS,
                }
            )
            logging.info('User %s added user %s to event %s' % (request.user.username, user.username, self.event.id))
            return redirect('event-view', uid=self.event.uid)
        else:
            return render(request, self.template_name, {'event': self.event, 'form': form})


class RemoveUserFromEvent(GetEventMixin, View):
    def post(self, request, uid=None):
        if not request.user.is_authenticated or not request.user.is_assistant:
            return JsonResponse({}, status=403)
        try:
            entry = EventEntry.objects.get(event=self.event, user_id=request.POST.get('user_id'),
                                           added_by_assistant=True)
        except (TypeError, ValueError, EventEntry.DoesNotExist):
            return JsonResponse({}, status=404)
        EventEntry.objects.filter(event=self.event, user_id=request.POST.get('user_id')).update(deleted=True)
        Attendance.objects.filter(event=self.event, user_id=request.POST.get('user_id')).delete()
        logging.warning('User %s removed user %s from event %s' %
                        (request.user.username, entry.user.username, entry.event.uid))
        return JsonResponse({})


class UserAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        event_id = self.forwarded.get('event_id')
        if not self.request.user.is_authenticated or not self.request.user.is_assistant or not event_id:
            return User.objects.none()
        qs = User.objects.filter(is_assistant=False).exclude(
            id__in=EventEntry.objects.filter(event_id=event_id).values_list('user_id', flat=True)
        ).filter(id__in=UserSocialAuth.objects.all().values_list('user__id', flat=True))
        if self.q:
            if len(self.q.split()) == 1:
                qs = qs.filter(
                    Q(email__icontains=self.q) | Q(username__icontains=self.q) |
                    Q(last_name__icontains=self.q) | Q(first_name__icontains=self.q) |
                    Q(second_name__icontains=self.q)
                )
            else:
                filters = []
                q_parts = self.q.split()
                fields = ['last_name', 'first_name', 'second_name']
                for p_len in range(1, min(len(fields), len(q_parts)) + 1):
                    indexes = filter(lambda c: c[0] == 0, combinations(range(len(q_parts)), p_len))
                    ranges = (zip(idxs, idxs[1:] + (None,)) for idxs in indexes)
                    parts_combs = [[" ".join(q_parts[i:j]) for i, j in r] for r in ranges]
                    for p in permutations(fields, p_len):
                        filters.append(functools.reduce(lambda x, y: x | y,
                                              (Q(**{k: v for k, v in zip(p, parts)}) for parts in parts_combs)))
                qs = qs.filter(functools.reduce(lambda x, y: x | y, filters))
        return qs

    def get_result_label(self, result):
        full_name = ' '.join(filter(None, [result.last_name, result.first_name, result.second_name]))
        return '%s, (%s)' % (full_name, result.leader_id)


class ResultTypeAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated or not self.request.user.is_assistant:
            return []
        try:
            event = Event.objects.get(id=self.forwarded.get('event'))
        except (TypeError, ValueError, Event.DoesNotExist):
            logging.warning("User %s hasn't provided event parameter for ResultTypeAutocomplete")
            raise SuspiciousOperation
        return BlockType.result_types_for_event(event)

    def get_result_label(self, result):
        return result[1]

    def get_result_value(self, result):
        return result[0]


class Paginator(PageNumberPagination):
    page_size = 20


class ApiPermission(BasePermission):
    def has_permission(self, request, view):
        if request.method == 'OPTIONS':
            return True
        api_key = getattr(settings, 'API_KEY', '')
        key = request.META.get('HTTP_X_API_KEY')
        if key and api_key and key == api_key:
            return True
        return False


class AttendanceApi(ListAPIView):
    """
    **Описание**

        Получение списка присутствовавших на мероприятии или добавление/обновление объекта присутствия.
        В запросе должен присутствовать хедер X-API-KEY

    **Пример get-запроса**

        GET /api/attendance/

    **Пример ответа**

        * {
            "count": 3, // общее количество объектов
            "next": null, // полный url следующей страницы (если есть)
            "previous": null, // полный url предыдущей страницы (если есть)
            "results": [
                {
                    "unti_id": 125, // id пользователя в UNTI SSO
                    "event_id": 2448, // id мероприятия в LABS
                    "created_on": "2018-07-15T07:14:04+10:00", // дата создания объекта
                    "updated_on": "2018-07-15T07:14:04+10:00", // дата обновления объекта
                    "is_confirmed": true, // присутствие подтверждено
                    "confirmed_by_user": 1, // id пользователя подтвердившего присутствие в UNTI SSO
                    "confirmed_by_system": "uploads", // кем подтверждено uploads или chat_bot
                    "run_id": 1405, // id прогона в LABS
                    "activity_id": 439 // id активити в LABS
                },
                ...
          }

    **Пример post-запроса**

    POST /api/attendance/{
            "is_confirmed": true,
            "user_id": 1,
            "event_id": 1,
            "confirmed_by_user": 1,
        }

    **Параметры post-запроса**

        * is_confirmed: подтверждено или нет, boolean
        * user_id: id пользователя в UNTI SSO, integer
        * event_id: id мероприятия в LABS, integer
        * confirmed_by_user: id пользователя в UNTI SSO, который подтвердил присутствие, integer или null,
          необязательный параметр

    **Пример ответа**

         * код 200, словарь с параметрами объекта как при get-запросе, если запрос прошел успешно
         * код 400, если не хватает параметров в запросе
         * код 403, если не указан хедер X-API-KEY или ключ неверен
         * код 404, если не найден пользователь или мероприятие из запроса

    """

    serializer_class = AttendanceSerializer
    pagination_class = Paginator
    permission_classes = (ApiPermission, )

    def get_queryset(self):
        qs = Attendance.objects.order_by('id')
        unti_id = self.request.query_params.get('unti_id')
        if unti_id and unti_id.isdigit():
            qs = qs.filter(user__unti_id=unti_id)
        return qs

    def post(self, request):
        is_confirmed = request.data.get('is_confirmed')
        user_id = request.data.get('user_id')
        event_id = request.data.get('event_id')
        confirmed_by = request.data.get('confirmed_by_user')
        if is_confirmed is None or not user_id or not event_id:
            return Response({'error': 'request should contain is_confirmed, user_id and event_id parameters'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(unti_id=user_id)
        except (User.DoesNotExist, TypeError):
            return Response({'error': 'user does not exist'}, status=status.HTTP_404_NOT_FOUND)
        try:
            event = Event.objects.get(ext_id=event_id)
        except (Event.DoesNotExist, TypeError):
            return Response({'error': 'event does not exist'}, status=status.HTTP_404_NOT_FOUND)
        if confirmed_by is not None:
            try:
                confirmed_by = User.objects.get(unti_id=confirmed_by)
            except (ValueError, TypeError, User.DoesNotExist):
                return Response({'error': 'user does not exist'}, status=status.HTTP_404_NOT_FOUND)
        a = Attendance.objects.update_or_create(
            user=user, event=event,
            defaults={
                'confirmed_by_user': confirmed_by,
                'confirmed_by_system': Attendance.SYSTEM_CHAT_BOT,
                'is_confirmed': is_confirmed,
            }
        )[0]
        EventEntry.all_objects.update_or_create(event=event, user=user,
                                                defaults={'deleted': False, 'added_by_assistant': False})
        logging.info('AttendanceApi request: %s' % request.data)
        return Response(self.serializer_class(instance=a).data)


class UpdateAttendanceView(GetEventMixin, View):
    def post(self, request, uid=None):
        user_id = request.POST.get('user_id')
        if not user_id or 'status' not in request.POST:
            return JsonResponse({}, status=400)
        user = User.objects.filter(id=user_id).first()
        if not request.user.is_assistant:
            return JsonResponse({}, status=400)
        is_confirmed = request.POST.get('status') == 'true'
        Attendance.objects.update_or_create(
            event=self.event, user=user,
            defaults={
                'confirmed_by_user': request.user,
                'is_confirmed': is_confirmed,
                'confirmed_by_system': Attendance.SYSTEM_UPLOADS,
            }
        )
        logging.info('User %s has checked in user %s on event %s' %
                     (request.user.username, user.username, self.event.id))
        print('User %s has changed attendance for user %s on event %s to %s' %
                     (request.user.username, user.username, self.event.id, is_confirmed))
        return JsonResponse({'success': True})


@method_decorator(login_required, name='dispatch')
class IsMaterialPublic(GetEventMixin, View):
    def post(self, request, uid=None):
        try:
            trace = EventMaterial.objects.get(id=request.POST.get('trace_id'))
        except (EventMaterial.DoesNotExist, ValueError, TypeError):
            return JsonResponse({}, status=404)
        if trace.user != request.user:
            return JsonResponse({}, status=403)
        is_public = request.POST.get('is_public') in ['true', 'True']
        EventMaterial.objects.filter(id=trace.id).update(is_public=is_public)
        return JsonResponse({'is_public': is_public})


class ConfirmTeamMaterial(GetEventMixin, View):
    def post(self, request, uid=None, team_id=None):
        if not request.user.is_authenticated or not request.user.is_assistant:
            return JsonResponse({}, status=403)
        try:
            team = Team.objects.get(event=self.event, id=team_id)
            confirmed = EventTeamMaterial.objects.filter(team=team, id=request.POST.get('material_id')).\
                update(confirmed=True)
            assert confirmed
            logging.info('User %s confirmed team %s upload %s' %
                         (request.user.username, team.id, request.POST.get('material_id')))
        except (Team.DoesNotExist, EventTeamMaterial.DoesNotExist, ValueError, TypeError, AssertionError):
            return JsonResponse({}, status=404)
        return JsonResponse({})


class ConfirmTeamView(GetEventMixin, View):
    def post(self, request, uid=None):
        if not request.user.is_authenticated or not request.user.is_assistant:
            return JsonResponse({}, status=403)
        try:
            assert Team.objects.filter(event=self.event, id=request.POST.get('team_id')).update(confirmed=True)
            logging.info('User %s confirmed team %s' % (request.user.username, request.POST.get('team_id')))
        except (Team.DoesNotExist, TypeError, ValueError, AssertionError):
            return JsonResponse({}, status=404)
        return JsonResponse({})


class BaseOwnershipChecker(GetEventMixin, View):
    def post(self, request, **kwargs):
        if request.user.is_assistant or not EventEntry.objects.filter(event=self.event, user=request.user):
            return JsonResponse({}, status=403)
        material = self.get_material()
        confirm = request.POST.get('confirm')
        if confirm not in ['true', 'false']:
            return JsonResponse({}, status=400)
        confirm = confirm == 'true'
        if confirm:
            material.owners.add(request.user)
        else:
            material.owners.remove(request.user)
        return JsonResponse({'is_owner': confirm, 'owners': ', '.join(material.get_owners())})


class TeamMaterialOwnership(BaseOwnershipChecker):
    def get_material(self):
        return get_object_or_404(EventTeamMaterial, id=self.kwargs['material_id'], event=self.event,
                                 team_id=self.kwargs['team_id'])


class EventMaterialOwnership(BaseOwnershipChecker):
    def get_material(self):
        return get_object_or_404(EventOnlyMaterial, id=self.kwargs['material_id'], event=self.event)


class ApproveTextEdit(View):
    def post(self, request, event_entry_id=None):
        if not request.user.is_authenticated or not event_entry_id:
            return JsonResponse({}, status=403)
        try:
            event_entry = EventEntry.objects.get(id=event_entry_id)
            event_entry.approve_text = request.POST.get('approve_text')
            event_entry.save()
        except EventEntry.DoesNotExist:
            return JsonResponse({}, status=404)
        return JsonResponse({})


@method_decorator(login_required, name='dispatch')
class Statistics(TemplateView):
    template_name = 'stat.html'

    def get_context_data(self):
        if not self.request.user.is_assistant:
            return {}
        event_materials = EventMaterial.objects.count()
        event_team_materials = EventTeamMaterial.objects.count()
        event_only_materials = EventOnlyMaterial.objects.count()
        total_elements = event_materials + event_team_materials + event_only_materials

        category_event_materials = Counter(EventMaterial.objects.values_list('event__event_type__title', flat=True))
        category_event_team_materials = Counter(EventTeamMaterial.objects.values_list('event__event_type__title', flat=True))
        category_event_only_materials = Counter(EventOnlyMaterial.objects.values_list('event__event_type__title', flat=True))

        private_elements = EventMaterial.objects.filter(is_public=False).count()
        public_elements = total_elements - private_elements

        fixics = list(User.objects.filter(is_assistant=True).exclude(unti_id__isnull=True).values_list('unti_id', flat=True))

        student_event_materials = (EventMaterial.objects.exclude(initiator__in=fixics) & EventMaterial.objects.filter(initiator__isnull=False)).values_list('initiator', flat=True)
        student_loaders_event_materials = set(student_event_materials)
        student_event_materials_count = len(student_event_materials)

        student_event_team_materials = (EventTeamMaterial.objects.exclude(initiator__in=fixics) & EventTeamMaterial.objects.filter(initiator__isnull=False)).values_list('initiator', flat=True)
        student_loaders_event_team_materials = set(student_event_team_materials)
        student_event_team_materials_count = len(student_event_team_materials)

        student_event_only_materials = (EventOnlyMaterial.objects.exclude(initiator__in=fixics) & EventOnlyMaterial.objects.filter(initiator__isnull=False)).values_list('initiator', flat=True)
        student_loaders_event_only_materials = set(student_event_only_materials)
        student_event_only_materials_count = len(student_event_only_materials)

        student_loaders = len(set(student_loaders_event_materials | student_loaders_event_team_materials | student_loaders_event_only_materials))

        fixics_event_materials = (EventMaterial.objects.filter(initiator__in=fixics) | EventMaterial.objects.filter(initiator__isnull=True)).values_list('initiator', flat=True)
        fixics_loaders_event_materials = set(fixics_event_materials)
        fixics_event_materials_count = len(fixics_event_materials)

        fixics_event_team_materials = (EventTeamMaterial.objects.filter(initiator__in=fixics) | EventTeamMaterial.objects.filter(initiator__isnull=True)).values_list('initiator', flat=True)
        fixics_loaders_event_team_materials = set(fixics_event_team_materials)
        fixics_event_team_materials_count = len(fixics_event_team_materials)

        fixics_event_only_materials = (EventOnlyMaterial.objects.filter(initiator__in=fixics) | EventOnlyMaterial.objects.filter(initiator__isnull=True)).values_list('initiator', flat=True)
        fixics_loaders_event_only_materials = set(fixics_event_only_materials)
        fixics_event_only_materials_count = len(fixics_event_only_materials)

        fixics_loaders = len(set(fixics_loaders_event_materials | fixics_loaders_event_team_materials | fixics_loaders_event_only_materials))

        evs = Event.objects.filter(id__in=set(EventEntry.objects.all().values_list('event', flat=True)), event_type__ext_id__in=[1,2,5,6])
        iterator = (e for e in evs if e.trace_count==0 and EventEntry.objects.filter(is_active=True, event=e).count() > 0)
        without_trace = sum(1 for _ in iterator)

        data = {
            'total_elements': total_elements,
            'event_materials': event_materials,
            'event_team_materials': event_team_materials,
            'event_only_materials': event_only_materials,

            'student_event_materials_count': student_event_materials_count,
            'student_event_team_materials_count': student_event_team_materials_count,
            'student_event_only_materials_count': student_event_only_materials_count,
            'student_loaders': student_loaders,

            'fixics_event_materials_count': fixics_event_materials_count,
            'fixics_event_team_materials_count': fixics_event_team_materials_count,
            'fixics_event_only_materials_count': fixics_event_only_materials_count,
            'fixics_loaders': fixics_loaders,

            'private_elements': private_elements,
            'public_elements': public_elements,

            'category_event_materials': dict(category_event_materials),
            'category_event_team_materials': dict(category_event_team_materials),
            'category_event_only_materials': dict(category_event_only_materials),
            'without_trace': without_trace,

        }
        return data


class TransferView(GetEventMixin, View):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.is_assistant:
            return HttpResponseForbidden()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, uid=None):
        if request.POST.get('type') == 'event':
            return self.move_to_event(request)
        if request.POST.get('type') not in ['user', 'team']:
            return JsonResponse({}, status=400)
        try:
            material = EventOnlyMaterial.objects.get(event=self.event, id=request.POST.get('material_id'))
        except (EventOnlyMaterial.DoesNotExist, TypeError, ValueError):
            return JsonResponse({}, status=404)
        if request.POST['type'] == 'user':
            return self.move_to_user(request, material)
        return self.move_to_team(request, material)

    def move_to_user(self, request, material):
        try:
            user = User.objects.get(id=request.POST.get('dest_id'))
        except (User.DoesNotExist, TypeError, ValueError):
            return JsonResponse({}, status=404)
        if not EventEntry.objects.filter(event=self.event, user=user).exists():
            return JsonResponse({}, status=400)
        EventMaterial.copy_from_object(material, user)
        logging.info('User %s transferred event file %s to user %s' % (request.user.username, material.id, user.id))
        return JsonResponse({})

    def move_to_team(self, request, material):
        try:
            team = Team.objects.get(id=request.POST.get('dest_id'))
        except (Team.DoesNotExist, TypeError, ValueError):
            return JsonResponse({}, status=404)
        if not Team.objects.filter(id=team.id, event=self.event).exists():
            return JsonResponse({}, status=400)
        EventTeamMaterial.copy_from_object(material, team)
        logging.info('User %s transferred event file %s to team %s' % (request.user.username, material.id, team.id))
        return JsonResponse({})

    def move_to_event(self, request):
        model = {'true': EventMaterial, 'false': EventTeamMaterial}.get(request.POST.get('from_user'))
        if not model:
            return JsonResponse({}, status=400)
        try:
            obj = model.objects.get(id=request.POST.get('material_id'), event=self.event)
        except (model.DoesNotExist, TypeError, ValueError):
            return JsonResponse({}, status=404)
        if not obj.trace:
            return JsonResponse({}, status=404)
        if model == EventMaterial and not EventEntry.objects.filter(event=self.event, user=obj.user_id).exists():
            return JsonResponse({}, status=400)
        if model == EventTeamMaterial and not Team.objects.filter(id=obj.team_id, event=self.event).exists():
            return JsonResponse({}, status=400)
        EventOnlyMaterial.copy_from_object(obj)
        logging.info('User %s transferred %s file %s to event' %
                     (request.user.username, 'user' if model == EventMaterial else 'team', obj.id))
        return JsonResponse({})


@method_decorator(login_required, name='dispatch')
class ActivitiesView(TemplateView):
    template_name = 'activities.html'

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        activities = self.get_activities().filter(event__event_type_id__in=get_allowed_event_type_ids()).distinct()
        activities = activities.order_by('title', 'ext_id').annotate(event_count=Count('event'))
        user_materials = dict(EventMaterial.objects.values_list('event__activity_id').annotate(cnt=Count('id')))
        team_materials = dict(EventTeamMaterial.objects.values_list('event__activity_id').annotate(cnt=Count('id')))
        event_materials = dict(EventOnlyMaterial.objects.values_list('event__activity_id').annotate(cnt=Count('id')))
        participants = dict(EventEntry.objects.filter(deleted=False).values_list('event__activity_id').
                            annotate(cnt=Count('user_id')))
        check_ins = dict(EventEntry.objects.filter(deleted=False, is_active=True).values_list('event__activity_id').
                         annotate(cnt=Count('user_id')))
        activity_types = dict(Event.objects.values_list('activity_id', 'event_type__title'))
        for a in activities:
            a.participants_num = participants.get(a.id, 0)
            a.check_ins_num = check_ins.get(a.id, 0)
            a.materials_num = user_materials.get(a.id, 0) + team_materials.get(a.id, 0) + event_materials.get(a.id, 0)
            a.activity_type = activity_types.get(a.id)
        data.update({'objects': activities, 'only_my': self.only_my_activities()})
        return data

    def get_activities(self):
        if not self.only_my_activities():
            return Activity.objects.filter(is_deleted=False)
        return Activity.objects.filter(is_deleted=False, id__in=ActivityEnrollment.objects.filter(user=self.request.user).
                                       values_list('activity_id', flat=True))

    def only_my_activities(self):
        return self.request.GET.get('activities') == 'my'


class CreateEventBlocks(GetEventMixin, TemplateView):
    template_name = 'create_blocks.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseRedirect('{}?next={}'.format(reverse('login'), request.get_full_path()))
        if not request.user.is_authenticated:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update({
            'formset': EventBlockFormset(queryset=EventBlock.objects.none()),
            'event': self.event,
            'blocks': EventBlock.objects.filter(event=self.event).order_by('id'),
        })
        return data

    def post(self, request, **kwargs):
        formset = EventBlockFormset(request.POST)
        if formset.is_valid():
            for form in formset.forms:
                b = form.save(commit=False)
                b.event = self.event
                b.save()
        return redirect('create-blocks', uid=self.event.uid)


class DeleteEventBlock(GetEventMixin, View):
    def post(self, request, **kwargs):
        if request.user.is_authenticated and request.user.is_assistant:
            EventBlock.objects.filter(id=kwargs['block_id']).delete()
            return redirect('create-blocks', uid=self.event.uid)
        raise PermissionDenied


class BaseCreateResult(GetEventMixin, View):
    form_class = UserResultForm
    result_model = UserResult

    def post(self, request, **kwargs):
        if not request.user.is_assistant:
            raise PermissionDenied
        instance = None
        if request.POST.get('result_id'):
            try:
                result = self.result_model.objects.get(id=request.POST.get('result_id'))
                assert result.event == self.event
                self.additional_assertion(result)
                instance = result
            except (ValueError, TypeError, self.result_model.DoesNotExist, AssertionError):
                return JsonResponse({}, status=400)
        form = self.get_form(request, instance)
        if form.is_valid():
            item = form.save()
            res = item.to_json(as_object=True)
            res['created'] = not instance
            logging.info('User {} {} {} #{} with data: {}'.format(
                request.user.username,
                'created' if not instance else 'changed',
                self.result_model._meta.model_name,
                item.id,
                item.to_json()
            ))
            return JsonResponse(res)
        return JsonResponse({}, status=400)

    def additional_assertion(self, result):
        pass

    def get_form(self, request, instance):
        return self.form_class(data=request.POST, instance=instance)


class CreateUserResult(BaseCreateResult):
    def additional_assertion(self, result):
        assert result.user.unti_id == self.kwargs['unti_id']


class CreateTeamResult(BaseCreateResult):
    form_class = TeamResultForm
    result_model = TeamResult

    def additional_assertion(self, result):
        assert result.team_id == self.kwargs['team_id']

    def get_form(self, request, instance):
        team = get_object_or_404(Team, id=self.kwargs['team_id'])
        return self.form_class(data=request.POST, instance=instance, initial={'team': team})


class RolesFormsetRender(GetEventMixin, TemplateView):
    """
    отрисовка формсета с ролями пользователей, нужно для того чтобы без проблем менять
    формсеты на форме редактирования результата при нажатии кнопки редактирования
    """
    template_name = '_user_roles_formset.html'

    def get_context_data(self, **kwargs):
        if not self.request.user.is_assistant:
            raise PermissionDenied
        try:
            result = TeamResult.objects.get(id=self.request.GET.get('id'))
        except (TeamResult.DoesNotExist, ValueError, TypeError):
            raise Http404
        formset = UserRoleFormset(
            initial=UserRole.get_initial_data_for_team_result(result.team, result.id, serializable=False)
        )
        return {
            'roles_formset': formset,
        }
