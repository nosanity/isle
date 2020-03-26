import hashlib
import json
import os
import pytz
import re
import urllib
from collections import defaultdict
from functools import reduce
from uuid import uuid4
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.deconstruct import deconstructible
from django.utils.functional import cached_property
from django.utils.html import strip_tags
from django.utils.translation import ugettext_lazy as _
import bleach
from jsonfield import JSONField
from .cache import get_user_available_contexts
from .fields import SafeUTF8Text


def check_permission(user, context, obj_type='file', action='upload'):
    from .casbin import enforce
    if not user.unti_id or not context:
        return False
    return enforce(str(user.unti_id), context, obj_type, action)


class User(AbstractUser):
    second_name = models.CharField(max_length=50)
    icon = JSONField()
    is_assistant = models.BooleanField(default=False)
    unti_id = models.PositiveIntegerField(null=True, db_index=True)
    leader_id = models.CharField(max_length=255, default='')
    chosen_context = models.ForeignKey('Context', on_delete=models.SET_NULL, null=True, default=None)

    class Meta:
        verbose_name = _(u'Пользователь')
        verbose_name_plural = _(u'Пользователи')

    def __str__(self):
        return '%s %s' % (self.leader_id, self.get_full_name())

    @property
    def fio(self):
        return ' '.join(filter(None, [self.last_name, self.first_name, self.second_name]))

    def get_full_name(self):
        return ' '.join(filter(None, [self.last_name, self.first_name]))

    def is_assistant_for_context(self, context):
        context_uuid = context if isinstance(context, str) else context and context.uuid
        return check_permission(self, context_uuid)

    def has_assistant_role(self):
        return bool(self.available_context_uuids)

    @cached_property
    def available_context_uuids(self):
        return get_user_available_contexts(self)


class EventType(models.Model):
    ext_id = models.PositiveIntegerField(verbose_name='Внешний id', null=True)
    uuid = models.CharField(max_length=36)
    title = models.CharField(max_length=500, verbose_name='Название')
    description = models.TextField(verbose_name='Описание', blank=True, default='')
    visible = models.BooleanField(verbose_name='Отображать в списке мероприятий', default=True)
    trace_data = JSONField(blank=True, help_text='JSON в виде списка из объектов с ключами trace_type и name. '
                                                 'Например, [{"trace_type": "Презентация", "name": '
                                                 '"Презентация продукта"}]')

    class Meta:
        verbose_name = 'Тип мероприятия'
        verbose_name_plural = 'Типы мероприятия'

    def __str__(self):
        return self.title


class Author(models.Model):
    title = models.CharField(max_length=1000)
    uuid = models.CharField(max_length=50, unique=True)
    is_main = models.NullBooleanField()


class Activity(models.Model):
    uid = models.CharField(max_length=255, unique=True)
    ext_id = models.PositiveIntegerField(default=None, verbose_name='id в LABS', db_index=True, null=True)
    title = models.CharField(max_length=1000)
    main_author = models.CharField(max_length=500, default='')
    is_deleted = models.BooleanField(default=False, verbose_name=_(u'Удалено'))
    authors = models.ManyToManyField(Author)

    def get_labs_link(self):
        return '{}/admin/activity/view/{}'.format(settings.LABS_URL.rstrip('/'), self.uid)

    def get_authors(self):
        return list(self.authors.values_list('title', flat=True))


class NotDeletedEntries(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted=False)


class Run(models.Model):
    uuid = models.CharField(max_length=50, unique=True)
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE)
    deleted = models.BooleanField(default=False)


class RunEnrollment(models.Model):
    run = models.ForeignKey(Run, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    deleted = models.BooleanField(default=False)
    created = models.DateTimeField(null=True, auto_now_add=True)

    objects = NotDeletedEntries()
    all_objects = models.Manager()

    class Meta:
        unique_together = ('run', 'user')


class ActivityEnrollment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'activity')


class Context(models.Model):
    timezone = models.CharField(max_length=255)
    uuid = models.CharField(max_length=255, unique=True)
    title = models.CharField(max_length=500, default='')
    guid = models.CharField(max_length=500, default='')


