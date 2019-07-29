import csv
import codecs
import io
import functools
import json
import logging
import os
from functools import wraps
from itertools import permutations, combinations
from collections import defaultdict, Counter
from urllib.parse import quote
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import logout as base_logout
from django.core.files.storage import default_storage
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.db import transaction
from django.db.models import Count, Q, F
from django.http import HttpResponseForbidden, JsonResponse, HttpResponseRedirect, Http404, FileResponse, \
    StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, resolve, Resolver404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.views.generic import TemplateView, View, ListView
import django_filters
import requests
from dal import autocomplete
from rest_framework import status, exceptions
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import ListAPIView, CreateAPIView
from rest_framework.pagination import PageNumberPagination, LimitOffsetPagination
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import BasePermission, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from social_django.models import UserSocialAuth
from isle.api import LabsApi, XLEApi, DpApi, SSOApi
from isle.cache import UserAvailableContexts
from isle.filters import LabsUserResultFilter, LabsTeamResultFilter, StatisticsFilter
from isle.forms import CreateTeamForm, AddUserForm, EventBlockFormset, UserResultForm, TeamResultForm, UserRoleFormset, \
    EventMaterialForm, EditTeamForm
from isle.kafka import send_object_info, KafkaActions, check_kafka
from isle.models import Event, EventEntry, EventMaterial, User, Trace, Team, EventTeamMaterial, EventOnlyMaterial, \
    Attendance, Activity, ActivityEnrollment, EventBlock, BlockType, UserResult, TeamResult, UserRole, ApiUserChart, \
    LabsEventResult, LabsUserResult, LabsTeamResult, Context, CSVDump, PLEUserResult, RunEnrollment, DTraceStatistics, \
    CircleItem
from isle.serializers import AttendanceSerializer, LabsUserResultSerializer, LabsTeamResultSerializer, \
    UserFileSerializer, UserResultSerializer, EventOnlyMaterialSerializer, DTraceStatisticsSerializer
from isle.tasks import generate_events_csv, team_members_set_changed, handle_ple_user_result
from isle.utils import refresh_events_data, get_allowed_event_type_ids, update_check_ins_for_event, set_check_in, \
    recalculate_user_chart_data, get_results_list, get_release_version, check_mysql_connection, \
    EventMaterialsCSV, EventGroupMaterialsCSV, BytesCsvStreamWriter, get_csv_encoding_for_request, XLSWriter, \
    check_celery_active, calculate_user_context_statistics


VIEW_MODE_COOKIE_NAME = 'index-view-mode'


class ResultUpdateType:
    SET_VALIDATION = 'set_validation'
    EDIT_COMMENT = 'edit_comment'
    ADD_FILE = 'add_file'
    EDIT_TOOLS = 'edit_tools'
    BLOCK_CHANGED = 'block_changed'
    DELETE_FILE = 'delete_file'


def login(request):
    return render(request, 'login.html', {'next': request.GET.get('next', reverse('index'))})


def logout(request):
    return base_logout(request)


