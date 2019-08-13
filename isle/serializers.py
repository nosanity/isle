from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from isle.api import SSOApi, ApiError
from isle.models import User, Team, UserFile, PLEUserResult, EventOnlyMaterial, Trace, DTraceStatistics
from .utils import pull_sso_user


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


class TeamNestedserializer(serializers.BaseSerializer):
    def to_representation(self, instance):
        team = instance.team
        members = team.get_members_for_event(instance.result.block.event)
        return {
            'id': team.id,
            'name': team.name,
            'members': [i.unti_id for i in members]
        }

    def get_attribute(self, instance):
        return instance


class LabsBaseResultSerializer(serializers.Serializer):
    activity_uuid = serializers.CharField(source='result.block.event.activity.uid')
    title = serializers.CharField(source='result.title')
    event_uuid = serializers.CharField(source='result.block.event.uid')
    comment = serializers.CharField()
    approved = serializers.NullBooleanField()
    levels = serializers.JSONField(allow_null=True, source='get_meta')
    url = serializers.CharField(source='get_page_url')


class LabsUserResultSerializer(LabsBaseResultSerializer):
    files = FileSerializer(many=True, source='eventmaterial_set.all')
    user = UserNestedSerializer()


class LabsTeamResultSerializer(LabsBaseResultSerializer):
    files = FileSerializer(many=True, source='eventteammaterial_set.all')
    team = TeamNestedserializer()


class UserFieldSerializer(serializers.BaseSerializer):
    def to_internal_value(self, data):
        user = User.objects.filter(unti_id=data).first() or pull_sso_user(data)
        if not user:
            raise serializers.ValidationError(_('Пользователь с unti id %s не найден') % data)
        return user

    def to_representation(self, instance):
        return instance.unti_id


class UserFileSerializer(serializers.ModelSerializer):
    user = UserFieldSerializer()
    data = serializers.JSONField(required=False, binary=True)

    class Meta:
        model = UserFile
        exclude = ['ple_result', 'url', 'created_at', 'file_type', 'file_size']
        extra_kwargs = {
            'file': {'required': True}
        }

    def save(self, **kwargs):
        f = self.validated_data['file']
        kwargs.update({
            'file_size': f.size,
            'file_type': f.content_type,
        })
        return super().save(**kwargs)


class UserFromUntiIdSerializer(serializers.BaseSerializer):
    """
    Поле для сериализации пользователя по его unti id.
    Пытается получить пользователя из sso, если он не был найден
    """
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


class TraceSerializer(serializers.ModelSerializer):
    event_type = serializers.CharField(source='event_type.uuid')

    class Meta:
        model = Trace
        fields = ['trace_type', 'name', 'event_type', 'deleted']


class EventOnlyMaterialSerializer(serializers.ModelSerializer):
    event = serializers.CharField(source='event.uid')
    trace = TraceSerializer()

    class Meta:
        model = EventOnlyMaterial
        fields = ['id', 'url', 'file', 'file_type', 'file_size', 'created_at', 'initiator', 'deleted',
                  'comment', 'event', 'trace']


class DTraceStatisticsSerializer(serializers.ModelSerializer):
    context = serializers.CharField(source='context.uuid')
    unti_id = serializers.IntegerField(source='user.unti_id')
    leader_id = serializers.CharField(source='user.leader_id')

    class Meta:
        model = DTraceStatistics
        fields = ['context', 'unti_id', 'leader_id', 'n_entry', 'n_run_entry', 'n_personal', 'n_team',
                  'n_event', 'updated_at']
