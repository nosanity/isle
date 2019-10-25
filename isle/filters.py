import django_filters
from isle.models import LabsUserResult, LabsTeamResult


class LabsUserResultFilter(django_filters.FilterSet):
    created_at = django_filters.IsoDateTimeFromToRangeFilter(field_name='eventmaterial__created_at')
    unti_id = django_filters.NumberFilter(field_name='user__unti_id', required=False)

    class Meta:
        model = LabsUserResult
        fields = []


class LabsTeamResultFilter(django_filters.FilterSet):
    created_at = django_filters.IsoDateTimeFromToRangeFilter(field_name='eventteammaterial__created_at')
    team_id = django_filters.NumberFilter(required=False)

    class Meta:
        model = LabsTeamResult
        fields = []


class StatisticsFilter(django_filters.FilterSet):
    unti_id = django_filters.NumberFilter(required=False, field_name='user__unti_id')
    leader_id = django_filters.CharFilter(required=False, field_name='user__leader_id')