def context_setter(f):
    """
    декоратор для установки контекста ассистенту при заходе на страницы мероприятия и связанных страниц в случае,
    если его текущий контекст не совпадает с контекстом этого мероприятия
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            uid = kwargs.get('uid')
            if uid:
                event = Event.objects.filter(uid=uid).first()
                if event and request.user.is_authenticated and request.user.has_assistant_role() and \
                        request.user.chosen_context_id != event.context_id:
                    request.user.chosen_context_id = event.context_id
                    request.user.save(update_fields=['chosen_context_id'])
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator(f)


class SearchHelperMixin:
    DATE_FORMAT = '%Y-%m-%d'

    def get_dt(self, attr):
        try:
            return timezone.datetime.strptime(self.request.GET.get(attr), self.DATE_FORMAT)
        except:
            return

    def get_dates(self):
        min_dt, max_dt = self.get_dt('date_min'), self.get_dt('date_max')
        min_dt_ok, max_dt_ok = self.is_date_correct(min_dt), self.is_date_correct(max_dt)
        now = timezone.datetime.now()
        if not min_dt_ok and not max_dt_ok:
            min_dt, max_dt = now, now
        elif not min_dt_ok:
            min_dt = min(max_dt, now) if max_dt else now
        elif not max_dt_ok:
            max_dt = max(min_dt, now) if min_dt else now
        return min_dt, max_dt

    def is_date_correct(self, dt):
        try:
            if dt:
                timezone.make_aware(dt)
        except OverflowError:
            return False
        return True

    def get_datetimes(self):
        date_min, date_max = self.get_dates()
        min_dt, max_dt = None, None
        if date_min:
            min_dt = timezone.make_aware(timezone.datetime.combine(date_min, timezone.datetime.min.time()))
        if date_max:
            max_dt = timezone.make_aware(timezone.datetime.combine(date_max, timezone.datetime.min.time())) + \
                     timezone.timedelta(days=1)
        return min_dt, max_dt

    def update_context_with_search_parameters(self, ctx):
        min_dt, max_dt = self.get_dates()
        ctx.update({
            'date_min': min_dt.strftime(self.DATE_FORMAT) if min_dt else None,
            'date_min_obj': min_dt,
            'date_max': max_dt.strftime(self.DATE_FORMAT) if max_dt else None,
            'date_max_obj': max_dt,
            'search': self.request.GET.get('search') or '',
        })

    @cached_property
    def current_user_has_assistant_role(self):
        return self.request.user.has_assistant_role()

    @cached_property
    def current_mode_is_assistant(self):
        """
        просматривает ли пользователь страницу в режиме ассистента
        """
        if self.current_user_has_assistant_role:
            return self.request.COOKIES.get(VIEW_MODE_COOKIE_NAME) != 'as_user'
        return False

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update({
            'is_assistant': self.current_mode_is_assistant,
            'has_assistant_role': self.current_user_has_assistant_role,
        })
        return data


class IndexPageEventsFilterMixin(SearchHelperMixin):
    @cached_property
    def activity_filter(self):
        try:
            return Activity.objects.get(id=self.request.GET.get('activity'))
        except (ValueError, TypeError, Activity.DoesNotExist):
            return

    def filter_search(self, qs):
        text = self.request.GET.get('search')
        if text:
            return qs.filter(Q(title__icontains=text) | Q(activity__authors__title__icontains=text)).distinct()
        return qs

    def get_events(self):
        if self.current_mode_is_assistant:
            events = Event.objects.filter(is_active=True)
        else:
            events = Event.objects.filter(
                Q(id__in=EventEntry.objects.filter(user=self.request.user).values_list('event_id', flat=True)) |
                Q(run_id__in=RunEnrollment.objects.filter(user=self.request.user).values_list('run_id', flat=True)))
        events = events.filter(Q(event_type_id__in=get_allowed_event_type_ids()) | Q(event_type__isnull=True))
        min_dt, max_dt = self.get_datetimes()
        if min_dt:
            events = events.filter(dt_start__gte=min_dt)
        if max_dt:
            events = events.filter(dt_start__lt=max_dt)
        if self.activity_filter:
            events = events.filter(activity=self.activity_filter)
        events = self.filter_search(events)
        events = events.order_by('{}dt_start'.format('' if self.is_asc_sort() else '-'))
        if self.current_mode_is_assistant:
            if self.request.user.chosen_context_id and \
                    self.request.user.is_assistant_for_context(self.request.user.chosen_context):
                events = events.filter(context_id=self.request.user.chosen_context_id)
            else:
                events = events.filter(context__uuid__in=UserAvailableContexts.get(self.request.user) or [])
        return events

    def is_asc_sort(self):
        return self.request.GET.get('sort') != 'desc'


@method_decorator(login_required, name='dispatch')
class Events(IndexPageEventsFilterMixin, ListView):
    """
    все эвенты (доступные пользователю)
    """
    template_name = 'events.html'
    paginate_by = settings.PAGINATE_EVENTS_BY

    def get_queryset(self):
        return self.get_events()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        objects = ctx['object_list']
        ctx.update({
            'objects': objects,
            'sort_asc': self.is_asc_sort(),
            'activity_filter': self.activity_filter,
        })
        self.update_context_with_search_parameters(ctx)
        event_ids = [i.id for i in objects]
        context_ids = list(set([i.context_id for i in objects if i.context_id]))
        if self.current_mode_is_assistant:
            fdict = {
                'loaded_by_assistant': True,
            }
            ctx.update({
                'elements_cnt': EventMaterial.objects.filter(event_id__in=event_ids).count() +
                                EventTeamMaterial.objects.filter(event_id__in=event_ids).count() +
                                EventOnlyMaterial.objects.filter(event_id__in=event_ids).count(),
                'elements_user_cnt': EventMaterial.objects.exclude(initiator__isnull=True).exclude(**fdict).filter(event_id__in=event_ids).count() +
                                     EventTeamMaterial.objects.exclude(initiator__isnull=True).exclude(**fdict).filter(event_id__in=event_ids).count(),
            })
            run_enrs = Event.objects.filter(id__in=event_ids, run__runenrollment__isnull=False)\
                .values_list('id', 'run__runenrollment__user_id')
            event_enrs = EventEntry.objects.filter(event_id__in=event_ids).values_list('event_id', 'user_id')
            enrs = event_enrs.union(run_enrs)
            enrollments = defaultdict(int)
            for event_id, _ in enrs.iterator():
                enrollments[event_id] += 1
            check_ins = dict(EventEntry.objects.filter(is_active=True).values_list('event_id')
                             .annotate(cnt=Count('user_id')))
            event_files_cnt = defaultdict(int)
            for model in (EventMaterial, EventTeamMaterial, EventOnlyMaterial):
                qs = model.objects.filter(event_id__in=event_ids, event__is_active=True). \
                    values_list('event_id').annotate(cnt=Count('id'))
                for eid, num in qs.iterator():
                    event_files_cnt[eid] += num
            for obj in objects:
                obj.prop_enrollments = enrollments.get(obj.id, 0)
                obj.prop_checkins = check_ins.get(obj.id, 0)
                obj.trace_cnt = event_files_cnt.get(obj.id, 0)
        else:
            user_materials_num = dict(EventMaterial.objects.filter(event_id__in=event_ids, user=self.request.user)
                                      .values_list('event_id').annotate(cnt=Count('user_id')))
            teams = Team.objects.filter(
                Q(system=Team.SYSTEM_UPLOADS, event_id__in=event_ids) |
                Q(system=Team.SYSTEM_PT, contexts__id__in=context_ids)
            ).filter(users=self.request.user).values_list('id', flat=True)
            team_materials_num = dict(EventTeamMaterial.objects.filter(event_id__in=event_ids, team_id__in=teams)
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


class GetEventMixin:
    @cached_property
    def event(self):
        return get_object_or_404(Event, uid=self.kwargs['uid'])

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    @cached_property
    def current_user_is_assistant(self):
        return self.request.user.is_assistant_for_context(self.event.context)

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data['is_assistant'] = self.current_user_is_assistant
        return data


class GetEventMixinWithAccessCheck(GetEventMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseRedirect('{}?next={}'.format(
                reverse('social:begin', kwargs={'backend': 'unti'}), request.get_full_path()
            ))
        if self.current_user_is_assistant or EventEntry.objects.filter(user=request.user, event=self.event).exists() \
                or (self.event.run_id and RunEnrollment.objects.filter(user=request.user, run_id=self.event.run_id)):
            return super().dispatch(request, *args, **kwargs)
        return render(request, 'to_xle.html', {
            'link': getattr(settings, 'XLE_URL', 'https://xle.2035.university/feedback'),
            'event': self.event,
        })


@method_decorator(context_setter, name='get')
class EventView(GetEventMixin, TemplateView):
    """
    Страница мероприятия
    """
    template_name = 'event_view.html'

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        users = list(self.event.get_participants())
        user_entry = [i for i in users if i.id == self.request.user.id]
        if user_entry:
            users = user_entry + [i for i in users if i.id != self.request.user.id]
        check_ins = set(EventEntry.objects.filter(event=self.event, is_active=True).values_list('user_id', flat=True))
        attends = set(Attendance.objects.filter(event=self.event, is_confirmed=True).values_list('user_id', flat=True))
        chat_bot_added = set(Attendance.objects.filter(event=self.event, confirmed_by_system=Attendance.SYSTEM_CHAT_BOT)
                             .values_list('user_id', flat=True))
        if not self.current_user_is_assistant:
            num = dict(EventMaterial.objects.filter(event=self.event, user__in=users, is_public=True).
                       values_list('user_id').annotate(num=Count('event_id')))
            num[self.request.user.id] = EventMaterial.objects.filter(event=self.event, user=self.request.user).count()
        else:
            num = dict(EventMaterial.objects.filter(event=self.event, user__in=users).
                       values_list('user_id').annotate(num=Count('event_id')))
        can_delete = set(EventEntry.objects.filter(
            Q(added_by_assistant=True) | Q(self_enrolled=True), event=self.event).values_list('user_id', flat=True))
        for u in users:
            u.materials_num = num.get(u.id, 0)
            u.checked_in = u.id in check_ins
            u.attend = u.id in attends
            u.can_delete = u.id in can_delete
            u.added_by_chat_bot = u.id in chat_bot_added
        event_entry = EventEntry.objects.filter(event=self.event, user=self.request.user).first()
        teams = list(Team.objects.filter(event=self.event).select_related('creator').prefetch_related('users')) + \
            list(self.event.get_pt_teams(user_ids=[i.id for i in users]))
        user_teams = [
            i.id for i in teams if self.request.user in
                i.get_members_for_event(self.event, user_ids=[i.id for i in users])
        ]
        teams = sorted(list(teams), key=lambda x: (int(x.id not in user_teams), x.name.lower()))
        for team in teams:
            team.traces_number = team.get_traces_number_for_event(self.event)
        teams_allowed_to_delete = [i.id for i in teams if i.user_can_delete_team(self.request.user)]
        data.update({
            'students': users,
            'event': self.event,
            'teams': teams,
            'user_teams': user_teams,
            'event_entry': event_entry,
            'event_entry_id': getattr(event_entry, 'id', 0),
            'teams_allowed_to_delete': teams_allowed_to_delete,
        })
        return data


@method_decorator(context_setter, name='get')
class BaseLoadMaterials(TemplateView):
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
            'unattached_files': self.get_unattached_files()
        })
        return data

    def get_unattached_files(self):
        return []

    def can_upload(self):
        return self.current_user_is_assistant

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
        if not self.event.is_active:
            return JsonResponse({'error': 'Мероприятие недоступно для оцифровки'}, status=403)
        if not self.can_upload():
            return JsonResponse({}, status=403)

    def delete_item(self, request):
        material_id = request.POST.get('material_id')
        if not material_id or not material_id.isdigit():
            return JsonResponse({}, status=400)
        result_value = self._get_result_value(request)
        if not result_value:
            return JsonResponse({}, status=400)
        return self._delete_item(result_value, material_id)

    def get_result_key_and_value(self, request):
        return self._get_result_key(), self._get_result_value(request)

    def _get_result_key(self):
        return 'trace'

    def _get_result_value(self, request):
        return Trace.objects.filter(id=request.POST['trace_name']).first()

    def add_item(self, request, block_upload=False):
        result_key, result_value = self.get_result_key_and_value(request)
        if not result_value:
            return JsonResponse({}, status=400)
        data = self.get_material_fields(request)
        data[result_key] = result_value
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
        self.update_add_item_response(resp, material, result_value)
        if self.extra_context and self.extra_context.get('team_upload'):
            resp['uploader_name'] = request.user.fio
        return JsonResponse(resp)

    def update_add_item_response(self, resp, material, trace):
        pass

    def get_material_fields(self, request):
        return {}

    def make_file_path(self, fn):
        return fn

    def set_initiator_users_to_qs(self, qs):
        users = {i.unti_id: i for i in User.objects.filter(unti_id__in=filter(None, [j.initiator for j in qs]))}
        for item in qs:
            item.initiator_user = users.get(item.initiator)


class BaseLoadMaterialsWithAccessCheck(GetEventMixinWithAccessCheck, BaseLoadMaterials):
    pass


class BaseLoadMaterialsLabsResults:
    """
    Базовый класс для вьюх загрузки результатов в привязке к лабсовским результатам
    """
    results_model = LabsUserResult
    lookup_attr = 'user'
    legacy_results_model = UserResult

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        blocks = self.event.blocks.prefetch_related('results', 'results__circle_items')
        structure = [
            {
                'title': block.title,
                'deleted': block.deleted,
                'results': [
                    {
                        'id': result.id,
                        'deleted': result.deleted,
                        'title': 'Результат {}.{}'.format(i, j)
                    } for j, result in enumerate(block.results.all(), 1) if self.is_according_result_type(result)
                ]
            } for i, block in enumerate(blocks, 1) if self.block_has_available_results(block)
        ]
        qs_results = self.results_model.objects.filter(**self._update_query_dict({
            'result__block__event_id': self.event.id
        })).order_by('-id')
        qs_materials = self.material_model.objects.filter(**self._update_query_dict({
            'event': self.event,
            'result_v2__isnull': False
        })).order_by('-id')
        materials = defaultdict(list)
        for m in qs_materials:
            materials[m.result_v2_id].append(m)
        item_results = defaultdict(list)
        for item in qs_results:
            item.links = materials.get(item.id, [])
            if item.links:
                item_results[item.result_id].append(item)
        for block in blocks:
            for result in block.results.all():
                result.results = item_results.get(result.id, [])
        traces = data['traces']
        links = functools.reduce(lambda x, y: x + y, [i.get('links', []) for i in traces], [])
        data.update(self._update_query_dict({
            'blocks': blocks,
            'old_results': self.get_old_results(),
            'links': links,
            'blocks_structure_json': json.dumps(structure, ensure_ascii=False),
            'event_members': list(EventEntry.objects.filter(event=self.event).values_list('user_id', flat=True)) +
                             list(RunEnrollment.objects.filter(run_id=self.event.run_id)
                                  .values_list('user_id', flat=True)),
        }))
        return data

    def get_unattached_files(self):
        return self.material_model.objects.filter(**self._update_query_dict({
            'event': self.event,
            'result_v2__isnull': True,
            'result__isnull': True,
            'trace__isnull': True,
        }))

    def _update_query_dict(self, d):
        """
        т.к. у базовых классов есть cached_property user или team, которое одновременно является
        параметром фильтрации для персональных файлов/результатов и командных файлов/результатов соответственно,
        то этот метод добавляет нужный параметр в словарь для фильтрации/создания объектов
        """
        d.update({self.lookup_attr: getattr(self, self.lookup_attr)})
        return d

    def get_old_results(self):
        """
        получение старых результатов legacy_results_model если такие есть
        """
        results = self.legacy_results_model.objects.filter(**self._update_query_dict({
            'event': self.event,
        })).order_by('id')
        if not results:
            return []
        data = defaultdict(list)
        for item in self.material_model.objects.filter(**self._update_query_dict({'result__isnull': False})):
            data[item.result_id].append(item)
        res = []
        for result in results:
            res.append({'result': result, 'links': data.get(result.id, [])})
        return res

    def post(self, request, *args, **kwargs):
        if request.POST.get('action') == 'edit_comment':
            # действие доступно для всех, кто может заходить на страницу
            return self.action_edit_comment(request)
        resp = self.check_post_allowed(request)
        if resp is not None:
            return resp
        result_id_error, result_deleted, type_ok = self._check_labs_result_id(request)
        allowed_actions = ['delete_all', 'init_result', 'move', 'move_unattached', 'approve_result',
                           'change_circle_items']
        if 'add_btn' in request.POST:
            if result_id_error is not None or result_deleted or not type_ok:
                return result_id_error
            return self.add_item(request)
        elif 'action' in request.POST and request.POST['action'] in allowed_actions:
            if request.POST['action'] != 'move_unattached' and result_id_error is not None:
                return result_id_error
            if request.POST['action'] == 'delete_all':
                return self.action_delete_all(request)
            elif request.POST['action'] == 'init_result':
                if result_deleted or not type_ok:
                    return JsonResponse({}, status=400)
                return self.action_init_result(request)
            elif request.POST['action'] == 'move':
                return self.action_move(request)
            elif request.POST['action'] == 'move_unattached':
                return self.action_move_unattached(request)
            elif request.POST['action'] == 'approve_result':
                return self.action_approve_result(request)
            elif request.POST['action'] == 'change_circle_items':
                return self.action_change_circle_items(request)
        return self.delete_item(request)

    def action_approve_result(self, request):
        if not self.current_user_is_assistant:
            raise PermissionDenied
        result_id = request.POST.get('labs_result_id') or ''
        result_item_id = request.POST.get('result_item_id') or ''
        approve_text = request.POST.get('approve_text') or ''
        approved = {'true': True, 'false': False}.get(request.POST.get('approved'))
        if result_id.isdigit() and result_item_id.isdigit() and isinstance(approved, bool):
            result = self.get_result_for_request(request)
            if not result or result.result.block.event_id != self.event.id:
                return JsonResponse({}, status=404)
            result.approve_text = approve_text
            result.approved = approved
            result.save(update_fields=['approve_text', 'approved'])
            if self.should_send_to_kafka(result):
                send_object_info(result, result.id, KafkaActions.UPDATE,
                                 additional_data={'what': ResultUpdateType.SET_VALIDATION})
            logging.info('User %s set approved to %s, comment: %s for result #%s' %
                         (request.user.username, result.approved, result.approve_text, result_id))
            return JsonResponse({'approved': result.approved, 'approve_text': result.approve_text, 'id': result.id})
        return JsonResponse({}, status=400)

    def action_change_circle_items(self, request):
        result_id = request.POST.get('labs_result_id') or ''
        result_item_id = request.POST.get('result_item_id') or ''
        selected_circle_items = request.POST.get('circle_items') or ''
        try:
            selected_circle_items = [int(i) for i in selected_circle_items.split(',')] if selected_circle_items else []
        except (ValueError, TypeError, AttributeError):
            return JsonResponse({}, status=400)
        if result_id.isdigit() and result_item_id.isdigit():
            result = self.get_result_for_request(request)
            if not result or result.result.block.event_id != self.event.id:
                return JsonResponse({}, status=404)
            result.circle_items.set([i for i in result.result.available_circle_items if i.id in selected_circle_items])
            if self.should_send_to_kafka(result):
                send_object_info(result, result.id, KafkaActions.UPDATE,
                                 additional_data={'what': ResultUpdateType.EDIT_TOOLS})
            logging.info('User %s updated circle items for result #%s, circle items ids: %s' %
                         (request.user.username, result_id, [i.id for i in result.circle_items.all()]))
            return JsonResponse({'selected_items': [i.id for i in result.circle_items.all()]})
        return JsonResponse({}, status=400)

    def action_edit_comment(self, request):
        result_id = request.POST.get('labs_result_id') or ''
        result_item_id = request.POST.get('result_item_id') or ''
        comment = request.POST.get('comment')
        if result_id.isdigit() and result_item_id.isdigit() and comment is not None:
            result = self.get_result_for_request(request)
            if not result:
                return JsonResponse({}, status=404)
            result.comment = comment
            result.save(update_fields=['comment'])
            if self.should_send_to_kafka(result):
                send_object_info(result, result.id, KafkaActions.UPDATE,
                                 additional_data={'what': ResultUpdateType.EDIT_COMMENT})
            logging.info('User %s has updated comment for result #%s: %s' %
                (request.user.username, result_id, comment))
            return JsonResponse({})
        return JsonResponse({}, status=400)

    def action_move(self, request):
        """
        перемещение объекта результата из одного блока результата в другой
        """
        if not self.current_user_is_assistant:
            raise PermissionDenied
        item_result = self.results_model.objects.filter(**self._update_query_dict({
            'result_id': request.POST.get('labs_result_id'),
            'id': request.POST.get('result_item_id'),
        })).first()
        if not item_result:
            return JsonResponse({}, status=400)
        old_result_id = item_result.result.id
        try:
            assert item_result.result.block.event_id == self.event.id
            move_to = LabsEventResult.objects.select_related('block').get(id=request.POST.get('move_to'))
            assert move_to.block.event_id == self.event.id and not move_to.deleted and not move_to.block.deleted
            assert self.is_according_result_type(move_to)
        except (AssertionError, LabsEventResult.DoesNotExist, TypeError, ValueError):
            return JsonResponse({}, status=400)
        item_result.result = move_to
        item_result.save(update_fields=['result'])
        logging.info('User %s moved result %s from LabsEventResult %s to %s' %
                     (self.request.user.email, item_result.id, old_result_id, move_to.id))
        if self.should_send_to_kafka(item_result):
            send_object_info(item_result, item_result.id, KafkaActions.UPDATE,
                             additional_data={'what': ResultUpdateType.BLOCK_CHANGED})
        return JsonResponse({'new_result_id': move_to.id})

    def action_move_unattached(self, request):
        """
        перемещение файла, у которого нет связей с трейсом или результатом, в результат
        """
        if not self.current_user_is_assistant:
            raise PermissionDenied
        try:
            material = self.material_model.objects.get(**self._update_query_dict({
                'event': self.event,
                'id': request.POST.get('material_id'),
                'trace__isnull': True,
                'result__isnull': True,
                'result_v2__isnull': True,
            }))
        except (self.material_model.DoesNotExist, ValueError, TypeError):
            return JsonResponse({}, status=400)
        try:
            result = LabsEventResult.objects.get(
                block__event_id=self.event.id,
                id=request.POST.get('move_to')
            )
            assert not result.deleted and not result.block.deleted
            assert self.is_according_result_type(result)
        except (AssertionError, self.material_model.DoesNotExist, ValueError, TypeError):
            return JsonResponse({}, status=400)
        item_result = self.results_model.objects.create(**self._update_query_dict({
            'result': result,
        }))
        if self.should_send_to_kafka(item_result):
            send_object_info(item_result, item_result.id, KafkaActions.CREATE)
        material.result_v2 = item_result
        material.save(update_fields=['result_v2'])
        if self.should_send_to_kafka(item_result):
            send_object_info(item_result, item_result.id, KafkaActions.UPDATE,
                             additional_data={'what': ResultUpdateType.ADD_FILE})
        logging.info('User %s created result %s from unattached file %s' %
                     (request.user.email, item_result.id, material.id))
        return JsonResponse({
            'material_id': material.id,
            'url': material.get_url(),
            'name': material.get_name(),
            'comment': '',
            'is_public': getattr(material, 'is_public', True),
            'data_attrs': material.render_metadata(),
            'can_set_public': self._can_set_public(),
            'item_result_id': item_result.id,
            'result_id': result.id,
            'result_url': item_result.get_page_url(),
        })

    def action_init_result(self, request):
        """
        создание результата, в который будут загружаться файлы
        """
        item = self.results_model.objects.create(**self._update_query_dict({
            'result_id': request.POST.get('labs_result_id'),
            'comment': request.POST.get('comment') or '',
        }))
        circle_items = request.POST.get('circle_items') or ''
        circle_items = circle_items.split(',')
        circle_items_ids = []
        for cid in circle_items:
            try:
                circle_items_ids.append(int(cid))
            except (ValueError, TypeError):
                pass
        item.circle_items.set(CircleItem.objects.filter(id__in=circle_items_ids, result_id=item.result_id))
        if self.should_send_to_kafka(item):
            send_object_info(item, item.id, KafkaActions.CREATE)
        return JsonResponse({'result_id': item.id})

    def action_delete_all(self, request):
        if not request.POST.get('result_item_id'):
            return JsonResponse({}, status=400)
        result = self.results_model.objects.filter(**self._update_query_dict({
            'result_id': request.POST.get('labs_result_id'),
            'id': request.POST.get('result_item_id'),
        })).first()
        if not result:
            return JsonResponse({}, status=400)
        materials = self.material_model.objects.filter(**self._update_query_dict({
            'event': self.event,
            'result_v2': result
        }))
        try:
            result_id = result.id
            should_send = self.should_send_to_kafka(result)
            with transaction.atomic():
                materials.delete()
                result.delete()
            if should_send:
                send_object_info(result, result_id, KafkaActions.DELETE)
        except Exception:
            logging.exception('Failed to delete result %s for user %s' % (result.id, result.user.username))
            return JsonResponse({}, status=500)
        logging.warning('User %s deleted all result files for %s %s result #%s' %
                        (request.user.username, self.lookup_attr, getattr(self, self.lookup_attr).id,
                         request.POST.get('labs_result_id')))
        return JsonResponse({})

    def delete_item(self, request):
        material_id = request.POST.get('material_id')
        if not material_id or not material_id.isdigit():
            return JsonResponse({}, status=400)
        if 'labs_result_id' in request.POST:
            result_value = self.get_result_for_request(request)
            if not result_value:
                return JsonResponse({}, status=400)
            return self._delete_item(result_value, material_id)
        # обработка удаления старых файлов, не привязанных к результатам из лабс
        material = self.material_model.objects.filter(**self._update_query_dict({
            'event': self.event,
            'result_v2__isnull': True,
            'id': request.POST.get('material_id', 0),
        })).first()
        if not material:
            return JsonResponse({}, status=400)
        logging.warning('User %s deleted old file %s for %s %s' %
                        (request.user.username, material.get_url(), self.lookup_attr, getattr(self, self.lookup_attr)))
        material.delete()
        return JsonResponse({})

    def _check_labs_result_id(self, request):
        try:
            result_id = int(request.POST.get('labs_result_id'))
        except (ValueError, TypeError):
            return JsonResponse({}, status=400), None, None
        result = LabsEventResult.objects.filter(id=result_id, block__event_id=self.event.id).\
            select_related('block').first()
        if not result_id or not result:
            return JsonResponse({}, status=400), None, None
        return None, result.deleted or result.block.deleted, self.is_according_result_type(result)

    def is_according_result_type(self, result):
        """
        проверка того, что формат результата соответствует типу загрузки
        """
        return True

    def block_has_available_results(self, block):
        """
        проверка того, что в блоке есть результаты нужного формата
        """
        return True

    def _get_result_key(self):
        return 'result_v2'

    def _get_result_value(self, request):
        return self.get_result_for_request(request)

    def update_add_item_response(self, resp, material, trace):
        resp['comment'] = trace.comment
        resp['result_url'] = trace.get_page_url()
        resp['circle_items'] = [{'id': i.id, 'tool': i.tool} for i in trace.result.available_circle_items]
        resp['selected_circle_items'] = list(trace.circle_items.values_list('id', flat=True))
        # отправка сообщения об изменении результата
        if self.should_send_to_kafka(trace):
            send_object_info(trace, trace.id, KafkaActions.UPDATE,
                             additional_data={'what': ResultUpdateType.ADD_FILE})

    def _delete_item(self, trace, material_id):
        result_id = trace.id
        material = self.material_model.objects.filter(**self._update_query_dict({
            'event': self.event,
            'id': material_id,
            'result_v2': trace,
        })).first()
        if not material:
            return JsonResponse({}, status=400)
        material.delete()
        self._log_material_delete(material)
        # удаление связи пользователя/команды с результатом, если у пользователя/команды больше нет файлов
        # с привязкой к этому результату
        should_send = self.should_send_to_kafka(trace)
        additional_data = None
        if not self.material_model.objects.filter(
                **self._update_query_dict({'result_v2': trace, 'event': self.event})).exists():
            trace.delete()
            action = KafkaActions.DELETE
        else:
            action = KafkaActions.UPDATE
            additional_data = {'what': ResultUpdateType.DELETE_FILE}
        if should_send:
            send_object_info(trace, result_id, action, additional_data=additional_data)
        return JsonResponse({})

    def _log_material_delete(self, material):
        pass

    def get_result_for_request(self, request):
        return self.results_model.objects.filter(**self._update_query_dict({
            'result_id': request.POST.get('labs_result_id'),
            'id': request.POST.get('result_item_id')
        })).first()

    def should_send_to_kafka(self, result):
        """
        проверка того, что для соответствующего результата блока заданы ячейки
        """
        return bool(result.result.circle_items.exists())


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
        if not self.current_user_is_assistant:
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

    def _get_result_key(self):
        return 'result'

    def _get_result_value(self, request):
        return self.get_result_for_request(request)

    def check_event_has_result(self, result_id):
        pass

    def delete_item(self, request):
        material_id = request.POST.get('material_id')
        if not material_id or not material_id.isdigit():
            return JsonResponse({}, status=400)
        return self._delete_item(material_id)


class LoadMaterials(BaseLoadMaterialsWithAccessCheck):
    """
    Просмотр/загрузка материалов по эвенту
    """
    material_model = EventMaterial
    extra_context = {'with_public_checkbox': True, 'user_upload': True}

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update({'other_materials': self.user.connected_materials.order_by('id')})
        return data

    def _can_set_public(self):
        return self.request.user.unti_id == int(self.kwargs['unti_id'])

    def can_upload(self):
        return self.current_user_is_assistant or int(self.kwargs['unti_id']) == self.request.user.unti_id

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
        if not (EventEntry.objects.filter(event=self.event, user=self.user).exists() or (self.event.run_id and
                RunEnrollment.objects.filter(run_id=self.event.run_id, user=self.user).exists())):
            return JsonResponse({}, status=400)
        return super().add_item(request, **kwargs)

    def get_material_fields(self, request):
        public = self._can_set_public() and request.POST.get('is_public') in ['on']
        return dict(event=self.event, user=self.user, is_public=public,
                    comment=request.POST.get('comment', ''))

    def make_file_path(self, fn):
        return os.path.join(self.event.uid, str(self.user.unti_id), fn)


class LoadUserMaterialsResult(BaseLoadMaterialsLabsResults, LoadMaterials):
    template_name = 'personal_results.html'
    material_model = EventMaterial
    extra_context = {'user_upload': True}

    def get_material_fields(self, request):
        return dict(event=self.event, user=self.user, is_public=True,
                    loaded_by_assistant=self.current_user_is_assistant)

    def _log_material_delete(self, material):
        logging.warning('User %s has deleted file %s for user %s' %
                        (self.request.user.username, material.get_url(), self.user.username))

    def is_according_result_type(self, result):
        return result.is_personal()

    def block_has_available_results(self, block):
        return not block.block_has_only_group_results()


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


class LoadTeamMaterials(BaseLoadMaterialsWithAccessCheck):
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
                     'event_participants': list(self.event.get_participant_ids()),
                     'team': self.team, 'other_materials': self.team.connected_materials.order_by('id')})
        return data

    @cached_property
    def team(self):
        return get_object_or_404(Team, id=self.kwargs['team_id'])

    def get_materials(self):
        qs = EventTeamMaterial.objects.filter(event=self.event, team=self.team).prefetch_related('owners')
        users = {i.unti_id: i for i in User.objects.filter(unti_id__in=filter(None, [j.initiator for j in qs]))}
        for item in qs:
            item.initiator_user = users.get(item.initiator)
            if not self.current_user_is_assistant:
                item.is_owner = self.request.user in item.owners.all()
                item.ownership_url = reverse('team-material-owner', kwargs={
                    'uid': self.event.uid, 'material_id': item.id, 'team_id': self.team.id})
        return qs

    def can_upload(self):
        # командные файлы загружает ассистент или участники этой команды
        return self.current_user_is_assistant or self.team.users.filter(id=self.request.user.id).exists()

    def post(self, request, *args, **kwargs):
        # загрузка и удаление файлов доступны только для эвентов, доступных для оцифровки, и по
        # командам, сформированным в данном эвенте
        if not self.event.is_active or not (self.current_user_is_assistant or
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
                Team.objects.filter(Q(event=self.event, id=self.kwargs['team_id'], system=Team.SYSTEM_UPLOADS) |
                                    (Q(system=Team.SYSTEM_PT, contexts=self.event.context, id=self.kwargs['team_id']))
                                    ).exists():
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
                    confirmed=self.current_user_is_assistant)


class LoadTeamMaterialsResult(BaseLoadMaterialsLabsResults, LoadTeamMaterials):
    results_model = LabsTeamResult
    legacy_results_model = TeamResult
    lookup_attr = 'team'
    template_name = 'team_results.html'

    def get_material_fields(self, request):
        return dict(event=self.event, team=self.team, loaded_by_assistant=self.current_user_is_assistant)

    def _log_material_delete(self, material):
        logging.warning('User %s has deleted file %s for team %s' %
                        (self.request.user.username, material.get_url(), self.team.id))

    def is_according_result_type(self, result):
        return result.is_group()

    def block_has_available_results(self, block):
        return not block.block_has_only_personal_results()


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


class LoadEventMaterials(GetEventMixin, BaseLoadMaterials):
    """
    Загрузка материалов мероприятия
    """
    material_model = EventOnlyMaterial
    extra_context = {'with_comment_input': True, 'show_owners': True, 'event_upload': True}

    def post(self, request, *args, **kwargs):
        if request.user.is_authenticated and self.current_user_is_assistant and 'change_material_info' in request.POST:
            return self.change_material_info(request)
        return super().post(request, *args, **kwargs)

    def change_material_info(self, request):
        result_key, result_value = self.get_result_key_and_value(request)
        if not result_value:
            return JsonResponse({}, status=400)
        try:
            material = self.material_model.objects.get(id=request.POST.get('material_id'), event=self.event)
            original_trace_id = material.trace_id
        except (self.material_model.DoesNotExist, ValueError, TypeError):
            return JsonResponse({}, status=400)
        comment = request.POST.get('comment') or ''
        material.trace = result_value
        material.comment = comment
        material.save(update_fields=['comment', 'trace'])
        logging.info('User %s updated material %s. Trace_id: %s, comment: %s' %
                     (request.user.username, material.id, result_value.id, comment))
        return JsonResponse({
            'comment': comment,
            'trace_id': result_value.id,
            'info_str': material.get_info_string(),
            'original_trace_id': original_trace_id,
            'material_id': material.id,
        })

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update({
            'event_users': self.event.get_participants(),
            'event_teams': Team.objects.filter(event=self.event).order_by('name'),
            'blocks_form': EventMaterialForm(event=self.event),
        })
        return data

    def can_upload(self):
        """
        любой пользователь может грузить материалы мероприятия
        """
        return True

    def get_unattached_files(self):
        return self.material_model.objects.filter(event=self.event, trace__isnull=True)

    def get_materials(self):
        qs = EventOnlyMaterial.objects.filter(event=self.event)
        for item in qs:
            if not self.current_user_is_assistant:
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
        if not (self.request.user.unti_id and self.request.user.unti_id == material.initiator or
                self.current_user_is_assistant):
            return JsonResponse({}, status=400)
        if self.event.uid == getattr(settings, 'API_DATA_EVENT', ''):
            ApiUserChart.objects.update(updated=None)
        material.delete()
        logging.warning('User %s has deleted file %s for event %s' %
                        (self.request.user.username, material.get_url(), self.event.uid))
        return JsonResponse({})

    def make_file_path(self, fn):
        return os.path.join(self.event.uid, fn)

    def get_material_fields(self, request):
        return dict(event=self.event, comment=request.POST.get('comment', ''))

    def update_add_item_response(self, resp, material, trace):
        if not isinstance(trace, Trace):
            return
        form = EventMaterialForm(instance=material, data=self.request.POST, prefix=str(trace.id), event=self.event)
        if form.is_valid():
            material = form.save()
        resp['trace_id'] = trace.id
        resp['info_string'] = material.get_info_string()
        logging.info('User %s created block info for material %s: %s' %
                     (self.request.user.username, material.id, resp['info_string']))


class BaseTeamView(GetEventMixin):
    template_name = 'create_or_edit_team.html'
    form_class = CreateTeamForm

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not (self.current_user_is_assistant or
                self.has_permission(request)):
            return HttpResponseForbidden()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update({'students': self.get_available_users(), 'event': self.event})
        return data

    def get_available_users(self):
        return self.event.get_participants()

    def post(self, request, **kwargs):
        form = self.form_class(data=request.POST, event=self.event, users_qs=self.get_available_users(),
                               creator=self.request.user, instance=self.team)
        if not form.is_valid():
            return JsonResponse({}, status=400)
        team, members_changed = form.save()
        self.team_saved(team, members_changed)
        return JsonResponse({'redirect': reverse('event-view', kwargs={'uid': self.event.uid})})

    def team_saved(self, team, members_changed):
        pass

    @cached_property
    def team(self):
        return None


class CreateTeamView(BaseTeamView, TemplateView):
    extra_context = {'edit': False}

    def has_permission(self, request):
        return EventEntry.objects.filter(event=self.event, user=request.user).exists() or (self.event.run_id and
               RunEnrollment.objects.filter(run_id=self.event.run_id, user=request.user).exists())


class EditTeamView(BaseTeamView, TemplateView):
    form_class = EditTeamForm
    extra_context = {'edit': True}

    def has_permission(self, request):
        return self.team is not None and self.team.user_can_edit_team(request.user)

    @cached_property
    def team(self):
        return Team.objects.filter(id=self.kwargs['team_id']).prefetch_related('users').first()

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data['team'] = self.team
        data['students'] = sorted(list(data['students']), key=lambda x: x not in self.team.users.all())
        return data

    def team_saved(self, team, members_changed):
        if members_changed and LabsTeamResult.objects.filter(team=team).exists():
            team_members_set_changed.delay(team.id)


class AddUserToEvent(GetEventMixin, TemplateView):
    """
    Добавить пользователя на мероприятие вручную
    """
    template_name = 'add_user.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and self.current_user_is_assistant:
            return super().dispatch(request, *args, **kwargs)
        return HttpResponseForbidden()

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update({'event': self.event, 'form': AddUserForm(event=self.event)})
        return data

    def post(self, request, uid=None):
        form = AddUserForm(data=request.POST, event=self.event)
        if form.is_valid():
            users = form.cleaned_data['users']
            for user in users:
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
            logging.info('User %s added users %s to event %s' % (
                request.user.username,
                ', '.join(map(str, users.values_list('unti_id', flat=True))),
                self.event.id))
            return redirect('event-view', uid=self.event.uid)
        else:
            return render(request, self.template_name, {'event': self.event, 'form': form})


class RemoveUserFromEvent(GetEventMixin, View):
    def post(self, request, uid=None):
        if not request.user.is_authenticated or not self.current_user_is_assistant:
            return JsonResponse({}, status=403)
        user_id = request.POST.get('user_id')
        try:
            entry = EventEntry.objects.get(event=self.event, user_id=user_id)
            assert entry.added_by_assistant or entry.self_enrolled
        except (AssertionError, TypeError, ValueError, EventEntry.DoesNotExist):
            return JsonResponse({}, status=404)
        if not request.POST.get('confirm'):
            has_results = EventMaterial.objects.filter(user_id=user_id, event=self.event).exists() or \
                          EventTeamMaterial.objects.filter(event=self.event, team__users__id=user_id).exists()
            return JsonResponse({'can_delete': True, 'has_results': has_results, 'user_id': user_id})
        EventEntry.objects.filter(event=self.event, user_id=request.POST.get('user_id')).update(deleted=True)
        Attendance.objects.filter(event=self.event, user_id=request.POST.get('user_id')).delete()
        logging.warning('User %s removed user %s from event %s' %
                        (request.user.username, entry.user.username, entry.event.uid))
        return JsonResponse({})


class UserAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        event_id = self.forwarded.get('event_id')
        event = Event.objects.filter(id=event_id).first()
        run_id = event and event.run_id
        chosen = self.forwarded.get('users') or []
        if not self.request.user.is_authenticated or not self.request.user.has_assistant_role() or not event_id:
            return User.objects.none()
        q = Q(id__in=EventEntry.objects.filter(event_id=event_id).values_list('user_id', flat=True))
        if run_id:
            q |= Q(id__in=RunEnrollment.objects.filter(run_id=run_id).values_list('user_id', flat=True))
        qs = User.objects.exclude(q).filter(
            id__in=UserSocialAuth.objects.all().values_list('user__id', flat=True)).exclude(id__in=chosen)
        if self.q:
            qs = self.search_user(qs, self.q)
        return qs

    @staticmethod
    def search_user(qs, query):
        def make_q(val):
            str_args = ['email__icontains', 'username__icontains', 'first_name__icontains', 'last_name__icontains',
                        'leader_id']
            int_args = ['unti_id']
            q = [Q(**{i: val}) for i in str_args]
            if val.isdigit():
                q.extend([Q(**{i: val}) for i in int_args])
            return functools.reduce(lambda x, y: x | y, q)

        if query.strip():
            q_parts = list(filter(None, query.split()))
            if len(q_parts) > 1:
                return qs.filter(functools.reduce(lambda x, y: x & y, map(make_q, q_parts)))
            return qs.filter(make_q(q_parts[0]))
        return qs

    def get_result_label(self, result):
        full_name = ' '.join(filter(None, [result.last_name, result.first_name, result.second_name]))
        return '%s, (%s)' % (full_name, result.leader_id)


class ResultTypeAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return []
        try:
            event = Event.objects.get(id=self.forwarded.get('event'))
        except (TypeError, ValueError, Event.DoesNotExist):
            logging.warning("User %s hasn't provided event parameter for ResultTypeAutocomplete")
            raise SuspiciousOperation
        if not self.request.user.is_assistant_for_context(event.context):
            return []
        return BlockType.result_types_for_event(event)

    def get_result_label(self, result):
        return result[1]

    def get_result_value(self, result):
        return result[0]


class EventItemAutocompleteBase(autocomplete.Select2QuerySetView):
    model = None

    def get_queryset(self):
        exclude = self.forwarded.get('exclude') or []
        event_id = str(self.forwarded.get('event'))
        event = Event.objects.get(id=event_id)
        if not event_id.isdigit() or not (self.request.user.is_authenticated and self.request.user.is_assistant_for_context(event.context)):
            return self.model.objects.none()
        return self.model.objects.filter(**self.get_filters(event_id)).exclude(id__in=exclude)

    def get_filters(self, event_id):
        return {}


class EventUserAutocomplete(EventItemAutocompleteBase):
    model = User

    def get_filters(self, event_id):
        return {'id__in': EventEntry.objects.filter(event_id=event_id).values_list('user_id', flat=True)}

    def get_queryset(self):
        return UserAutocomplete.search_user(super().get_queryset(), self.q)


class EventTeamAutocomplete(EventItemAutocompleteBase):
    model = Team

    def get_queryset(self):
        qs = super().get_queryset()
        if self.q:
            qs = qs.filter(name__icontains=self.q)
        return qs.prefetch_related('users')

    def get_filters(self, event_id):
        return {'event_id': event_id}

    def get_result_label(self, result):
        return '{} ({})'.format(result.name, ', '.join([i.last_name for i in result.users.all()]))


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
                    "event_uuid": "11111111-1111-1111-11111111", // uuid мероприятия в LABS
                    "created_on": "2018-07-15T07:14:04+10:00", // дата создания объекта
                    "updated_on": "2018-07-15T07:14:04+10:00", // дата обновления объекта
                    "is_confirmed": true, // присутствие подтверждено
                    "confirmed_by_user": 1, // id пользователя подтвердившего присутствие в UNTI SSO
                    "confirmed_by_system": "uploads", // кем подтверждено uploads или chat_bot
                },
                ...
          }

    **Пример post-запроса**

    POST /api/attendance/{
            "is_confirmed": true,
            "user_id": 1,
            "event_uuid": "11111111-1111-1111-11111111",
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
        event_id = request.data.get('event_uuid')
        confirmed_by = request.data.get('confirmed_by_user')
        if is_confirmed is None or not user_id or not event_id:
            return Response({'error': 'request should contain is_confirmed, user_id and event_id parameters'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(unti_id=user_id)
        except (User.DoesNotExist, TypeError):
            return Response({'error': 'user does not exist'}, status=status.HTTP_404_NOT_FOUND)
        try:
            event = Event.objects.get(uid=event_id)
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
        if not self.current_user_is_assistant:
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
        if not request.user.is_authenticated or not self.current_user_is_assistant:
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


class BaseOwnershipChecker(GetEventMixin, View):
    def post(self, request, **kwargs):
        if self.current_user_is_assistant or not EventEntry.objects.filter(event=self.event, user=request.user):
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
        if request.user.is_authenticated and not self.current_user_is_assistant:
            return HttpResponseForbidden()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, uid=None):
        if request.POST.get('type') == 'event':
            return self.move_to_event(request)
        if request.POST.get('type') not in ['team']:
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
        if not (EventEntry.objects.filter(event=self.event, user=user).exists() or
                (self.event.run_id and RunEnrollment.objects.filter(run_id=self.event.run_id, user=user).exists())):
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
        if model == EventMaterial and not (EventEntry.objects.filter(event=self.event, user=obj.user_id).exists() or
                                           (self.event.run_id and RunEnrollment.objects.filter(
                                               run_id=self.event.run_id, user_id=obj.user_id).exists())):
            return JsonResponse({}, status=400)
        if model == EventTeamMaterial and not Team.objects.filter(id=obj.team_id, event=self.event).exists():
            return JsonResponse({}, status=400)
        EventOnlyMaterial.copy_from_object(obj)
        logging.info('User %s transferred %s file %s to event' %
                     (request.user.username, 'user' if model == EventMaterial else 'team', obj.id))
        return JsonResponse({})


class ActivitiesFilter(SearchHelperMixin):
    def filter_search(self, qs):
        text = self.request.GET.get('search')
        if text:
            return qs.filter(Q(title__icontains=text) | Q(authors__title__icontains=text))
        return qs

    def get_activities(self):
        if not self.only_my_activities():
            qs = Activity.objects.filter(is_deleted=False)
            if self.current_mode_is_assistant:
                qs = self.filter_context(qs)
            else:
                qs = qs.filter(
                    Q(id__in=EventEntry.objects.filter(user=self.request.user)
                      .values_list('event__activity_id', flat=True)) |
                    Q(id__in=RunEnrollment.objects.filter(user=self.request.user).values_list('run__activity_id'))
                )
        else:
            qs = Activity.objects.filter(
                is_deleted=False,
                id__in=ActivityEnrollment.objects.filter(user=self.request.user).values_list('activity_id', flat=True))
        min_dt, max_dt = self.get_datetimes()
        if min_dt:
            qs = qs.filter(event__dt_start__gte=min_dt)
        if max_dt:
            qs = qs.filter(event__dt_start__lt=max_dt)
        qs = self.filter_search(qs)
        return qs.distinct().order_by('title', 'id')

    def filter_context(self, qs):
        if self.request.user.chosen_context_id:
            if self.request.user.is_assistant_for_context(self.request.user.chosen_context):
                return qs.filter(id__in=Event.objects.filter(
                    context_id=self.request.user.chosen_context_id).values_list('activity_id', flat=True)
                )
            return qs.none()
        return qs.filter(event__context__uuid__in=UserAvailableContexts.get(self.request.user) or [])

    def only_my_activities(self):
        return self.request.GET.get('activities') == 'my'


@method_decorator(login_required, name='dispatch')
class ActivitiesView(ActivitiesFilter, ListView):
    template_name = 'activities.html'
    paginate_by = settings.PAGINATE_EVENTS_BY

    def get_queryset(self):
        return self.get_activities()

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        self.update_context_with_search_parameters(data)
        activities = data['object_list']
        activity_ids = [i.id for i in activities]
        user_materials = dict(EventMaterial.objects.values_list('event__activity_id').annotate(cnt=Count('id')))
        team_materials = dict(EventTeamMaterial.objects.values_list('event__activity_id').annotate(cnt=Count('id')))
        event_materials = dict(EventOnlyMaterial.objects.values_list('event__activity_id').annotate(cnt=Count('id')))
        run_enrs = RunEnrollment.objects.filter(run__activity_id__in=activity_ids)\
            .values_list('run__activity_id', 'user_id')
        activity_enrs = EventEntry.objects.filter(event__activity_id__in=activity_ids)\
            .values_list('event__activity_id', 'user_id')
        participants = defaultdict(int)
        enrs = run_enrs.union(activity_enrs)
        for activity_id, _ in enrs.iterator():
            participants[activity_id] += 1
        check_ins = dict(EventEntry.objects.filter(deleted=False, is_active=True).values_list('event__activity_id').
                         annotate(cnt=Count('user_id')))
        activity_types = dict(Event.objects.values_list('activity_id', 'event_type__title'))
        q = Q(event__is_active=True) & \
            (Q(event__event_type_id__in=get_allowed_event_type_ids()) | Q(event__event_type__isnull=True))
        events_cnt = dict(Activity.objects.values_list('id').annotate(cnt=Count('event', filter=q)))
        for a in activities:
            a.participants_num = participants.get(a.id, 0)
            a.check_ins_num = check_ins.get(a.id, 0)
            a.materials_num = user_materials.get(a.id, 0) + team_materials.get(a.id, 0) + event_materials.get(a.id, 0)
            a.activity_type = activity_types.get(a.id)
            a.event_count = events_cnt.get(a.id, 0)
        data.update({'objects': activities, 'only_my': self.only_my_activities()})
        return data


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
        trace = self.event.get_event_structure_trace()
        materials = []
        if trace:
            materials = EventOnlyMaterial.objects.filter(event=self.event, trace=trace)
        data.update({
            'formset': EventBlockFormset(queryset=EventBlock.objects.none()),
            'event': self.event,
            'blocks': EventBlock.objects.filter(event=self.event).order_by('id'),
            'import_events': Event.objects.filter(activity_id=self.event.activity_id).exclude(id=self.event.id).
                order_by('ext_id').annotate(num_blocks=Count('eventblock')),
            'trace': trace,
            'materials': materials,
            'max_size': settings.MAXIMUM_ALLOWED_FILE_SIZE,
            'max_uploads': settings.MAX_PARALLEL_UPLOADS,
        })
        return data

    def post(self, request, **kwargs):
        formset = EventBlockFormset(request.POST)
        if formset.is_valid():
            # если происходит импорт блоков из другого мероприятия, все ранее созданные блоки удаляются
            if any(form.save(commit=False).id for form in formset.forms):
                EventBlock.objects.filter(event=self.event).delete()
            for form in formset.forms:
                b = form.save(commit=False)
                b.event = self.event
                # всегда создается новый блок
                b.id = None
                b.save()
        return redirect('create-blocks', uid=self.event.uid)


class ImportEventBlocks(GetEventMixin, TemplateView):
    template_name = 'includes/_blocks_form.html'

    def get_context_data(self, **kwargs):
        if not self.current_user_is_assistant:
            raise PermissionDenied
        try:
            event = Event.objects.get(id=self.request.GET.get('id'), activity_id=self.event.activity_id)
        except (Event.DoesNotExist, TypeError, ValueError):
            raise Http404
        return {'formset': EventBlockFormset(queryset=EventBlock.objects.filter(event=event).order_by('id'))}


class CheckEventBlocks(GetEventMixin, View):
    """
    проверка того, что для текущей структуры мероприятия нет файлов мероприятия, привязанных к блокам
    """
    def get(self, request, **kwargs):
        if self.current_user_is_assistant:
            return JsonResponse({
                'blocks_with_materials': EventOnlyMaterial.objects.filter(event_block__event=self.event).exists(),
            })
        raise PermissionDenied


class DeleteEventBlock(GetEventMixin, View):
    def get(self, request, **kwargs):
        if request.user.is_authenticated and self.current_user_is_assistant:
            block = EventBlock.objects.filter(id=kwargs['block_id']).first()
            if not block:
                raise Http404
            return JsonResponse({'has_materials': EventOnlyMaterial.objects.filter(event_block=block).exists()})
        raise PermissionDenied

    def post(self, request, **kwargs):
        if request.user.is_authenticated and self.current_user_is_assistant:
            EventBlock.objects.filter(id=kwargs['block_id']).delete()
            return JsonResponse({'redirect': reverse('create-blocks', kwargs={'uid': self.event.uid})})
        raise PermissionDenied


class BaseCreateResult(GetEventMixin, View):
    form_class = UserResultForm
    result_model = UserResult

    def post(self, request, **kwargs):
        if not self.current_user_is_assistant:
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
    template_name = 'includes/_user_roles_formset.html'

    def get_context_data(self, **kwargs):
        if not self.current_user_is_assistant:
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


class AddEventBlockToMaterial(GetEventMixin, View):
    def post(self, request, **kwargs):
        """
        изменение блока, пользователей и команд у файла мероприятия ассистентом
        """
        pref = request.POST.get('custom_form_prefix')
        if not self.current_user_is_assistant or not pref:
            raise PermissionDenied
        try:
            material = EventOnlyMaterial.objects.get(id=EventBlockEditRenderer.parse_material_id_from_prefix(pref))
        except (TypeError, EventOnlyMaterial.DoesNotExist):
            return JsonResponse({}, status=400)
        form = EventMaterialForm(instance=material, data=request.POST, prefix=pref, event=self.event)
        if not form.is_valid():
            return JsonResponse({}, status=400)
        instance = form.save()
        info_str = instance.get_info_string()
        logging.info('User %s changed block info for material %s: %s' %
                     (self.request.user.username, material.id, info_str))
        return JsonResponse({'info_string': info_str})


class EventBlockEditRenderer(GetEventMixin, TemplateView):
    """
    форма редактирования блоков, пользователей и команд для файла мероприятия
    """
    template_name = 'includes/_material_event_block.html'

    def get_context_data(self, **kwargs):
        if not self.current_user_is_assistant:
            raise PermissionDenied
        try:
            material = EventOnlyMaterial.objects.get(id=self.request.GET.get('id'))
        except (EventOnlyMaterial, TypeError, ValueError):
            raise Http404
        data = super().get_context_data(**kwargs)
        prefix = self.make_prefix(material.id)
        data.update({
            'blocks_form': EventMaterialForm(instance=material, event=self.event, prefix=prefix),
            'custom_form_prefix': prefix,
        })
        return data

    @staticmethod
    def make_prefix(material_id):
        return 'edit-{}'.format(material_id)

    @staticmethod
    def parse_material_id_from_prefix(prefix):
        try:
            return int(prefix.split('-')[1])
        except:
            pass


class UserChartApiView(APIView):
    """
    **Описание**

        Запрос данных для отрисовки чарта пользовательских компетенций

    **Пример запроса**

        GET /api/user-chart/?user_id=123

    **Параметры запроса**

        * user_id - leader id пользователя

    **Пример ответа**

        * 200 успешно
        * 400 неполный запрос
        * 403 api key отсутствует или неправильный
        * 404 пользователь не найден
    """

    permission_classes = ()

    def get(self, request):
        user_id = request.GET.get('user_id')
        if not user_id:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.filter(leader_id=user_id).first()
        if not user:
            return Response(status=status.HTTP_404_NOT_FOUND)
        data = recalculate_user_chart_data(user)
        return Response(data)


class FileInfoMixin:
    def get_file_info(self, m):
        return {
            'event_uuid': m.event.uid,
            'file_url': m.get_url(),
            'file_name': m.get_file_name(),
            'comment': m.result_v2.comment,
            'levels': m.result_v2.get_meta(),
            'url': m.get_page_url(),
        }


class UserMaterialsListView(FileInfoMixin, APIView):
    """
    **Описание**

        Запрос файлов пользователя по его unti_id, выводятся только файлы, привязанные к результату

    **Пример запроса**

        GET /api/user-materials/?unti_id=123

    **Параметры запроса**

        * unti_id - unti id пользователя

    **Пример ответа**

        * 200 успешно
            [
                {
                    "event_uuid": "11111111-1111-1111-11111111",
                    "file_url": "http://example.com/file.pdf"
                    "file_name": "file.pdf",
                    "comment": "",
                    "levels": [{"level": 1, "sublevel": 1, "competence": "11111111-1111-1111-11111111}],
                    "url": "https://uploads.2035.university/11111111-1111-1111-11111111/123/"
                },
                {
                    "event_uuid": "11111111-1111-1111-11111111",
                    "file_url": "http://example.com/file.pdf"
                    "file_name": "file.pdf",
                    "comment": "",
                    "levels": [{"level": 1, "sublevel": 1, "competence": "11111111-1111-1111-11111111}],
                    "url": "https://uploads.2035.university/load-team/11111111-1111-1111-11111111/123/",
                    "team": {"id": 1, "name": "name", "members": [1, 2]}
                },
                ...
            ]
        * 400 неполный запрос
        * 403 api key отсутствует или неправильный
        * 404 пользователь не найден
    """

    permission_classes = (ApiPermission, )

    def get(self, request):
        unti_id = request.query_params.get('unti_id')
        if not unti_id or not unti_id.isdigit():
            return Response(status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.filter(unti_id=unti_id).first()
        if not user:
            return Response(status=status.HTTP_404_NOT_FOUND)
        materials = EventMaterial.objects.filter(user_id=user.id, result_v2__isnull=False).\
            select_related('event', 'user', 'result_v2', 'result_v2__result').\
            prefetch_related('result_v2__circle_items')
        team_materials = EventTeamMaterial.objects.filter(team__users__id=user.id, result_v2__isnull=False).\
            select_related('event', 'team', 'result_v2', 'result_v2__result').\
            prefetch_related('team__users', 'result_v2__circle_items')
        resp = [self.get_file_info(m) for m in materials.iterator()]
        for m in team_materials:
            data = self.get_file_info(m)
            data.update({'team': {
                'id': m.team.id,
                'name': m.team.name,
                'members': [i.unti_id for i in m.team.users.all()]
            }})
            resp.append(data)
        return Response(resp)


class BaseResultInfoView(APIView):
    permission_classes = (ApiPermission, )
    result_model = LabsUserResult
    materials_model = EventMaterial

    def get(self, request):
        result_id = request.query_params.get('id')
        if not result_id or not result_id.isdigit():
            return Response(status=status.HTTP_400_BAD_REQUEST)
        result = self.result_model.objects.filter(id=result_id).\
            select_related('result', 'result__block__event').prefetch_related('circle_items').first()
        if not result:
            return Response(status=status.HTTP_404_NOT_FOUND)
        materials = self.materials_model.objects.filter(result_v2=result)
        resp = {
            'event_uuid': result.result.block.event.uid,
            'comment': result.comment,
            'approved': result.approved,
            'levels': result.get_meta(),
            'url': result.get_page_url(),
            'files': [{
                'file_url': f.get_url(),
                'file_name': f.get_file_name(),
                'created_at': f.created_at and f.created_at.isoformat()
            } for f in materials]
        }
        self.update_response(resp, result)
        return Response(resp)

    def update_response(self, resp, result):
        pass


class UserResultInfoView(BaseResultInfoView):
    """
    **Описание**

        Запрос информации о пользовательском результате по его id

    **Пример запроса**

        GET /api/user-result-info/?id=123

    **Параметры запроса**

        * id - id результата

    **Пример ответа**

        * 200 успешно
            {
                "event_uuid": "11111111-1111-1111-11111111",
                "comment": "",
                "approved": false,
                "levels": [{"level": 1, "sublevel": 1, "competence": "11111111-1111-1111-11111111}],
                "user": {"unti_id": 1},
                "url": "https://uploads.2035.university/11111111-1111-1111-11111111/123/",
                "files": [
                    {
                        "file_url": "http://example.com/file.pdf",
                        "file_name": "file.pdf",
                        "created_at": "2019-04-26T10:33:09.223871+00:00"
                    }
                ]
            }
        * 400 неполный запрос
        * 403 api key отсутствует или неправильный
        * 404 результат не найден
    """

    def update_response(self, resp, result):
        resp['user'] = {'unti_id': result.user.unti_id}


class TeamResultInfoView(BaseResultInfoView):
    """
    **Описание**

        Запрос информации о командном результате по его id

    **Пример запроса**

        GET /api/team-result-info/?id=123

    **Параметры запроса**

        * id - id результата

    **Пример ответа**

        * 200 успешно
            {
                "event_uuid": "11111111-1111-1111-11111111",
                "comment": "",
                "approved": false,
                "levels": [{"level": "1", "sublevel": "1", "competence": "11111111-1111-1111-11111111"}],
                "team": {"id": 1, "name": "name", "members": [1, 2]},
                "url": "https://uploads.2035.university/load-team/11111111-1111-1111-11111111/123/",
                "files": [
                    {
                        "file_url": "http://example.com/file.pdf",
                        "file_name": "file.pdf",
                        "created_at": "2019-04-26T10:33:09.223871+00:00"
                    }
                ]
            }
        * 400 неполный запрос
        * 403 api key отсутствует или неправильный
        * 404 результат не найден
    """
    result_model = LabsTeamResult
    materials_model = EventTeamMaterial

    def update_response(self, resp, result):
        resp['team'] = {
            'id': result.team_id,
            'name': result.team.name,
            'members': [i.unti_id for i in result.team.get_members_for_event(result.result.block.event)]
        }


class CustomLimitOffsetPagination(LimitOffsetPagination):
    default_limit = settings.DRF_LIMIT_OFFSET_PAGINATION_DEFAULT
    max_limit = settings.DRF_LIMIT_OFFSET_PAGINATION_MAX


class AllUserResultsView(ListAPIView):
    """
    **Описание**

        Запрос информации о всех пользовательских результатах

    **Пример запроса**

        GET /api/all-user-results/?unti_id=123&created_at_after=2019-01-31T00:00:00&limit=10&offset=10

    **Параметры запроса**

        * unti_id - unti id пользователя, необязательный параметр
        * created_at_after - минимальная дата и время создания в iso формате, необязательный параметр
        * created_at_before - максимальная дата и время создания в iso формате, необязательный параметр
        * limit - максимальное количество результатов на странице, но не более 50
        * offset

    **Пример ответа**

        * 200 успешно
            {
                "count": 1,
                "next": null,
                "previous": null,
                "results": [
                    {
                        "event_uuid": "63284c8e-4f4a-4b54-9ef9-92f1cfb13d98",
                        "comment": "",
                        "approved": false,
                        "levels": null,
                        "url": "http://example.com/63284c8e-4f4a-4b54-9ef9-92f1cfb13d98/2/user/1",
                        "files": [
                            {
                                "file_url": "http://example.com/media/63284c8e-4f4a-4b54-9ef9-92f1cfb13d98/22/file.pdf",
                                "file_name": "file.pdf",
                                "created_at": "2019-04-26T10:33:09.223871+00:00"
                            }
                        ],
                        "user": {
                            "unti_id": 2
                        }
                    }
                ]
            }
        * 400 некорректный запрос
        * 403 неправильный api key
    """
    pagination_class = CustomLimitOffsetPagination
    serializer_class = LabsUserResultSerializer
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = LabsUserResultFilter
    permission_classes = (ApiPermission,)

    def get_queryset(self):
        return LabsUserResult.objects.select_related('user', 'result__block__event')\
            .prefetch_related('eventmaterial_set', 'circle_items').distinct()


class AllTeamResultsView(ListAPIView):
    """
    **Описание**

        Запрос информации о всех командных результатах

    **Пример запроса**

        GET /api/all-team-results/?team_id=123&created_at_after=2019-01-31T00:00:00&limit=10&offset=10

    **Параметры запроса**

        * team_id - id команды, необязательный параметр
        * created_at_after - минимальная дата и время создания в iso формате, необязательный параметр
        * created_at_before - максимальная дата и время создания в iso формате, необязательный параметр
        * limit - максимальное количество результатов на странице, но не более 50
        * offset

    **Пример ответа**

        * 200 успешно
            {
                "count": 1,
                "next": null,
                "previous": null,
                "results": [
                    {
                        "event_uuid": "63284c8e-4f4a-4b54-9ef9-92f1cfb13d98",
                        "comment": "",
                        "approved": false,
                        "levels": null,
                        "url": "http://example.com/63284c8e-4f4a-4b54-9ef9-92f1cfb13d98/2/team/1",
                        "files": [
                            {
                                "file_url": "http://example.com/media/63284c8e-4f4a-4b54-9ef9-92f1cfb13d98/22/file.pdf",
                                "file_name": "file.pdf",
                                "created_at": "2019-04-26T10:33:09.223871+00:00"
                            }
                        ],
                        "team": {
                            "id": 123,
                            "name": "name",
                            "members": [1, 2, 3]
                        }
                    }
                ]
            }
        * 400 некорректный запрос
        * 403 неправильный api key
    """
    pagination_class = CustomLimitOffsetPagination
    serializer_class = LabsTeamResultSerializer
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = LabsTeamResultFilter
    permission_classes = (ApiPermission,)

    def get_queryset(self):
        return LabsTeamResult.objects.select_related('team', 'result__block__event')\
            .prefetch_related('eventteammaterial_set', 'team__users', 'circle_items').distinct()


class GetDpData(APIView):
    """
    TODO: описание
    """
    authentication_classes = (SessionAuthentication, )
    permission_classes = (IsAdminUser, )

    def get(self, request):
        event_uid = request.GET.get('event')
        if not event_uid:
            event = None
        else:
            event = get_object_or_404(Event, uid=event_uid)
        s = io.StringIO()
        c = csv.writer(s, delimiter=';')
        for line in get_results_list(event):
            c.writerow(line)
        s.seek(0)
        b = io.BytesIO()
        b.write(s.read().encode('utf8'))
        b.seek(0)
        resp = FileResponse(b, content_type='text/csv')
        resp['Content-Disposition'] = "attachment; filename*=UTF-8''{}.csv".format('data')
        return resp


@method_decorator(login_required, name='dispatch')
@method_decorator(context_setter, name='get')
class ResultPage(TemplateView):
    template_name = 'result_page.html'

    def get_context_data(self, **kwargs):
        if self.kwargs['result_type'] not in ['user', 'team']:
            raise Http404
        model = LabsUserResult if self.kwargs['result_type'] == 'user' else LabsTeamResult
        dic = {'id': self.kwargs['result_id']}
        if self.kwargs['result_type'] == 'user':
            dic['user__unti_id'] = self.kwargs['unti_id']
        else:
            dic['team_id'] = self.kwargs['unti_id']
        result = get_object_or_404(model, **dic)
        event = result.result.block.event
        return {
            'type': self.kwargs['result_type'],
            'result': result,
            'files': result.get_files(),
            'event': event,
            'structure': event.blocks.prefetch_related('results'),
            'models': result.models_list(),
        }


class ApiCheckHealth(APIView):
    """
    **Описание**

        Проверка статуса приложения, связи с системами, с которыми оно общается, и с базой данных

    **Пример запроса**

        GET /api/check/

    **Пример ответа**

        * 200 успешно
            {
                "labs": "ok",
                "dp": 500,
                "xle": "ok",
                "sso": "ok",
                "mysql": "ok",
                "kafka": false,
                "release": "1.1.0",
            }
        * 403 api key отсутствует или неправильный
    """
    permission_classes = (ApiPermission, )

    def get(self, request):
        return Response({
            'labs': LabsApi().health_check(),
            'dp': DpApi().health_check(),
            'xle': XLEApi().health_check(),
            'sso': SSOApi().health_check(),
            'mysql': check_mysql_connection(),
            'kafka': check_kafka(),
            'release': get_release_version(),
        })


class CSVResponseGeneratorMixin:
    def get_csv_response(self, obj):
        b = BytesCsvStreamWriter(get_csv_encoding_for_request(self.request))
        c = csv.writer(b, delimiter=';')
        resp = StreamingHttpResponse(
            (c.writerow(list(map(str, row))) for row in obj.generate()),
            content_type="text/csv"
        )
        resp['Content-Disposition'] = "attachment; filename*=UTF-8''{}.csv".format(obj.get_csv_filename())
        return resp


class XLSResponseGeneratorMixin:
    def get_xls_response(self, obj):
        out = io.BytesIO()
        writer = XLSWriter(out)
        for row in obj.generate():
            writer.writerow(row)
        writer.close()
        out.seek(0)
        resp = FileResponse(out)
        resp['Content-Disposition'] = "attachment; filename*=UTF-8''{}.xlsx".format(obj.get_csv_filename())
        return resp


class ChooseFormatResponseGeneratorMixin(CSVResponseGeneratorMixin, XLSResponseGeneratorMixin):
    def get_response(self, obj):
        if self.request.GET.get('format') == 'xls':
            return self.get_xls_response(obj)
        return self.get_csv_response(obj)


class EventCsvData(GetEventMixin, ChooseFormatResponseGeneratorMixin, View):
    def get(self, request, *args, **kwargs):
        if not self.current_user_is_assistant:
            raise PermissionDenied
        obj = EventMaterialsCSV(self.event)
        if request.GET.get('check_empty'):
            return JsonResponse({'has_contents': obj.has_contents()})
        return self.get_response(obj)


@method_decorator(login_required, name='dispatch')
class BaseCsvEventsDataView(ChooseFormatResponseGeneratorMixin, View):
    def get(self, request):
        if not request.user.has_assistant_role():
            raise PermissionDenied
        events = self.get_events_for_csv()
        activity_filter = getattr(self, 'activity_filter', None)
        date_min, date_max = self.get_dates()
        meta_data = {
            'activity': activity_filter,
            'date_min': date_min,
            'date_max': date_max,
            'context': request.user.chosen_context,
            'format': 'xlsx' if request.GET.get('format') == 'xls' else 'csv',
        }
        obj = EventGroupMaterialsCSV(events, meta_data)
        num = obj.count_materials()
        if request.GET.get('check_empty'):
            return JsonResponse({
                'has_contents': num > 0,
                'max_num': settings.MAX_MATERIALS_FOR_SYNC_GENERATION,
                'sync': num <= settings.MAX_MATERIALS_FOR_SYNC_GENERATION,
                'max_csv': settings.MAX_PARALLEL_CSV_GENERATIONS,
                'can_generate': CSVDump.current_generations_for_user(request.user) < \
                                settings.MAX_PARALLEL_CSV_GENERATIONS,
                'page_url': reverse('csv-dumps-list'),
            })
        if num <= settings.MAX_MATERIALS_FOR_SYNC_GENERATION:
            return self.get_response(obj)
        if CSVDump.current_generations_for_user(request.user) >= settings.MAX_PARALLEL_CSV_GENERATIONS:
            raise PermissionDenied
        task_meta = meta_data.copy()
        task_meta['activity'] = activity_filter and activity_filter.id
        task_meta['context'] = request.user.chosen_context and request.user.chosen_context.id
        csv_dump = CSVDump.objects.create(
            owner=request.user, header=obj.get_csv_filename(do_quote=False), meta_data=task_meta
        )
        generate_events_csv.delay(csv_dump.id, [i.id for i in events], request.GET.get('format'), task_meta)
        return JsonResponse({'page_url': reverse('csv-dumps-list'), 'dump_id': csv_dump.id})

    def get_events_for_csv(self):
        return Event.objects.none()


class EventsCsvData(IndexPageEventsFilterMixin, BaseCsvEventsDataView):
    """
    Выгрузка csv по нескольким мероприятиям сразу
    """
    def get_events_for_csv(self):
        return self.get_events()


class ActivitiesCsvData(ActivitiesFilter, BaseCsvEventsDataView):
    """
    Выгрузка csv по нескольким активностям сразу
    """
    def get_events_for_csv(self):
        return Event.objects.filter(
            activity_id__in=self.get_activities().order_by().values_list('id', flat=True)
        ).order_by('title', 'dt_start')



@login_required
def switch_context(request):
    """
    Установка нового контекста для пользователя. Возвращает урл редиректа
    """
    if not request.user.has_assistant_role():
        raise PermissionDenied
    try:
        if 'context_id' in request.POST and request.POST['context_id'] == '':
            context = None
        else:
            context = Context.objects.get(id=request.POST.get('context_id'))
        request.user.chosen_context = context
        request.user.save(update_fields=['chosen_context'])
        current_url = request.POST.get('url')
        try:
            url = resolve(current_url)
            if url.url_name == 'index':
                redirect_url = current_url
            else:
                redirect_url = reverse('events')
        except Resolver404:
            redirect_url = reverse('index')
        resp = JsonResponse({'redirect': redirect_url})
        if context:
            # если пользователь ассистент в выбранном контексте, по дефолту показывать мероприятия в режиме ассистента
            resp.set_cookie(
                VIEW_MODE_COOKIE_NAME,
                'as_assistant' if request.user.is_assistant_for_context(context) else 'as_user'
            )
        return resp
    except (Context.DoesNotExist, ValueError, TypeError):
        raise Http404


@method_decorator(login_required, name='dispatch')
class LoadCsvDump(View):
    def get(self, request, **kwargs):
        if not request.user.has_assistant_role():
            raise PermissionDenied
        obj = get_object_or_404(CSVDump, id=kwargs['dump_id'], status=CSVDump.STATUS_COMPLETE)
        resp = FileResponse(default_storage.open(obj.csv_file.name))
        resp['Content-Disposition'] = "attachment; filename*=UTF-8''{header}".format(header=quote(obj.get_file_name()))
        return resp


@method_decorator(login_required, name='dispatch')
class CSVDumpsList(ListView):
    model = CSVDump
    paginate_by = 50
    template_name = 'my_csv_dumps.html'

    def get_queryset(self):
        return self.model.objects.filter(owner=self.request.user).order_by('-datetime_ordered').select_related('owner')

    def get_context_data(self, *, object_list=None, **kwargs):
        if not self.request.user.has_assistant_role():
            raise PermissionDenied
        data = super().get_context_data(object_list=object_list, **kwargs)
        context_ids = {}
        object_list = data['object_list']
        for obj in object_list:
            meta_data = obj.meta_data if isinstance(obj.meta_data, dict) else {}
            context_ids[obj.id] = meta_data.get('context')
        contexts = dict(Context.objects.filter(id__in=filter(None, context_ids.values())).values_list('id', 'guid'))
        for obj in object_list:
            obj.meta = {
                'context_guid': contexts.get(context_ids[obj.id]),
            }
        return data


class UploadUserFile(CreateAPIView):
    """
    **Описание**

        Загрузка пользовательского файла

    **Пример запроса**

        POST /api/upload-user-file/

    **Параметры post-запроса**

        * user: int - unti id пользователя
        * source: str - система инициатор загрузки
        * file: загружаемый файл
        * activity_uuid: str - uuid активности (необязательный параметр)
        * data: str - json с дополнительными данными (необязательный параметр)

    **Пример ответа**

        * 200 успешно
            {
                "id":8,
                "user":1,
                "data":"{\"qwerty\": 123}",
                "source":"PLE",
                "activity_uuid":"",
                "file":"http://127.0.0.1:8092/media/course-image.jpg"
            }
        * 400 некорректный запрос
        * 403 api key отсутствует или неправильный
    """

    permission_classes = (ApiPermission, )
    serializer_class = UserFileSerializer
    parser_classes = (MultiPartParser, )


class CreateUserResultAPI(APIView):
    """
    **Описание**

        Загрузка пользовательского результата

    **Пример запроса**

        POST /api/upload/create-user-result/{
            "user": 1,
            "comment": "",
            "meta": "{\"key\": \"value\"}",
            "materials": [{"url": "http://example.com/file.pdf"}, {"file": "http://example.com/file.pdf"}],
            "callback_url": "https://ple.2035.university/callback"
        }

    **Параметры запроса**

        * user - unti id пользователя
        * comment - комментарий к результату (необязательно)
        * additional_data - json c разметкой
        * materials - массив ссылок на файлы или ссылки результата, ключ url должен присутствовать для ссылок,
                      а file - для файлов, которые uploads будет закачивать
        * callback_url - url, к которому обратится uploads после обработки запроса

    **Пример ответа**

        * 200 успешно
        * 400 некорректный запрос
        * 403 неверный api key
        * 417 если невозможно обработать запрос
    """

    permission_classes = (ApiPermission,)
    serializer_class = UserResultSerializer

    def post(self, request):
        if not check_celery_active():
            return Response(status=status.HTTP_417_EXPECTATION_FAILED)
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        handle_ple_user_result.delay(request.data)
        return Response(status=status.HTTP_200_OK)


class GetPLEUserResultApi(APIView):
    """
    **Описание**

        Запрос информации о пользовательском результате в PLE

    **Пример запроса**

        GET /api/get-ple-user-result/{result_id}/

    **Параметры запроса**

        * result_id - id результата, обязательный параметр

    **Пример ответа**

        * 200 успешно
            {
                "id": 1,
                "user": 1,
                "meta": {"key": "value"},
                "comment": "",
                "materials": [
                    {
                        "id": 1,
                        "uploads_url": "http://example.com/file.pdf"
                    }
                ]
            }
        * 403 неверный api key
        * 404 результат с указанным id не существует
    """

    permission_classes = (ApiPermission,)

    def get(self, request, *args, **kwargs):
        try:
            user_result = PLEUserResult.objects.get(id=kwargs['result_id'])
        except PLEUserResult.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(user_result.get_json())


class DeleteTeamView(GetEventMixinWithAccessCheck, View):
    def post(self, request, **kwargs):
        team = get_object_or_404(Team, id=self.kwargs['team_id'])
        if not team.user_can_delete_team(request.user):
            raise PermissionDenied
        logging.warning('User #%s deleted team %s from event %s', request.user.id, team.name, team.event.uid)
        team.delete()
        return JsonResponse({'status': 0})


class EventSelfEnroll(GetEventMixin, View):
    def post(self, request, **kwargs):
        EventEntry.all_objects.update_or_create(
            user=request.user, event=self.event, defaults={'self_enrolled': True, 'deleted': False}
        )
        return JsonResponse({'status': 0})


class CheckUserTraceApi(APIView):
    """
    **Описание**

        Проверка загрузки пользователем цифрового следа для мероприятия

    **Пример запроса**

        GET /api/check-user-trace/?leader_id=1&event_id=cd602dd7-4fef-440b-82bf-013b5817e3dd

    **Параметры запроса**

        * event_id - uuid мероприятия, обязательный параметр
        * leader_id - leader id пользователя, обязательный параметр

    **Пример ответа**

        * 200 успешно
            {
                "exists": true,
                "n_personal": 2,
                "n_team": 3
            }
            где n_personal - количество ЦС, который пользователь загрузил для себя,
            n_team - количество ЦС из команд event-а, в которых есть пользователь,
            exists true, если хотя бы одно из значенй n_personal или n_team больше 0
        * 400
            {
                "leader_id": "user with leader_id 1 not found",
                "event_id": "event with uuid cd602dd7-4fef-440b-82bf-013b5817e3dd not found"
            }
            если не указан какой-то параметр или не найден пользователь/мероприятие с описанием ошибок по параметрам
    """
    permission_classes = ()

    def get(self, request):
        event_id = request.query_params.get('event_id')
        leader_id = request.query_params.get('leader_id')
        errors = {}
        if not event_id:
            errors['event_id'] = 'required parameter'
        else:
            try:
                event = Event.objects.get(uid=event_id)
            except Event.DoesNotExist:
                errors['event_id'] = 'event with uuid {} not found'.format(event_id)
        if not leader_id:
            errors['leader_id'] = 'leader_id required'
        else:
            try:
                user = User.objects.get(leader_id=leader_id)
            except (User.DoesNotExist, User.MultipleObjectsReturned):
                errors['leader_id'] = 'user with leader_id {} not found'.format(leader_id)
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        n_personal = EventMaterial.objects.filter(event=event, user=user).count()
        n_team = EventTeamMaterial.objects.filter(event=event, team__users=user).distinct().count()
        return Response({
            'exists': n_personal + n_team > 0,
            'n_personal': n_personal,
            'n_team': n_team,
        })


class EventMaterialsApi(ListAPIView):
    """
    **Описание**

        Получение списка материалов мероприятия

    **Пример запроса**

        GET /api/event-materials/?event_id=cd602dd7-4fef-440b-82bf-013b5817e3dd

    **Параметры запроса**

        * event_id - uuid мероприятия, обязательный параметр

    **Пример ответа**

        * 200 успешно
            {
                "count": 1, // количество объектов
                "next": null, // полный url следующей страницы (если есть)
                "previous": null, // полный url предыдущей страницы (если есть)
                "results": [
                    {
                        "id": 1,
                        "url": "", // урл файла, если он был загружен ссылкой
                        "file": "http://127.0.0.1:8092/media/file.csv", // урл файла в uploads, если он был загружен как файл
                        "file_type": "text/csv", // тип файла
                        "file_size": 8835, // размер в байтах
                        "created_at": "2019-07-08T20:01:50.104666+10:00",
                        "initiator": 11111134, // unti_id того, кто загрузил файл (может быть null)
                        "deleted": false, // если deleted: true, значит файл был перенесен в личные или командные
                        "comment": "qwe",
                        "event": "c26530a5-09a0-485d-89cc-3ccb790ba876",
                        "trace": { // информация о блоке, который загружен файл
                            "trace_type": "Презентация",
                            "name": "Презентация спикера",
                            "event_type": "36364eea-de91-4a9d-b498-87e5beb9b3c1", // uuid типа события из labs
                            "deleted": false
                        }
                    }
                ]
            }

        * 400 если не указан event_id или такого мероприятия нет
        * 403 если не указан хедер X-API-KEY или ключ неверен
    """

    permission_classes = (ApiPermission, )
    serializer_class = EventOnlyMaterialSerializer
    pagination_class = Paginator

    def get_queryset(self):
        if not self.request.query_params.get('event_id'):
            raise exceptions.ValidationError({'event_id': 'required parameter'})
        event = Event.objects.filter(uid=self.request.query_params.get('event_id')).first()
        if not event:
            raise exceptions.ValidationError({'event_id': 'event with uuid {} not found'.
                                             format(self.request.query_params.get('event_id'))})
        return EventOnlyMaterial.all_objects.filter(event=event).select_related('event', 'trace', 'trace__event_type')


class StatisticsPaginator(PageNumberPagination):
    page_size = 100


class ContextUserStatistics(ListAPIView):
    """
    **Описание**

        Получение статистики по пользователям, у которых есть цс в контексте

    **Пример запроса**

        GET /api/context-user-statistics/{context_uuid}/?unti_id=1&force_update=1

    **Параметры запроса**

        * unti_id - unti_id пользователя, необязательный параметр
        * leader_id - leader_id пользователя, необязательный параметр
        * force_update - если присутствует в запросе, будет произведен пересчет статистики по пользователю. Работает
                         только в случае запроса статистики по конкретному пользователю

    **Пример ответа**

        * 200 успешно
            {
                "count": 1, // количество объектов
                "next": null, // полный url следующей страницы (если есть)
                "previous": null, // полный url предыдущей страницы (если есть)
                "results": [
                    {
                        "context": "2fa173c5-6a0b-4d76-b670-be49004ac7c6",
                        "unti_id": 1,
                        "leader_id": "123",
                        "n_entry": 2,  // количество материалов мероприятия, загруженных пользователем
                        "n_run_entry": 0,  // количество записей на прогоны котекста
                        "n_personal": 0,  // колчество персональных файлов
                        "n_team": 2018,  // количество командных файлов
                        "n_event": 4,  // количество записей на мероприятия контекста
                        "updated_at": "2019-07-17T02:35:32.685916+10:00"
                    }
                ]
            }

        * 400 если unti_id не является числом
        * 403 если не указан хедер X-API-KEY или ключ неверен
    """

    permission_classes = (ApiPermission, )
    serializer_class = DTraceStatisticsSerializer
    pagination_class = StatisticsPaginator
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = StatisticsFilter

    def get_queryset(self):
        return DTraceStatistics.objects.filter(context__uuid=self.kwargs['context_uuid'])\
            .select_related('user', 'context')

    def list(self, request, *args, **kwargs):
        if any(i in request.query_params for i in ('leader_id', 'unti_id')):
            item = self.filter_queryset(self.get_queryset()).first()
            if item and (item.updated_at < timezone.now() - timezone.timedelta(seconds=settings.STATISTICS_VALID_FOR)
                         or 'force_update' in request.query_params):
                calculate_user_context_statistics(item.user, item.context)
        return super().list(request, *args, **kwargs)