class Event(models.Model):
    uid = models.CharField(max_length=255, unique=True, verbose_name=_(u'UID события'))
    data = JSONField()
    is_active = models.BooleanField(default=False, verbose_name=_(u'Доступно для оцифровки'))
    dt_start = models.DateTimeField(verbose_name=_(u'Время начала'))
    dt_end = models.DateTimeField(verbose_name=_(u'Время окончания'))
    title = models.CharField(max_length=1000, default='', verbose_name='Название')
    event_type = models.ForeignKey(EventType, on_delete=models.SET_NULL, verbose_name='Тип мероприятия',
                                   blank=True, null=True, default=None)
    ext_id = models.PositiveIntegerField(default=None, verbose_name='id в LABS', null=True)

    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, default=None, null=True)
    context = models.ForeignKey(Context, on_delete=models.SET_NULL, null=True, default=None)
    run = models.ForeignKey(Run, on_delete=models.CASCADE, null=True, default=None)

    class Meta:
        verbose_name = _(u'Событие')
        verbose_name_plural = _(u'События')

    def __str__(self):
        fmt = '%H:%M %d.%m.%Y'
        if self.dt_start and self.dt_end:
            start = timezone.localtime(self.dt_start)
            end = timezone.localtime(self.dt_end)
            return '%s (%s - %s)' % (self.title or self.uid, start.strftime(fmt), end.strftime(fmt))
        return self.uid

    def get_dt_start(self):
        return self._get_dt('dt_start')

    def get_dt_end(self):
        return self._get_dt('dt_end')

    def _get_dt(self, dt_field_name):
        val = getattr(self, dt_field_name)
        if not val:
            return
        default = timezone.get_default_timezone()
        if not self.context_id:
            return val.astimezone(default)
        try:
            tz = pytz.timezone(self.context.timezone)
        except pytz.UnknownTimeZoneError:
            tz = default
        return val.astimezone(tz)

    def get_traces(self):
        traces = self.trace_set.order_by('name')
        if not traces and self.event_type is not None:
            events = self.event_type.trace_data or []
            order = {j['name']: i for i, j in enumerate(events)}
            traces = Trace.objects.filter(event_type=self.event_type)
            return sorted(traces, key=lambda x: order.get(x.name, 0))
        return Trace.objects.none()

    def get_event_structure_trace(self):
        """
        попытка выбрать трейс со структурой эвента
        """
        traces = list(filter(lambda x: re.search(r'разметк(а|и)', x.name.lower()), self.get_traces()))
        return traces and traces[0]

    @property
    def entry_count(self):
        return EventEntry.objects.filter(event=self).count()

    @property
    def trace_count(self):
        return EventMaterial.objects.filter(event=self).count() + EventTeamMaterial.objects.filter(event=self).count() + EventOnlyMaterial.objects.filter(event=self).count()

    @cached_property
    def event_only_material_count(self):
        return EventOnlyMaterial.objects.filter(event=self).count()

    def get_authors(self):
        if self.activity:
            return self.activity.get_authors()
        return []

    @cached_property
    def get_results(self):
        return EventBlock.objects.filter(event=self).order_by('id')

    def get_xle_link(self):
        return '{}/event/{}'.format(settings.XLE_URL.rstrip('/'), self.uid)

    def get_pt_teams(self, user_ids=None):
        """
        Команды, полученные из pt, которые должны отображаться на странице мероприятия.
        Если соответствующая настройка отключена показываются только те, для которых есть загруженный след
        """
        if self.context:
            user_ids = user_ids or self.get_participant_ids()
            filter_dict = {
                'system': Team.SYSTEM_PT,
                'contexts': self.context,
                'users__id__in': user_ids,
            }
            qs = Team.objects.filter(**filter_dict)
            if not settings.ENABLE_PT_TEAMS:
                qs = qs.annotate(
                    material_cnt=models.Count('eventteammaterial',
                                              filter=models.Q(id__in=list(qs.values_list('id', flat=True))))).filter(
                    material_cnt__gt=0
                )
            return qs.distinct().prefetch_related('users')
        return Team.objects.none()

    def get_participant_ids(self):
        ids = set(EventEntry.objects.filter(event=self).values_list('user_id', flat=True))
        if self.run_id:
            ids |= set(RunEnrollment.objects.filter(run_id=self.run_id).values_list('user_id', flat=True))
        return ids

    def get_participants(self):
        return User.objects.filter(id__in=self.get_participant_ids())\
            .order_by('last_name', 'first_name', 'second_name')


class BlockType:
    type_choices = (
        (1, r'Лекция с вопросами из зала'),
        (3, r'Лекция с проверкой усвоения'),
        (4, r'Мастер-класс/освоение инструмента'),
        (5, r'Мастер-класс\тренинг без фиксации'),
        (6, r'Работа над проектами \ групповая работа'),
        (7, r'Решение кейсов'),
        (8, r'Стратегическая сессия \ форсайт'),
        (9, r'Игра \ модельная сессия'),
        (10, r'Хакатон \ дизайн сессия'),
        (11, r'Нетворкинг - сессия'),
        (12, r'Обсуждение \ дискуссия'),
        (13, r'Питч сессия \ презентация результатов'),
        (14, r'Проведение эксперимента'),
        (15, r'Менторская \ тьюторская сессия'),
        (16, r'Другое'),
    )

    result_types = (
        (1, 'Автор интересных вопросов'),
        (2, 'Другое'),
        (3, 'Результаты тестов'),
        (4, 'Результат выполнения'),
        (5, 'Лидер мнений'),
        (6, 'Презентация с оценкой ведущего'),
        (7, 'Результаты эксперимента'),
        (8, 'Обратная связь участников (start-stop-continue)'),
        (9, 'Обратная связь тьютора\ментора (start-stop-continue)')
    )

    @classmethod
    def filter(cls, types):
        return [i for i in cls.type_choices if i[0] in types]

    @classmethod
    def in_event(cls, event, block_type):
        return EventBlock.objects.filter(event=event, block_type=block_type).exists()

    @classmethod
    def map_to_result_type(cls, t):
        return {
            1: [1, 2],
            3: [3, 2],
            4: [4, 2],
            5: [4, 2],
            6: [4, 2],
            7: [4, 2],
            8: [4, 2],
            9: [4, 2],
            10: [4, 2],
            11: [2],
            12: [5, 2],
            13: [6, 2],
            14: [7, 2],
            15: [8, 9, 2]
        }.get(t, [])

    @classmethod
    def result_types_for_event(cls, event):
        block_types = EventBlock.objects.filter(event=event).values_list('block_type', flat=True)
        result_types = []
        for x in block_types:
            result_types.extend(cls.map_to_result_type(x))
        result_types = sorted(set(result_types))
        return [item for item in cls.result_types if item[0] in result_types]


