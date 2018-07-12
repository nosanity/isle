from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from jsonfield import JSONField


class User(AbstractUser):
    second_name = models.CharField(max_length=50)
    icon = JSONField()
    is_assistant = models.BooleanField(default=False)
    unti_id = models.PositiveIntegerField(null=True, db_index=True)

    class Meta:
        verbose_name = _(u'Пользователь')
        verbose_name_plural = _(u'Пользователи')

    def __str__(self):
        return '%s %s' % (self.unti_id, self.get_full_name())


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


class EventEntry(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _(u'Запись пользователя')
        verbose_name_plural = _(u'Записи пользователей')
        unique_together = ('user', 'event')

    def __str__(self):
        return '%s - %s' % (self.event, self.user)


class AbstractMaterial(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    url = models.URLField(blank=True)
    file = models.FileField(blank=True)
    trace = models.ForeignKey(Trace, on_delete=models.CASCADE)

    class Meta:
        abstract = True

    def get_url(self):
        if self.url:
            return self.url
        elif self.file:
            return self.file.url

    def __str__(self):
        return '#%s %s' % (self.id, self.get_url())


class EventMaterial(AbstractMaterial):
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        verbose_name = _(u'Материал')
        verbose_name_plural = _(u'Материалы')


class Team(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, verbose_name='Событие')
    users = models.ManyToManyField(User, verbose_name='Студенты')
    name = models.CharField(max_length=500, verbose_name='Название команды')

    @property
    def team_name(self):
        return 'team_{}'.format(self.id)

    class Meta:
        verbose_name = 'Команда'
        verbose_name_plural = 'Команды'

    def __str__(self):
        return self.name


class EventTeamMaterial(AbstractMaterial):
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    comment = models.CharField(default='', max_length=255)

    class Meta:
        verbose_name = _(u'Материал команды')
        verbose_name_plural = _(u'Материалы команд')


class EventOnlyMaterial(AbstractMaterial):
    comment = models.CharField(default='', max_length=255)

    class Meta:
        verbose_name = _(u'Материал мероприятия')
        verbose_name_plural = _(u'Материалы мероприятий')
