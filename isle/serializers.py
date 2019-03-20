from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from isle.api import SSOApi, ApiError
from isle.models import User, EventEntry, PLEUserResult


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


class UserFromUntiIdSerializer(serializers.BaseSerializer):
    def get_user(self, data, raise_exception=True):
        try:
            return User.objects.get(unti_id=data)
        except User.DoesNotExist:
            if raise_exception:
                raise ValidationError(_('Пользователь с unti_id "{}" не найден').format(data))

    def create_user(self, data):
        try:
            SSOApi().push_user_to_uploads(data)
        except ApiError:
            pass

    def to_internal_value(self, data):
        user = self.get_user(data, raise_exception=False)
        if not user:
            self.create_user(data)
            user = self.get_user(data)
        return user

    def to_representation(self, instance):
        return instance.unti_id


class UserMaterialSerializer(serializers.Serializer):
    url = serializers.URLField(required=False)
    file = serializers.URLField(required=False)

    def is_valid(self, raise_exception=False):
        super().is_valid(raise_exception=False)
        url = self._validated_data.get('url')
        file_ = self._validated_data.get('file')
        if bool(url) != bool(file_):
            self._errors['__all__'] = _('Должен быть указан или url или file')
        if self._errors and raise_exception:
            raise ValidationError(self.errors)
        return not bool(self._errors)


class UserResultSerializer(serializers.ModelSerializer):
    """
    сериализатор для валидации запроса на создание пользовательского результата
    """
    user = UserFromUntiIdSerializer(required=True)
    materials = UserMaterialSerializer(required=True, many=True)
    meta = serializers.JSONField(required=True, binary=True)
    callback_url = serializers.URLField(required=True)

    def is_valid(self, raise_exception=False):
        super().is_valid(raise_exception=False)
        files = self._validated_data.get('files')
        if isinstance(files, list) and len(files) == 0:
            self._errors['files'] = _('Массив не должен быть пустым')
        if self._errors and raise_exception:
            raise ValidationError(self.errors)
        return not bool(self._errors)

    class Meta:
        model = PLEUserResult
        fields = ['user', 'comment', 'meta', 'materials', 'callback_url']
        extra_kwargs = {
            'comment': {'allow_blank': True},
        }