class EventBlock(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    duration = models.IntegerField(verbose_name='Минут')
    title = models.CharField(max_length=255, verbose_name='Название блока')
    block_type = models.SmallIntegerField(choices=BlockType.type_choices)

    def __str__(self):
        return '{} - {} - {}'.format(self.duration, self.title, self.get_block_type_display())


class Trace(models.Model):
    """
    Модель результата эвента. Удаление результата не предполагается, может только меняться
    список эвентов, к которым он относится.
    """
    events = models.ManyToManyField(Event, blank=True, verbose_name='События')
    ext_id = models.PositiveIntegerField(db_index=True, null=True, blank=True)
    trace_type = models.CharField(max_length=255, db_index=True, verbose_name='Тип')
    name = models.TextField(default='', verbose_name='Название')
    event_type = models.ForeignKey(EventType, on_delete=models.SET_NULL, verbose_name='Тип мероприятия',
                                   blank=True, null=True, default=None)
    deleted = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Результат'
        verbose_name_plural = 'Результаты'

    def __str__(self):
        return self.name


class EventEntry(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now=True)
    added_by_assistant = models.BooleanField(default=False, verbose_name='Добавлен вручную')
    check_in_pushed = models.BooleanField(default=False, verbose_name='Чекин проставлен в ILE')
    deleted = models.BooleanField(default=False)
    approve_text = models.TextField(verbose_name='Подтверждающий текст', blank=True, default='')
    self_enrolled = models.BooleanField(default=False)

    objects = NotDeletedEntries()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _(u'Запись пользователя')
        verbose_name_plural = _(u'Записи пользователей')
        unique_together = ('user', 'event')

    def __str__(self):
        return '%s - %s' % (self.event, self.user)

    def approved(self):
        return self.is_active or Attendance.objects.filter(user=self.user, event=self.event, is_confirmed=True)


class Attendance(models.Model):
    SYSTEM_UPLOADS = 'uploads'
    SYSTEM_CHAT_BOT = 'chat_bot'
    SYSTEMS = (
        (SYSTEM_UPLOADS, SYSTEM_UPLOADS),
        (SYSTEM_CHAT_BOT, SYSTEM_CHAT_BOT)
    )

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    confirmed_by_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='confirmed_by_user', null=True)
    confirmed_by_system = models.CharField(max_length=255, choices=SYSTEMS)
    is_confirmed = models.BooleanField()

    class Meta:
        unique_together = ('event', 'user')


class ResultAbstract(models.Model):
    RESULT_WEAK = 1
    RESULT_OK = 2
    RESULT_GREAT = 3
    RESULT_CHOICES = (
        (RESULT_WEAK, '1 – слабый результат'),
        (RESULT_OK, '2 – нормальный результат'),
        (RESULT_GREAT, '3 – отличный результат'),
    )

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    result_type = models.SmallIntegerField(choices=BlockType.result_types, null=True, blank=True,
                                           verbose_name='Тип результата')
    rating = models.SmallIntegerField(choices=RESULT_CHOICES, null=True, blank=True, verbose_name='Оценка')
    competences = models.CharField(max_length=300, default='', blank=True,
                                   verbose_name='Продемонстрированные компетенции')
    result_comment = models.CharField(max_length=1000, default='', blank=True, verbose_name='Комментарии сборщика')

    class Meta:
        abstract = True

    def to_json(self, as_object=False):
        res = {}
        for f in self._meta.fields:
            if getattr(f, 'choices', None):
                res['{}_display'.format(f.name)] = getattr(self, 'get_{}_display'.format(f.name))() or ''
                res[f.name] = getattr(self, f.name)
            elif isinstance(f, models.ForeignKey):
                res[f.name] = getattr(self, '{}_id'.format(f.name)) or ''
            else:
                res[f.name] = getattr(self, f.name) or ''
        for f in self._meta.many_to_many:
            self.handle_m2m(res, f.name)
        if as_object:
            return res
        return json.dumps(res, ensure_ascii=False)

    def handle_m2m(self, res, field):
        pass


