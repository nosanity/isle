from django import forms
from django.conf import settings
from dal import autocomplete, forward
from isle.models import Team, User, EventBlock, EventOnlyMaterial, UserResult, TeamResult, UserRole, EventEntry


class BaseTeamForm(forms.ModelForm):
    def __init__(self, **kwargs):
        qs = kwargs.pop('users_qs')
        self.event = kwargs.pop('event')
        self.creator = kwargs.pop('creator', None)
        super().__init__(**kwargs)
        self.fields['users'].queryset = qs

    class Meta:
        model = Team
        fields = ['name', 'users']

    def save(self, commit=True):
        instance = self.get_instance()
        if commit:
            instance.save()
            self.save_m2m()
        return instance, 'users' in self.changed_data

    def get_instance(self):
        return super().save(commit=False)


class CreateTeamForm(BaseTeamForm):
    def get_instance(self):
        instance = super().get_instance()
        instance.event = self.event
        instance.creator = self.creator
        instance.confirmed = self.creator.is_assistant_for_context(self.event.context)
        instance.created_by_assistant = instance.confirmed
        return instance


class EditTeamForm(BaseTeamForm):
    pass


class AddUserForm(forms.Form):
    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(url='user-autocomplete'),
        label='Пользователи'
    )

    def __init__(self, **kwargs):
        event = kwargs.pop('event')
        self.event = event
        super().__init__(**kwargs)
        self.fields['users'].widget.forward = [forward.Const(event.id, 'event_id'), forward.Field('users')]

    def clean_users(self):
        val = self.cleaned_data.get('users')
        if val.count() > settings.MAXIMUM_EVENT_MEMBERS_TO_ADD:
            raise forms.ValidationError('Нельзя добавить более %s пользователей за раз' %
                                        settings.MAXIMUM_EVENT_MEMBERS_TO_ADD)
        if val:
            no_auth = val.filter(social_auth__isnull=True)
            if no_auth:
                raise forms.ValidationError('Следующих пользователей нельзя добавить: %s' %
                                            ', '.join(map(str, no_auth)))
        return val


class EventMaterialForm(forms.ModelForm):
    class Meta:
        model = EventOnlyMaterial
        fields = ('event_block', 'related_users', 'related_teams')
        widgets = {
            'related_users': autocomplete.ModelSelect2Multiple(
                url='event-user-autocomplete', attrs={'data-placeholder': 'Отметить людей'}
            ),
            'related_teams': autocomplete.ModelSelect2Multiple(
                url='event-team-autocomplete', attrs={'data-placeholder': 'Отметить команды'}
            ),
        }

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)
        self.fields['event_block'].empty_label = 'Блок мероприятия'
        self.fields['event_block'].queryset = EventBlock.objects.filter(event=self.event)
        self.fields['related_users'].queryset = User.objects.filter(
            id__in=EventEntry.objects.filter(event=self.event).values_list('user_id', flat=True)
        )
        self.fields['related_teams'].queryset = Team.objects.filter(event=self.event)
        self.fields['related_users'].widget.forward = [
            forward.Const(self.event.id, 'event'), forward.Field('related_users', 'exclude')
        ]
        self.fields['related_teams'].widget.forward = [
            forward.Const(self.event.id, 'event'), forward.Field('related_teams', 'exclude')
        ]
