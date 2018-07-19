import os
import urllib
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from jsonfield import JSONField


class User(AbstractUser):
    second_name = models.CharField(max_length=50)
    icon = JSONField()
    is_assistant = models.BooleanField(default=False)
    unti_id = models.PositiveIntegerField(null=True, db_index=True)
    leader_id = models.CharField(max_length=255, default='')

    class Meta:
        verbose_name = _(u'Пользователь')
        verbose_name_plural = _(u'Пользователи')

    def __str__(self):
        return '%s %s' % (self.unti_id, self.get_full_name())

    @property
    def fio(self):
        return ' '.join(filter(None, [self.last_name, self.first_name, self.second_name]))


class EventType(models.Model):
    ext_id = models.PositiveIntegerField(unique=True, verbose_name='Внешний id')
    title = models.CharField(max_length=500, verbose_name='Название')
    description = models.TextField(verbose_name='Описание', blank=True, default='')
    trace_data = JSONField(blank=True, help_text='JSON в виде списка из объектов с ключами trace_type и name. '
                                                 'Например, [{"trace_type": "Презентация", "name": '
                                                 '"Презентация продукта"}]')

    class Meta:
        verbose_name = 'Тип мероприятия'
        verbose_name_plural = 'Типы мероприятия'

    def __str__(self):
        return self.title


class Event(models.Model):
    uid = models.CharField(max_length=255, unique=True, verbose_name=_(u'UID события'))
    data = JSONField()
    is_active = models.BooleanField(default=False, verbose_name=_(u'Доступно для оцифровки'))
    dt_start = models.DateTimeField(verbose_name=_(u'Время начала'))
    dt_end = models.DateTimeField(verbose_name=_(u'Время окончания'))
    title = models.CharField(max_length=1000, default='', verbose_name='Название')
    event_type = models.ForeignKey(EventType, on_delete=models.SET_NULL, verbose_name='Тип мероприятия',
                                   blank=True, null=True, default=None)
    ile_id = models.PositiveIntegerField(default=None, verbose_name='id в ILE')
    ext_id = models.PositiveIntegerField(default=None, verbose_name='id в LABS')

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

    def is_author(self, user):
        return user.is_assistant

    def get_traces(self):
        traces = self.trace_set.order_by('name')
        if not traces and self.event_type is not None:
            events = self.event_type.trace_data or []
            order = {j['name']: i for i, j in enumerate(events)}
            traces = Trace.objects.filter(event_type=self.event_type)
            return sorted(traces, key=lambda x: order.get(x.name, 0))
        return Trace.objects.none()

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
        if self.data and isinstance(self.data, dict):
            authors = (self.data.get('activity') or {}).get('authors') or []
            return [(i.get('title') or '').strip() for i in authors]
        return []


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

    class Meta:
        verbose_name = 'Результат'
        verbose_name_plural = 'Результаты'

    def __str__(self):
        return self.name


class NotDeletedEntries(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted=False)


class EventEntry(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now=True)
    added_by_assistant = models.BooleanField(default=False, verbose_name='Добавлен вручную')
    check_in_pushed = models.BooleanField(default=False, verbose_name='Чекин проставлен в ILE')
    deleted = models.BooleanField(default=False)

    objects = NotDeletedEntries()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _(u'Запись пользователя')
        verbose_name_plural = _(u'Записи пользователей')
        unique_together = ('user', 'event')

    def __str__(self):
        return '%s - %s' % (self.event, self.user)


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


class AbstractMaterial(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    url = models.URLField(blank=True)
    file = models.FileField(blank=True, max_length=300)
    trace = models.ForeignKey(Trace, on_delete=models.CASCADE)
    initiator = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        abstract = True

    def get_url(self):
        if self.url:
            return self.url
        elif self.file:
            return self.file.url

    def get_name(self):
        if self.file:
            return urllib.parse.unquote(os.path.basename(self.file.url))
        return self.url

    def __str__(self):
        return '#%s %s' % (self.id, self.get_url())


class EventMaterial(AbstractMaterial):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    is_public = models.BooleanField(default=False)
    comment = models.CharField(default='', max_length=255)

    class Meta:
        verbose_name = _(u'Материал')
        verbose_name_plural = _(u'Материалы')


class Team(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, verbose_name='Событие')
    users = models.ManyToManyField(User, verbose_name='Студенты')
    name = models.CharField(max_length=500, verbose_name='Название команды')
    creator = models.ForeignKey(User, on_delete=models.CASCADE, null=True, default=None, related_name='team_creator')
    confirmed = models.BooleanField(default=True)

    @property
    def team_name(self):
        return 'team_{}'.format(self.id)

    @property
    def traces_number(self):
        return EventTeamMaterial.objects.filter(team=self).count()

    class Meta:
        verbose_name = 'Команда'
        verbose_name_plural = 'Команды'

    def __str__(self):
        return self.name


class EventTeamMaterial(AbstractMaterial):
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    comment = models.CharField(default='', max_length=255)
    confirmed = models.BooleanField(default=True)

    class Meta:
        verbose_name = _(u'Материал команды')
        verbose_name_plural = _(u'Материалы команд')


class EventOnlyMaterial(AbstractMaterial):
    comment = models.CharField(default='', max_length=255)

    class Meta:
        verbose_name = _(u'Материал мероприятия')
        verbose_name_plural = _(u'Материалы мероприятий')