class UserResult(ResultAbstract):
    """
    результат пользователя по какому-то типу блока (не по самому блоку), к которому крепятся файлы
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)


class UserRole(models.Model):
    """
    роль пользователя в рамках команды
    """
    ROLE_LEADER = 1
    ROLE_PARTICIPANT = 2
    ROLE_CHOICES = (
        (ROLE_LEADER, 'Лидер'),
        (ROLE_PARTICIPANT, 'Участник'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    team_result = models.ForeignKey('TeamResult', on_delete=models.CASCADE)
    role = models.SmallIntegerField(choices=ROLE_CHOICES, blank=True, null=True)

    class Meta:
        unique_together = ('user', 'team_result')

    @classmethod
    def get_initial_data_for_team_result(cls, team, team_result_id=None, serializable=True):
        """
        получение данных для initial параметра формсета с ролями или для логирования состояния
        """
        users = team.users.order_by('last_name', 'first_name', 'second_name')
        if team_result_id:
            roles = dict(cls.objects.filter(team_result_id=team_result_id, user__in=users).
                         values_list('user_id', 'role'))
        else:
            roles = {}
        return [
            {'user': user.id if serializable else user, 'team_result': team_result_id, 'role': roles.get(user.id)}
            for user in users
        ]


class TeamResult(ResultAbstract):
    team = models.ForeignKey('Team', on_delete=models.CASCADE)
    group_dynamics = models.CharField(max_length=300, verbose_name='Групповая динамика', blank=True, default='')
    user_roles = models.ManyToManyField(User, through=UserRole)

    def handle_m2m(self, res, field_name):
        if field_name == 'user_roles':
            res[field_name] = UserRole.get_initial_data_for_team_result(self.team, self.id)


class BaseMaterial(models.Model):
    url = models.URLField(blank=True, max_length=1000)
    file = models.FileField(blank=True, max_length=300)
    file_type = models.CharField(max_length=1000, default='')
    file_size = models.PositiveIntegerField(default=None, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        abstract = True

    def get_url(self):
        if self.url:
            return self.url
        elif self.file:
            if self.file.url.startswith('/'):
                return '{}{}'.format(settings.BASE_URL, self.file.url)
            return self.file.url


class AbstractMaterial(BaseMaterial):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    trace = models.ForeignKey(Trace, on_delete=models.CASCADE, null=True, default=None)
    initiator = models.PositiveIntegerField(blank=True, null=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, default=None)
    object_id = models.PositiveIntegerField(null=True, default=None)
    parent = GenericForeignKey()
    deleted = models.BooleanField(default=False)
    summary = models.ForeignKey('Summary', on_delete=models.CASCADE, null=True, blank=True, default=None)

    objects = NotDeletedEntries()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def get_file_name(self):
        if self.url:
            s = self.url
        elif self.file:
            s = self.file.name
        else:
            return ''
        return urllib.parse.urlparse(s).path.rstrip('/').split('/')[-1]

    def get_extension(self):
        name = self.get_file_name()
        if '.' in name:
            return name.split('.')[-1]

    def get_name(self):
        if self.file:
            return urllib.parse.unquote(os.path.basename(self.file.url))
        return self.url

    def __str__(self):
        return '%s %s' % (self.get_initiator_user() or '', self.get_url())

    def get_owners(self):
        if hasattr(self, 'owners'):
            return [i.fio for i in self.owners.all()]
        return []

    def get_initiator_user(self):
        if hasattr(self, 'initiator_user'):
            return self.initiator_user
        try:
            initiator_user = User.objects.filter(unti_id=self.initiator).first()
        except:
            initiator_user = None
        self.initiator_user = initiator_user
        return self.initiator_user

    def get_metadata(self):
        initiator_user = self.get_initiator_user()
        file_type, icon = self.get_file_type_and_icon()
        return {
            'fio': initiator_user and initiator_user.fio or '',
            'file_type': file_type,
            'icon': icon,
            'size': self.file_size or '',
            'created': self.created_at and self.created_at.isoformat() or '',
        }

    def render_metadata(self):
        parts = ['data-{}="{}"'.format(k, v) for k, v in self.get_metadata().items()]
        return ' '.join(parts)

    def get_file_type_and_icon(self):
        if self.file_type:
            if self.file_type.startswith('image'):
                return 'image', 'fa-picture-o'
            if self.file_type.startswith('audio'):
                return 'audio', 'fa-file-audio-o'
            if self.file_type.startswith('video'):
                return 'video', 'fa-file-video-o'
            if 'pdf' in self.file_type:
                return 'pdf', 'fa-file-pdf-o'
        return 'other', 'fa-file'

    def get_summary(self):
        if self.summary_id:
            return self.summary.content

    def get_short_summary(self):
        if self.summary_id:
            return self.summary.get_short_content()


class EventMaterial(AbstractMaterial):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    is_public = models.BooleanField(default=False)
    comment = models.CharField(default='', max_length=255)
    result = models.ForeignKey(UserResult, on_delete=models.CASCADE, null=True, default=None)
    result_v2 = models.ForeignKey('LabsUserResult', on_delete=models.SET_NULL, null=True, default=None)
    loaded_by_assistant = models.BooleanField(default=False)

    class Meta:
        verbose_name = _(u'Материал')
        verbose_name_plural = _(u'Материалы')

    @classmethod
    def copy_from_object(cls, material, user):
        """
        перемещение материалов мероприятия пользователю
        """
        if not isinstance(material, EventOnlyMaterial):
            raise NotImplementedError
        new_obj = cls.objects.create(
            user=user,
            event=material.event,
            url=material.url,
            file=material.file,
            trace=material.trace,
            initiator=material.initiator,
            comment=material.comment,
            file_type=material.file_type,
            file_size=material.file_size,
            parent=material,
        )
        EventOnlyMaterial.objects.filter(id=material.id).update(deleted=True)
        return new_obj

    def get_page_url(self):
        return '{}{}'.format(
            settings.BASE_URL,
            reverse('load-materials', kwargs={'uid': self.event.uid, 'unti_id': self.user.unti_id})
        )


class Team(models.Model):
    SYSTEM_UPLOADS = 0
    SYSTEM_PT = 1

    event = models.ForeignKey(Event, on_delete=models.CASCADE, verbose_name='Событие', null=True)
    contexts = models.ManyToManyField(Context)
    users = models.ManyToManyField(User, verbose_name='Студенты')
    name = models.CharField(max_length=500, verbose_name='Название команды')
    creator = models.ForeignKey(User, on_delete=models.CASCADE, null=True, default=None, related_name='team_creator')
    confirmed = models.BooleanField(default=True)
    created_by_assistant = models.BooleanField(default=False)
    system = models.SmallIntegerField(choices=(
        (SYSTEM_UPLOADS, SYSTEM_UPLOADS),
        (SYSTEM_PT, SYSTEM_PT),
    ), default=SYSTEM_UPLOADS)
    uuid = models.CharField(max_length=50, default='')

    @property
    def team_name(self):
        return 'team_{}'.format(self.id)

    def get_traces_number_for_event(self, event):
        return EventTeamMaterial.objects.filter(team=self, event=event).count()

    class Meta:
        verbose_name = 'Команда'
        verbose_name_plural = 'Команды'
        unique_together = ('system', 'uuid')

    def __str__(self):
        return self.name

    def user_can_edit_team(self, user):
        if self.system != self.SYSTEM_UPLOADS:
            return False
        return user.is_assistant_for_context(self.event.context) or user.id == self.creator_id or \
               user in self.users.all()

    def user_can_delete_team(self, user):
        """
        удалить команду может ассистент, либо тот, кто ее создал, при условии, что у команды нет загруженных файлов
        """
        if self.system != self.SYSTEM_UPLOADS:
            return False
        team_is_deletable = not EventTeamMaterial.objects.filter(team=self).exists()
        user_has_right = user.id == self.creator_id or user.is_assistant_for_context(self.event.context)
        return team_is_deletable and user_has_right

    def get_members_for_event(self, event, user_ids=None):
        if self.system == self.SYSTEM_UPLOADS:
            return self.users.all() if event.id == self.event_id else Team.objects.none()
        user_ids = user_ids or list(event.get_participant_ids())
        if hasattr(self, '_prefetched_objects_cache') and self._prefetched_objects_cache.get('users'):
            return [i for i in self._prefetched_objects_cache['users'] if i.id in user_ids]
        return self.users.filter(id__in=user_ids)


class EventTeamMaterial(AbstractMaterial):
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    comment = models.CharField(default='', max_length=255)
    confirmed = models.BooleanField(default=True)
    owners = models.ManyToManyField(User)
    result = models.ForeignKey(TeamResult, on_delete=models.CASCADE, null=True, default=None)
    result_v2 = models.ForeignKey('LabsTeamResult', on_delete=models.CASCADE, null=True, default=None)
    loaded_by_assistant = models.BooleanField(default=False)

    class Meta:
        verbose_name = _(u'Материал команды')
        verbose_name_plural = _(u'Материалы команд')

    @classmethod
    def copy_from_object(cls, material, team):
        """
        перемещение материалов мероприятия команде
        """
        if not isinstance(material, EventOnlyMaterial):
            raise NotImplementedError
        new_obj = cls.objects.create(
            team=team,
            event=material.event,
            url=material.url,
            file=material.file,
            trace=material.trace,
            initiator=material.initiator,
            comment=material.comment,
            file_type=material.file_type,
            file_size=material.file_size,
            parent=material,
        )
        new_obj.owners.set(list(material.owners.all()))
        EventOnlyMaterial.objects.filter(id=material.id).update(deleted=True)
        return new_obj

    def get_page_url(self):
        return '{}{}'.format(
            settings.BASE_URL,
            reverse('load-team-materials', kwargs={'uid': self.event.uid, 'team_id': self.id})
        )


class EventOnlyMaterial(AbstractMaterial):
    comment = models.CharField(default='', max_length=255)
    owners = models.ManyToManyField(User)

    event_block = models.ForeignKey(EventBlock, on_delete=models.SET_NULL, null=True, default=None, blank=True)
    related_users = models.ManyToManyField(User, related_name='connected_materials', blank=True)
    related_teams = models.ManyToManyField(Team, related_name='connected_materials', blank=True)

    class Meta:
        verbose_name = _(u'Материал мероприятия')
        verbose_name_plural = _(u'Материалы мероприятий')

    def render_related_users(self):
        return ', '.join(i.get_full_name() for i in self.related_users.all())

    def render_related_teams(self):
        return ', '.join(i.name for i in self.related_teams.all())

    def get_info_string(self):
        parts = [
            self.event_block and str(self.event_block),
            self.render_related_users(),
            self.render_related_teams(),
            self.comment
        ]
        return ' | '.join(filter(None, parts))

    @classmethod
    def copy_from_object(cls, material):
        """
        перемещение материалов команды или пользователя в мероприятие
        """
        if isinstance(material, EventMaterial):
            new_obj = cls.objects.create(
                event=material.event,
                url=material.url,
                file=material.file,
                trace=material.trace,
                initiator=material.initiator,
                comment=material.comment,
                file_type=material.file_type,
                file_size=material.file_size,
                parent=material,
            )
            EventMaterial.objects.filter(id=material.id).update(deleted=True)
            return new_obj
        elif isinstance(material, EventTeamMaterial):
            new_obj = cls.objects.create(
                event=material.event,
                url=material.url,
                file=material.file,
                trace=material.trace,
                initiator=material.initiator,
                comment=material.comment,
                file_type=material.file_type,
                file_size=material.file_size,
                parent=material,
            )
            new_obj.owners.set(list(material.owners.all()))
            EventTeamMaterial.objects.filter(id=material.id).update(deleted=True)
            return new_obj
        else:
            raise NotImplementedError


class ApiUserChart(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    data = JSONField()
    updated = models.DateTimeField(null=True)

    class Meta:
        unique_together = ('user', 'event')


class LabsEventBlock(models.Model):
    """
    Блоки мероприятия по данным из лабс
    """
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='blocks', verbose_name=_('Мероприятие'))
    uuid = models.CharField(max_length=36, unique=True, verbose_name=_('UUID'))
    title = models.CharField(max_length=255, verbose_name=_('Название'))
    description = models.TextField(verbose_name=_('Описание'))
    block_type = models.CharField(max_length=255, verbose_name=_('Тип блока'))
    order = models.IntegerField(verbose_name=_('Порядок отображения в рамках мероприятия'))
    deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['order']

    def block_has_only_personal_results(self):
        return all(r.result_format == 'personal' for r in self.results.all() if not self.deleted and not r.deleted)

    def block_has_only_group_results(self):
        return all(r.result_format == 'group' for r in self.results.all() if not self.deleted and not r.deleted)


class LabsEventResult(models.Model):
    """
    Результаты блоков мароприятий по данным из лабс
    """
    block = models.ForeignKey(LabsEventBlock, on_delete=models.CASCADE, related_name='results',
                              verbose_name=_('Блок мероприятия'))
    uuid = models.CharField(max_length=36, unique=True, verbose_name=_('UUID'))
    title = models.TextField(verbose_name=_('Название'))
    result_format = models.CharField(max_length=50, verbose_name=_('Формат работы'))
    fix = models.TextField(verbose_name=_('Способ фиксации результата'))
    check = models.TextField(verbose_name=_('Способ проверки результата'))
    order = models.IntegerField(verbose_name=_('Порядок отображения в рамках блока мероприятия'))
    meta = JSONField(default=None, null=True, verbose_name=_('Ячейки, в которые попадает ЦС'))
    deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['order']

    def is_personal(self):
        """
        является ли результат персональным
        """
        return not self.result_format or self.result_format == 'personal'

    def is_group(self):
        """
        является ли результат групповым
        """
        return not self.result_format or self.result_format == 'group'

    @cached_property
    def available_circle_items(self):
        """
        доступные для разметки элементы колеса
        """
        return [i for i in self.circle_items.all() if i.tool and i.source == CircleItem.SYSTEM_LABS]

    def get_result_format_display(self):
        if self.result_format == 'personal':
            return _('персональный')
        elif self.result_format == 'group':
            return _('групповой')


class AbstractResult(models.Model):
    """
    общие поля для персональных/командных результатов
    """
    result = models.ForeignKey(LabsEventResult, on_delete=models.CASCADE)
    comment = SafeUTF8Text(default='')
    approved = models.NullBooleanField(default=None)
    approve_text = models.CharField(max_length=255, default='')
    circle_items = models.ManyToManyField('CircleItem')

    class Meta:
        abstract = True

    def models_list(self):
        """
        мета информация результата с дополнительными полем title - названием соответствующей метамодели
        """
        meta = self.get_meta()
        model_names = dict(MetaModel.objects.filter(uuid__in=filter(None, (i.get('model') for i in meta)))
                           .values_list('uuid', 'title'))
        for item in meta:
            item['title'] = model_names.get(item.get('model'))
        return meta

    @cached_property
    def selected_circle_items(self):
        return [i.id for i in self.circle_items.all() if i.tool]

    def get_meta(self):
        """
        приведение метаинформации к стандартному виду со схлопыванием инструментов в список для выдачи апи
        """
        data = defaultdict(list)
        for item in self.circle_items.all():
            i = item.get_json()
            key = tuple([i[key] for key in ('level', 'sublevel', 'competence', 'model')])
            data[key].append(i['tool'])
        result = [
            {
                'level': key[0],
                'sublevel': key[1],
                'competence': key[2],
                'model': key[3],
                'tools': list(filter(None, tools)) or None,
            }
            for key, tools in data.items()
        ]
        return result


class LabsUserResult(AbstractResult):
    """
    модель для привязки пользовательских файлов к результату LabsEventResult
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return str(self.user)

    def get_page_url(self):
        return '{}{}'.format(
            settings.BASE_URL,
            reverse('result-page', kwargs={
                'uid': self.result.block.event.uid,
                'unti_id': self.user.unti_id,
                'result_type': 'user',
                'result_id': self.id,
            })
        )

    def get_files(self):
        return EventMaterial.objects.filter(result_v2=self)


