from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers
from isle.models import User, Team


class AttendanceSerializer(serializers.Serializer):
    unti_id = serializers.IntegerField(source='user.unti_id', help_text=_('unti_id пользователя'))
    event_uuid = serializers.CharField(source='event.uid', help_text=_('uuid мероприятия'))
    created_on = serializers.DateTimeField(required=False, help_text=_('auto created'))
    updated_on = serializers.DateTimeField(required=False, help_text=_('auto created'))
    is_confirmed = serializers.BooleanField(help_text=_('подтверджено ли присутстие пользователя'))
    confirmed_by_user = serializers.SerializerMethodField(
        source='get_confirmed_by_user', allow_null=True, required=False,
        help_text=_('unti_id пользователя, подтвердивщего присутствие')
    )
    confirmed_by_system = serializers.CharField(required=False, help_text=_('auto created'))

    def get_confirmed_by_user(self, obj):
        if obj.confirmed_by_user:
            return obj.confirmed_by_user.unti_id


class FileSerializer(serializers.Serializer):
    file_url = serializers.CharField(source='get_url')
    file_name = serializers.CharField(source='get_file_name')
    created_at = serializers.DateTimeField(allow_null=True)


class UserNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['unti_id']


class TeamMembersSerializer(serializers.BaseSerializer):
    def to_representation(self, instance):
        return instance.unti_id


class TeamNestedserializer(serializers.ModelSerializer):
    members = TeamMembersSerializer(many=True, source='users.all')

    class Meta:
        model = Team
        fields = ['id', 'name', 'members']


class LabsBaseResultSerializer(serializers.Serializer):
    event_uuid = serializers.CharField(source='result.block.event.uid')
    comment = serializers.CharField()
    approved = serializers.BooleanField()
    levels = serializers.JSONField(allow_null=True, source='result.meta')
    url = serializers.CharField(source='get_page_url')


class LabsUserResultSerializer(LabsBaseResultSerializer):
    files = FileSerializer(many=True, source='eventmaterial_set.all')
    user = UserNestedSerializer()


class LabsTeamResultSerializer(LabsBaseResultSerializer):
    files = FileSerializer(many=True, source='eventteammaterial_set.all')
    team = TeamNestedserializer()
