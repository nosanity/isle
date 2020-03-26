import logging

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.functional import cached_property
from django.views import View
from django.views.generic import TemplateView

from isle.forms import CreateTeamForm, EditTeamForm
from isle.models import EventEntry, RunEnrollment, Team, LabsTeamResult
from isle.tasks import team_members_set_changed
from isle.views.common import GetEventMixin, GetEventMixinWithAccessCheck
from isle.views.event import EventView


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
        if request.GET.get('next'):
            redirect_url = request.GET['next']
        else:
            redirect_url = reverse('event-view', kwargs={'uid': self.event.uid})
        return JsonResponse({'redirect': redirect_url})

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


class DeleteTeamView(GetEventMixinWithAccessCheck, View):
    def post(self, request, **kwargs):
        team = get_object_or_404(Team, id=self.kwargs['team_id'])
        if not team.user_can_delete_team(request.user):
            raise PermissionDenied
        logging.warning('User #%s deleted team %s from event %s', request.user.id, team.name, team.event.uid)
        team.delete()
        return JsonResponse({'status': 0})


class EventTeams(GetEventMixinWithAccessCheck, TemplateView):
    template_name = 'event_teams.html'

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        users = list(self.event.get_participants())
        data.update({
            'students': users,
            'event': self.event,
            'team_ct': ContentType.objects.get_for_model(Team),
        })
        data.update(EventView.get_teams_data(self.event, self.request.user, users))
        return data