class LabsTeamResult(AbstractResult):
    """
    модель для привязки командных файлов к результату LabsEventResult
    """
    team = models.ForeignKey(Team, on_delete=models.CASCADE)

    def __str__(self):
        return str(self.team)

    def get_page_url(self):
        return '{}{}'.format(
            settings.BASE_URL,
            reverse('result-page', kwargs={
                'uid': self.result.block.event.uid,
                'unti_id': self.team_id,
                'result_type': 'team',
                'result_id': self.id,
            })
        )

    def get_files(self):
        return EventTeamMaterial.objects.filter(result_v2=self)


class DPType(models.Model):
    uuid = models.CharField(unique=True, max_length=50)
    title = models.CharField(max_length=500)


class ModelCompetence(models.Model):
    model = models.ForeignKey('MetaModel', on_delete=models.CASCADE, related_name='competences')
    competence = models.ForeignKey('DpCompetence', on_delete=models.CASCADE, related_name='models')
    order = models.IntegerField()

    class Meta:
        unique_together = ('model', 'competence')


class MetaModel(models.Model):
    """
    Информация о метамоделях. Нужно для хранения информации о названиях моделей
    из метаданных результата в лабс
    """
    uuid = models.CharField(max_length=255, unique=True)
    guid = models.CharField(max_length=255)
    title = models.CharField(max_length=500)

    def __str__(self):
        return self.title


