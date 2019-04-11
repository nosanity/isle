import django_filters
from isle.models import LabsUserResult, LabsTeamResult


class LabsUserResultFilter(django_filters.FilterSet):
    created_at = django_filters.IsoDateTimeFromToRangeFilter(field_name='eventmaterial__created_at')
    unti_id = django_filters.NumberFilter(field_name='user__unti_id')

    class Meta:
        model = LabsUserResult
        fields = []


class LabsTeamResultFilter(django_filters.FilterSet):
    created_at = django_filters.IsoDateTimeFromToRangeFilter(field_name='eventteammaterial__created_at')
    team_id = django_filters.NumberFilter()

    class Meta:
        model = LabsTeamResult
        fields = []
