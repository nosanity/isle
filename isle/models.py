from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from jsonfield import JSONField


class User(AbstractUser):
    second_name = models.CharField(max_length=50)
    icon = JSONField()
    is_assistant = models.BooleanField(default=False)
    unti_id = models.PositiveIntegerField(null=True)

    class Meta:
        verbose_name = _(u'Пользователь')
        verbose_name_plural = _(u'Пользователи')


class Event(models.Model):
    uid = models.CharField(max_length=255, unique=True, verbose_name=_(u'UID события'))
    data = JSONField()
    is_active = models.BooleanField(default=False, verbose_name=_(u'Доступно для оцифровки'))
    dt_start = models.DateTimeField(verbose_name=_(u'Время начала'))
    dt_end = models.DateTimeField(verbose_name=_(u'Время окончания'))
    title = models.CharField(max_length=1000, default='')

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
        data = self.data or {}
        return sorted(data.get('traces', []))


class EventEntry(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    is_active = models.BooleanField()
    timestamp = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _(u'Запись пользователя')
        verbose_name_plural = _(u'Записи пользователей')
        unique_together = ('user', 'event')

    def __str__(self):
        return '%s - %s' % (self.event, self.user)


class EventMaterial(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    url = models.URLField(blank=True)
    file = models.FileField(blank=True)
    trace = models.CharField(max_length=1000)

    class Meta:
        verbose_name = _(u'Материал')
        verbose_name_plural = _(u'Материалы')

    def get_url(self):
        if self.url:
            return self.url
        elif self.file:
            return self.file.url

    def __str__(self):
        return '#%s %s' % (self.id, self.get_url())
