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


class Event(models.Model):
    uid = models.CharField(max_length=255, unique=True, verbose_name=_(u'UID события'))
    data = JSONField()
    is_active = models.BooleanField(default=False, verbose_name=_(u'Доступно для оцифровки'))
    dt_start = models.DateTimeField(verbose_name=_(u'Время начала'))
    dt_end = models.DateTimeField(verbose_name=_(u'Время окончания'))
    title = models.CharField(max_length=1000, default='', verbose_name='Название')

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
        return self.trace_set.order_by('name')


class Trace(models.Model):
    """
    Модель результата эвента. Удаление результата не предполагается, может только меняться
    список эвентов, к которым он относится.
    """
    events = models.ManyToManyField(Event)
    ext_id = models.PositiveIntegerField(db_index=True)
    trace_type = models.CharField(max_length=255, db_index=True)
    name = models.TextField(default='')


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