class DpCompetence(models.Model):
    uuid = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=500)
    type = models.IntegerField(null=True, default=None)

    def __str__(self):
        return self.title


@deconstructible
class PathAndRename(object):
    """
    формирование уникального пути для сохранения файла
    """
    def __init__(self, path):
        self.path = path

    def __call__(self, instance, filename):
        ext = filename.split('.')[-1]
        filename = '{}.{}'.format(uuid4().hex, ext)
        return os.path.join(self.path, uuid4().hex[0], uuid4().hex[1:3], filename)


class CSVDump(models.Model):
    STATUS_ORDERED = 1
    STATUS_IN_PROGRESS = 2
    STATUS_COMPLETE = 3
    STATUS_ERROR = 4

    STATUSES = (
        (STATUS_ORDERED, _('ожидание генерации')),
        (STATUS_IN_PROGRESS, _('идет генерация')),
        (STATUS_COMPLETE, _('готово')),
        (STATUS_ERROR, _('ошибка')),
    )

    csv_file = models.FileField(upload_to=PathAndRename('csv-dumps'), null=True, blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    header = models.CharField(max_length=255)
    datetime_ordered = models.DateTimeField(default=timezone.now)
    datetime_ready = models.DateTimeField(null=True, blank=True)
    status = models.SmallIntegerField(choices=STATUSES, default=STATUS_ORDERED)
    meta_data = JSONField(null=True)

    @classmethod
    def current_generations_for_user(cls, user):
        """
        Количество текущих генераций выгрузок для пользователя. Если генерация зависла в статусе
        STATUS_ORDERED или STATUS_IN_PROGRESS, считается, что она провалилась
        """
        return cls.objects.filter(
            owner=user,
            status__in=[cls.STATUS_ORDERED, cls.STATUS_IN_PROGRESS],
            datetime_ordered__gt=timezone.now() - timezone.timedelta(seconds=settings.TIME_TO_FAIL_CSV_GENERATION)
        ).count()

    def get_download_link(self):
        return reverse('load_csv_dump', kwargs={'dump_id': self.id})

    def get_file_name(self):
        return '{}.{}'.format(self.header, self.csv_file.name.split('.')[-1] or self.meta_data.get('format', 'csv'))


class UserFile(BaseMaterial, models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    source = models.CharField(max_length=50)
    activity_uuid = models.CharField(default='', max_length=255)
    data = JSONField(null=True)
    ple_result = models.ForeignKey('PLEUserResult', on_delete=models.CASCADE, null=True, default=None)

    
class CasbinData(models.Model):
    model = models.TextField()
    policy = models.TextField()
    model_version = models.IntegerField(default=1)


class PLEUserResult(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    comment = models.TextField(default='')
    meta = JSONField()

    def get_json(self, with_materials=True):
        data = {
            'id': self.id,
            'user': self.user.unti_id,
            'meta': self.meta,
            'comment': self.comment,
        }
        if with_materials:
            materials = UserFile.objects.filter(ple_result=self)
            data['materials'] = [{'uploads_url': i.get_url(), 'id': i.id} for i in materials]
        return data

    def get_url(self):
        return reverse('api-ple-result', kwargs={'result_id': self.id})


class ZendeskData(models.Model):
    after_head = models.TextField(verbose_name=_('Код до закрывающегося тега head'), blank=True, default='')
    before_body = models.TextField(verbose_name=_('Код после открывающегося тега body'), blank=True, default='')

    class Meta:
        verbose_name = _('Виджет zendesk')
        verbose_name_plural = _('Виджет zendesk')


class DTraceStatisticsBase(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    context = models.ForeignKey(Context, on_delete=models.CASCADE)
    n_entry = models.IntegerField(default=0, verbose_name=_('Количество записей на мероприятия контекста'))
    n_run_entry = models.IntegerField(default=0, verbose_name=_('Количество записей на прогоны контекста'))
    n_personal = models.IntegerField(default=0, verbose_name=_('Количество персонального цс'))
    n_team = models.IntegerField(default=0, verbose_name=_('Количество командного цс'))
    n_event = models.IntegerField(default=0, verbose_name=_('Загруженные пользователем материалы мероприятия'))
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        abstract = True


class DTraceStatistics(DTraceStatisticsBase):
    class Meta:
        unique_together = ('user', 'context')

    @classmethod
    def update_entry(cls, entry):
        # запись в статистике создается, если у пользователя есть цс или уже есть статистика по этому контексту
        if cls.objects.filter(user_id=entry.id, context_id=entry.context_id).exists() or \
                any(getattr(entry, key) for key in ('n_personal', 'n_team', 'n_event')):
            cls.objects.update_or_create(user_id=entry.user_id, context_id=entry.context_id, defaults={
                f.name: getattr(entry, f.name) for f in cls._meta.fields
                if not f.auto_created and f.name not in ('user', 'context')
            })
            return True
        return False


class DTraceStatisticsHistory(DTraceStatisticsBase):
    @classmethod
    def copy_from_statistics(cls, entry):
        return cls(**{
            f.attname: getattr(entry, f.attname) for f in cls._meta.fields if not f.auto_created
        })


class CircleItem(models.Model):
    """
    элемент колеса
    """
    SYSTEM_UPLOADS = 'uploads'
    SYSTEM_LABS = 'labs'

    level = models.IntegerField(null=True, default=None)
    sublevel = models.IntegerField(null=True, default=None)
    competence = models.ForeignKey(DpCompetence, null=True, default=None, on_delete=models.CASCADE)
    competence_uuid = models.CharField(max_length=36, default=None, null=True)
    tool = models.TextField(default=None, null=True)
    model = models.ForeignKey(MetaModel, null=True, default=None, on_delete=models.CASCADE)
    model_uuid = models.CharField(max_length=36, default=None, null=True)
    result = models.ForeignKey(LabsEventResult, on_delete=models.CASCADE, related_name='circle_items')
    code = models.CharField(max_length=32, unique=True)
    created_in = models.CharField(max_length=15, default=SYSTEM_LABS)
    # параметр для отслеживания того, к какой системе сейчас принадлежит элемент. те, что есть в разметке
    # мероприятия в labs доступны обычным пользователям для добавления к результату
    source = models.CharField(max_length=15, default=SYSTEM_LABS)

    def get_code(self):
        """
        высчитывает уникальный код для объекта (т.к. длина поля tool неограничена, его нельзя использовать
        в связке unique_together)
        """
        key = ':'.join([
            str(self.level),
            str(self.sublevel),
            str(self.competence_uuid),
            str(self.model_uuid),
            str(self.result_id),
            str(self.tool),
        ])
        return hashlib.md5(key.encode('utf8')).hexdigest()

    def get_json(self):
        return {
            'level': self.level,
            'sublevel': self.sublevel,
            'competence': self.competence_uuid,
            'model': self.model_uuid,
            'tool': self.tool,
        }


class UpdateTimes(models.Model):
    CHECKINS = 'checkins'
    RUN_ENROLLMENTS = 'run_enrollments'
    DWH_CHECKINS = 'dwh_checkins'
    DWH_RUN_ENROLLMENTS = 'dwh_run_enrollments'
    DELETE_RUN_ENROLLMENTS = 'delete_run_enrollments'
    CONTEXTS = 'contexts'
    EVENT_CONTEXTS = 'event_contexts'
    EVENT_TYPES = 'event_types'
    EVENT_TYPE_CONNECTIONS = 'event_type_connections'
    ACTIVITY_AUTHORS = 'activity_authors'
    EVENT_AUTHORS = 'event_authors'
    METAMODELS = 'metamodels'
    COMPETENCES = 'competences'
    EVENT_STRUCTURE = 'event_structure'
    EVENT_RUN_ACTIVITY = 'event_run_activity'
    PT_TEAMS = 'pt_teams'
    ALL_EVENTS = 'all_events'

    event_type = models.CharField(max_length=255, unique=True, primary_key=True)
    dt = models.DateTimeField()

    @classmethod
    def get_last_update_for_event(cls, event_type, iso=True):
        item = cls.objects.filter(event_type=event_type).first()
        if iso:
            return item and item.dt and item.dt.isoformat()
        return item and item.dt

    @classmethod
    def set_last_update_for_event(cls, event_type, dt):
        cls.objects.update_or_create(event_type=event_type, defaults={'dt': dt})


class EventAuthor(models.Model):
    SOURCE_EVENT = 'event'
    SOURCE_ACTIVITY = 'activity'

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    source = models.CharField(max_length=15, choices=(
        (SOURCE_EVENT, SOURCE_EVENT),
        (SOURCE_ACTIVITY, SOURCE_ACTIVITY),
    ))
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('user', 'event')


class Summary(models.Model):
    """
    Модель для хранения конспектов и их черновиков
    """
    result_limit_models = models.Q(app_label='isle', model='Trace') | \
                          models.Q(app_label='isle', model='LabsEventResult')

    content = SafeUTF8Text(blank=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    is_draft = models.BooleanField(default=True)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+',
                                     limit_choices_to=result_limit_models, null=True)
    object_id = models.PositiveIntegerField(null=True)
    result = GenericForeignKey()
    created_at = models.DateTimeField(auto_now_add=True)

    def get_short_content(self):
        return '\n'.join(strip_tags(self.content).splitlines()[:2])

    @classmethod
    def publish_summary(cls, user, event, result, content):
        """
        сохранение конспекта с обработкой от потенциально опасных элементов и удаление старых черновиков, относящихся
        к указанному блоку
        """
        content = bleach.clean(
            content,
            tags=settings.BLEACH_ALLOWED_TAGS,
            attributes=settings.BLEACH_ALLOWED_ATTRIBUTES,
        )
        summary = cls.objects.create(author=user, event=event, result=result, content=content, is_draft=False)
        if isinstance(result, Trace):
            result = None
        cls.objects.filter(
            author=user,
            event=event,
            content_type=ContentType.objects.get_for_model(result) if result else None,
            object_id=result.id if result else None,
            is_draft=True
        ).delete()
        return summary


class DpTool(models.Model):
    uuid = models.CharField(max_length=50, unique=True)
    title = models.TextField()
    models = models.ManyToManyField(MetaModel, related_name='tools')

    def __str__(self):
        return self.title
