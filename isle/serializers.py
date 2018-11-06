from rest_framework import serializers


class AttendanceSerializer(serializers.Serializer):
    unti_id = serializers.IntegerField(source='user.unti_id')
    event_uuid = serializers.IntegerField(source='event.uid')
    created_on = serializers.DateTimeField()
    updated_on = serializers.DateTimeField()
    is_confirmed = serializers.BooleanField()
    confirmed_by_user = serializers.SerializerMethodField(source='get_confirmed_by_user', allow_null=True)
    confirmed_by_system = serializers.CharField()

    def get_confirmed_by_user(self, obj):
        if obj.confirmed_by_user:
            return obj.confirmed_by_user.unti_id
