from django import forms
from dal import autocomplete, forward
from isle.models import Team, User, EventBlock


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


EventBlockFormset = forms.modelformset_factory(
    EventBlock, form=EventBlockForm, fields=('event', 'duration', 'title', 'block_type'), extra=1,
    widgets={
        'event': forms.HiddenInput
    }
)
