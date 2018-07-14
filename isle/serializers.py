from rest_framework import serializers


class AttendanceSerializer(serializers.Serializer):
    unti_id = serializers.IntegerField(source='user.unti_id')
    event_id = serializers.IntegerField(source='event.ext_id')
    created_on = serializers.DateTimeField()
    updated_on = serializers.DateTimeField()
    is_confirmed = serializers.BooleanField()
    confirmed_by_user = serializers.SerializerMethodField(source='get_confirmed_by_user', allow_null=True)
    confirmed_by_system = serializers.CharField()
    run_id = serializers.SerializerMethodField(source='get_run_id')
    activity_id = serializers.SerializerMethodField(source='get_activity_id')

    def get_confirmed_by_user(self, obj):
        if obj.confirmed_by_user:
            return obj.confirmed_by_user.unti_id

    def get_run_id(self, obj):
        data = obj.event.data or {}
        return data.get('run', {}).get('ext_id')

    def get_activity_id(self, obj):
        data = obj.event.data or {}
        return data.get('activity', {}).get('ext_id')
