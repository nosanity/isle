from rest_framework import serializers
from isle.models import User, Team


class AttendanceSerializer(serializers.Serializer):
    unti_id = serializers.IntegerField(source='user.unti_id')
    event_uuid = serializers.CharField(source='event.uid')
    created_on = serializers.DateTimeField()
    updated_on = serializers.DateTimeField()
    is_confirmed = serializers.BooleanField()
    confirmed_by_user = serializers.SerializerMethodField(source='get_confirmed_by_user', allow_null=True)
    confirmed_by_system = serializers.CharField()

    def get_confirmed_by_user(self, obj):
        if obj.confirmed_by_user:
            return obj.confirmed_by_user.unti_id


class FileSerializer(serializers.Serializer):
    file_url = serializers.CharField(source='get_url')
    file_name = serializers.CharField(source='get_file_name')


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
