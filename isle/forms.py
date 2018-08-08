from django import forms
from dal import autocomplete, forward
from isle.models import Team, User, EventBlock, BlockType, UserResult, TeamResult, UserRole


class CreateTeamForm(forms.ModelForm):
    def __init__(self, **kwargs):
        qs = kwargs.pop('users_qs')
        self.event = kwargs.pop('event')
        self.creator = kwargs.pop('creator')
        super().__init__(**kwargs)
        self.fields['users'].queryset = qs

    class Meta:
        model = Team
        fields = ['name', 'users']

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.event = self.event
        instance.creator = self.creator
        instance.confirmed = self.creator.is_assistant
        instance.save()
        self.save_m2m()


class AddUserForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.all(),
                                  widget=autocomplete.ModelSelect2(url='user-autocomplete'),
                                  label='Пользователь')

    def __init__(self, **kwargs):
        event = kwargs.pop('event')
        super().__init__(**kwargs)
        self.fields['user'].widget.forward = [forward.Const(event.id, 'event_id')]


class EventBlockForm(forms.ModelForm):
    class Meta:
        model = EventBlock
        fields = ('event', 'duration', 'title', 'block_type')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['event'].required = False
        self.fields['duration'].min_value = 0


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
