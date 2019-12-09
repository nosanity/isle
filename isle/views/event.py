import logging
from collections import defaultdict

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import HttpResponseForbidden, JsonResponse, Http404
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse, resolve, Resolver404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.views import View
from django.views.generic import ListView, TemplateView

from isle.cache import get_user_available_contexts
from isle.forms import AddUserForm
from isle.models import EventMaterial, EventTeamMaterial, EventOnlyMaterial, Event, EventEntry, Team, Attendance, User, \
    Activity, RunEnrollment, ActivityEnrollment, LabsEventResult, Context, LabsUserResult, LabsTeamResult
from isle.utils import get_allowed_event_type_ids
from isle.views.common import context_setter, GetEventMixin


VIEW_MODE_COOKIE_NAME = 'index-view-mode'


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
        dt_filter = {}
        if min_dt:
            dt_filter['dt_start__gte'] = min_dt
        if max_dt:
            dt_filter['dt_start__lt'] = max_dt
        if dt_filter:
            events = events.filter(**dt_filter)
        if self.activity_filter:
            events = events.filter(activity=self.activity_filter)
        events = self.filter_search(events)
        events = events.order_by('{}dt_start'.format('' if self.is_asc_sort() else '-'))
        if self.current_mode_is_assistant:
            if self.request.user.chosen_context_id and \
                    self.request.user.is_assistant_for_context(self.request.user.chosen_context):
                events = events.filter(context_id=self.request.user.chosen_context_id)
            else:
                events = events.filter(context__uuid__in=get_user_available_contexts(self.request.user) or [])
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
        data.update({
            'students': users,
            'event': self.event,
            'event_entry': event_entry,
            'event_entry_id': getattr(event_entry, 'id', 0),
        })
        data.update(self.get_teams_data(self.event, self.request.user, users))
        return data

    @staticmethod
    def get_teams_data(event, user, users):
        teams = list(Team.objects.filter(event=event).select_related('creator').prefetch_related('users')) + \
                list(event.get_pt_teams(user_ids=[i.id for i in users]))
        user_teams = [
            i.id for i in teams if user in
                                   i.get_members_for_event(event, user_ids=[i.id for i in users])
        ]
        teams = sorted(list(teams), key=lambda x: (int(x.id not in user_teams), x.name.lower()))
        for team in teams:
            team.traces_number = team.get_traces_number_for_event(event)
        return {
            'teams': teams,
            'user_teams': user_teams,
            'teams_allowed_to_delete': [i.id for i in teams if i.user_can_delete_team(user)],
        }


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
        dt_filter = {}
        if min_dt:
            dt_filter['event__dt_start__gte'] = min_dt
        if max_dt:
            dt_filter['event__dt_start__lt'] = max_dt
        if dt_filter:
            qs = qs.filter(**dt_filter)
        qs = self.filter_search(qs)
        return qs.distinct().order_by('title', 'id')

    def filter_context(self, qs):
        if self.request.user.chosen_context_id:
            if self.request.user.is_assistant_for_context(self.request.user.chosen_context):
                return qs.filter(id__in=Event.objects.filter(
                    context_id=self.request.user.chosen_context_id).values_list('activity_id', flat=True)
                )
            return qs.none()
        return qs.filter(event__context__uuid__in=get_user_available_contexts(self.request.user) or [])

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


class EventSelfEnroll(GetEventMixin, View):
    def post(self, request, **kwargs):
        EventEntry.all_objects.update_or_create(
            user=request.user, event=self.event, defaults={'self_enrolled': True, 'deleted': False}
        )
        if LabsEventResult.objects.filter(block__event=self.event, deleted=False, block__deleted=False).\
                exclude(result_format='group').exists():
            redirect_url = reverse('load-materials', kwargs={'uid': self.event.uid, 'unti_id': request.user.unti_id})
        else:
            redirect_url = reverse('event-view', kwargs={'uid': self.event.uid})
        return JsonResponse({'status': 0, 'redirect': redirect_url})


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
            'models': result.models_list(),
        }
