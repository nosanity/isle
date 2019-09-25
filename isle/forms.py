from django import forms
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils import six
from django.utils.translation import ugettext_lazy as _
from dal import autocomplete, forward
from dal_genericm2m.fields import GenericM2MFieldMixin
from dal_select2_queryset_sequence.fields import QuerySetSequence, QuerySetSequenceModelField
from dal_select2_queryset_sequence.widgets import QuerySetSequenceSelect2
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


class GenericUserTeamField(GenericM2MFieldMixin, QuerySetSequenceModelField):
    """
    GenericField, считающий для объектов User основным полем unti_id вместо id
    """
    def to_python(self, value):
        if not value:
            return value

        content_type_id, object_id = self.get_content_type_id_object_id(value)
        queryset = self.get_queryset_for_content_type(content_type_id)

        if queryset is None:
            self.raise_invalid_choice()

        try:
            if queryset.model is User:
                return queryset.get(unti_id=object_id)
            return queryset.get(pk=object_id)
        except (queryset.model.DoesNotExist, queryset.model.MultipleObjectsReturned):
            self.raise_invalid_choice()

    def prepare_value(self, value):
        if not value:
            return ''

        if isinstance(value, six.string_types):
            if value.split('-')[0] == str(ContentType.objects.get_for_model(User).id):
                user = User.objects.filter(unti_id=value.split('-')[1]).first()
                value = '{}-{}'.format(value.split('-')[0], user.id) if user else ''
            return value

        return '%s-%s' % (ContentType.objects.get_for_model(value).pk,
                          value.unti_id if isinstance(value, User) else value.pk)


class UserOrTeamUploadAutocompleteBase(forms.Form):
    item = GenericUserTeamField(
        queryset=QuerySetSequence(
            User.objects.all(),
            Team.objects.all(),
        ),
        required=False,
        widget=QuerySetSequenceSelect2('team-and-user-autocomplete',
                                       attrs={'data-placeholder': _('Пользователь или команда'),
                                              'class': 'user-or-team-autocomplete-selector'})
    )

    def __init__(self, **kwargs):
        event = kwargs.pop('event')
        super().__init__(**kwargs)
        self.event = event
        self.fields['item'].widget.forward = [forward.Const(self.event.id, 'event')]


class UserOrTeamUploadAutocomplete(UserOrTeamUploadAutocompleteBase):
    """
    форма с полем пользователь/команда для использования в форме загрузки
    """
    def __init__(self, **kwargs):
        result = kwargs.pop('result')
        super().__init__(**kwargs)
        self.fields['item'].widget.forward.append(forward.Const('upload', 'format'))
        if result.result_format == 'personal':
            self.fields['item'].queryset = QuerySetSequence(User.objects.all())
            self.fields['item'].widget.forward.append(forward.Const('user', 'type'))
        elif result.result_format == 'group':
            self.fields['item'].queryset = QuerySetSequence(Team.objects.all())
            self.fields['item'].widget.forward.append(forward.Const('team', 'type'))


class EventDTraceFilter(UserOrTeamUploadAutocompleteBase):
    """
    форма для фильтрации результатов на странице общих результатов мероприятия
    """
    APPROVED_ANY = 0
    APPROVED_TRUE = 1
    APPROVED_FALSE = 2
    APPROVED_NONE = 3

    field_order = ['only_my', 'search', 'item']

    only_my = forms.BooleanField(widget=forms.CheckboxInput, label=_('Показывать только мой след'), required=False)
    search = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={'placeholder': _('Найти')}))

    def clean(self):
        data = super().clean()
        if data.get('only_my') and data.get('item'):
            self.add_error('item', forms.ValidationError(_('Нельзя выбрать одновременно с опцией "{}"')
                                                         .format(self.fields['only_my'].label)))
        return data


class EventDTraceAdminFilter(EventDTraceFilter):
    """
    форма для фильтрации результатов на странице общих результатов мероприятия - вид для ассистента
    """
    field_order = ['only_my', 'search', 'approved', 'item']

    approved = forms.IntegerField(widget=forms.Select(choices=(
        (EventDTraceFilter.APPROVED_ANY, _('Любой статус валидности')),
        (EventDTraceFilter.APPROVED_TRUE, _('Валидный')),
        (EventDTraceFilter.APPROVED_FALSE, _('Невалидный')),
        (EventDTraceFilter.APPROVED_NONE, _('Не валидирован')),
    )), required=False)
