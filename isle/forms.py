from django import forms
from isle.models import Team


class CreateTeamForm(forms.ModelForm):
    def __init__(self, **kwargs):
        qs = kwargs.pop('users_qs')
        self.event = kwargs.pop('event')
        super().__init__(**kwargs)
        self.fields['users'].queryset = qs

    class Meta:
        model = Team
        fields = ['name', 'users']

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.event = self.event
        instance.save()
        self.save_m2m()
