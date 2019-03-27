from django import forms
from django.conf import settings
from dal import autocomplete, forward
from social_django.models import UserSocialAuth
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
        instance.confirmed = self.creator.is_assistant
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


class EventBlockForm(forms.ModelForm):
    class Meta:
        model = EventBlock
        fields = ('event', 'duration', 'title', 'block_type')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['event'].required = False
        self.fields['duration'].widget.attrs['min'] = 1
        # замена дефолтного варианта ('', '----') на вариант с нужным текстом
        self.fields['block_type'].choices.pop(0)
        self.fields['block_type'].choices = [('', 'Тип блока')] + list(self.fields['block_type'].choices)


class BaseResultForm:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['rating'].choices.pop(0)
        self.fields['rating'].choices = [('', 'Оценка')] + list(self.fields['rating'].choices)


class UserResultForm(BaseResultForm, forms.ModelForm):
    class Meta:
        model = UserResult
        fields = '__all__'
        widgets = {
            'result_type': autocomplete.Select2(url='result-type-autocomplete', forward=['event'],
                                                attrs={'data-placeholder': 'Тип результата'}),
            'event': forms.HiddenInput,
            'user': forms.HiddenInput,
            'result_comment': forms.Textarea,
        }


class TeamResultForm(BaseResultForm, forms.ModelForm):
    class Meta:
        model = TeamResult
        fields = ('event', 'team', 'result_type', 'rating', 'competences', 'group_dynamics', 'result_comment', )
        widgets = {
            'result_type': autocomplete.Select2(url='result-type-autocomplete', forward=['event'],
                                                attrs={'data-placeholder': 'Тип результата'}),
            'event': forms.HiddenInput,
            'team': forms.HiddenInput,
            'result_comment': forms.Textarea,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        fs_kwargs = {
            'initial': UserRole.get_initial_data_for_team_result(self.initial.get('team'), serializable=False),
            'data': kwargs.get('data', {})
        }
        self.user_roles = UserRoleFormset(**fs_kwargs)

    def is_valid(self):
        if not super().is_valid():
            return False
        return self.user_roles.is_valid(self.cleaned_data.get('team'))

    def save(self, commit=True):
        if commit:
            instance = super().save(commit)
            self.user_roles.save(instance)
            return instance
        return super().save(commit)


class UserRoleForm(forms.ModelForm):
    class Meta:
        model = UserRole
        fields = '__all__'
        widgets = {
            'team_result': forms.HiddenInput,
            'user': forms.HiddenInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].choices.pop(0)
        self.fields['role'].choices = [('', 'Роль')] + list(self.fields['role'].choices)
        self.fields['team_result'].required = False

_UserRoleFormset = forms.formset_factory(UserRoleForm, extra=0, can_delete=False, min_num=1)


class UserRoleFormset(_UserRoleFormset):
    def is_valid(self, team=None):
        if not super().is_valid() or not team:
            return False
        allowed_users = set(team.users.values_list('id', flat=True))
        for form in self.forms:
            if form.cleaned_data.get('user').id not in allowed_users:
                return False
        return True

    def save(self, team_result=None):
        for form in self.forms:
            UserRole.objects.update_or_create(
                user=form.cleaned_data.get('user'),
                team_result=form.cleaned_data.get('team_result') or team_result,
                defaults={'role': form.cleaned_data.get('role')}
            )


EventBlockFormset = forms.modelformset_factory(
    EventBlock, form=EventBlockForm, fields=('event', 'duration', 'title', 'block_type'), extra=1,
    widgets={
        'event': forms.HiddenInput
    }
)


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
