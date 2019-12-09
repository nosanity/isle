import functools

from dal import autocomplete
from dal_select2_queryset_sequence.views import Select2QuerySetSequenceView
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.http import Http404
from queryset_sequence import QuerySetSequence
from social_django.models import UserSocialAuth

from isle.forms import get_available_sublevels
from isle.models import Event, User, EventEntry, RunEnrollment, Team, MetaModel, DpCompetence, DpTool, ModelCompetence


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


class MetaModelAutocomplete(autocomplete.Select2QuerySetView):
    queryset = MetaModel.objects.all()
    model_field_name = 'title'

    def get_queryset(self):
        return super().get_queryset().order_by('title')


class CompetenceAutocomplete(autocomplete.Select2QuerySetView):
    queryset = DpCompetence.objects.all()
    model_field_name = 'title'

    def get_queryset(self):
        if self.forwarded.get('metamodel') and self.forwarded['metamodel'].isdigit():
            return super().get_queryset().filter(models__model_id=self.forwarded['metamodel'])\
                .order_by('models__order')
        else:
            raise Http404


class ToolAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        try:
            model = MetaModel.objects.get(id=self.forwarded['metamodel'])
        except (MetaModel.DoesNotExist, TypeError, ValueError):
            return DpTool.objects.none()
        qs = model.tools.order_by('title')
        if self.q:
            qs = qs.filter(title__icontains=self.q)
        return qs


class SublevelAutocomplete(autocomplete.Select2ListView):
    def get_list(self):
        try:
            modelcompetence = ModelCompetence.objects.select_related('competence').\
                get(competence_id=self.forwarded['competence'], model_id=self.forwarded['metamodel'])
            level = int(self.forwarded['level'])
        except (ModelCompetence.DoesNotExist, ValueError, TypeError, KeyError):
            raise Http404
        return list(map(str, get_available_sublevels(modelcompetence, level)))


class TeamAndUserAutocomplete(Select2QuerySetSequenceView):
    """
    автокомплит по пользователям и командам для использования в форме фильтрации результатов
    и форме загрузки файлов на странице цс мероприятия
    """
    def get_queryset(self):
        event_id = self.forwarded.get('event')
        try:
            event = Event.objects.get(id=event_id)
        except (Event.DoesNotExist, ValueError, TypeError):
            raise Http404
        obj_type = self.forwarded.get('type')
        action_upload = self.forwarded.get('format') == 'upload'
        is_assistant = self.request.user.is_assistant_for_context(event.context)
        if obj_type == 'team':
            users = User.objects.none()
        else:
            users = event.get_participants()
            if action_upload and not is_assistant:
                users = users.filter(id=self.request.user.id)
        if obj_type == 'user':
            teams = Team.objects.none()
        else:
            teams = Team.objects.filter(event=event, system=Team.SYSTEM_UPLOADS)
            if not (action_upload and not settings.ENABLE_PT_TEAMS):
                uploads_teams = set(teams.values_list('id', flat=True))
                pt_teams = set(event.get_pt_teams().values_list('id', flat=True))
                teams = Team.objects.filter(id__in=uploads_teams | pt_teams)
            if action_upload and not is_assistant:
                teams = teams.filter(users=self.request.user)
        if self.q:
            teams_q = Q(name__icontains=self.q) | \
                Q(users__last_name__icontains=self.q) | \
                Q(users__first_name__icontains=self.q) | \
                Q(users__second_name__icontains=self.q)
            teams = teams.filter(teams_q).distinct()
            users = UserAutocomplete.search_user(users, self.q)
        return QuerySetSequence(users, teams)

    def get_result_value(self, result):
        return '%s-%s' % (ContentType.objects.get_for_model(result).pk,
                          result.unti_id if isinstance(result, User) else result.pk)
