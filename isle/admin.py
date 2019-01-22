import logging
from django import forms
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.utils.translation import ugettext_lazy as _
from isle.models import Event, Team, EventType, Trace


class RemoveDeleteActionMixin:
    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions


@admin.register(Event)
class EventAdmin(RemoveDeleteActionMixin, admin.ModelAdmin):
    actions = ['make_active', 'make_inactive']
    list_display = ('uid', 'title', 'dt_start', 'dt_end', 'event_type', 'is_active')
    list_filter = ('is_active', 'event_type',)
    readonly_fields = ('uid', 'dt_start', 'dt_end', 'data', 'title', 'event_type', 'ext_id')
    search_fields = ('uid', )

    def has_add_permission(self, request):
        return False

    def make_active(self, request, queryset):
        selected = request.POST.getlist('_selected_action')
        Event.objects.filter(id__in=selected).update(is_active=True)
        return HttpResponseRedirect(request.get_full_path())
    make_active.short_description = _(u'Сделать доступным для оцифровки')

    def make_inactive(self, request, queryset):
        selected = request.POST.getlist('_selected_action')
        Event.objects.filter(id__in=selected).update(is_active=False)
        return HttpResponseRedirect(request.get_full_path())
    make_inactive.short_description = _(u'Сделать недоступным для оцифровки')


@admin.register(Team)
class TeamAdmin(RemoveDeleteActionMixin, admin.ModelAdmin):
    list_display = ('event', 'name')
    search_fields = ('name', 'event__uid', 'event__title')
    filter_horizontal = ('users', )

    def has_add_permission(self, request):
        return False


class EventTypeForm(forms.ModelForm):
    class Meta:
        model = EventType
        fields ='__all__'

    def clean_trace_data(self):
        val = self.cleaned_data.get('trace_data')
        if val:
            err_msg = 'Некорректный формат'
            if not isinstance(val, list):
                raise forms.ValidationError(err_msg)
            for item in val:
                if not isinstance(item, dict):
                    raise forms.ValidationError(err_msg)
                if set(item.keys()) != {'trace_type', 'name'}:
                    raise forms.ValidationError(err_msg)
        return val


@admin.register(EventType)
class EventTypeAdmin(RemoveDeleteActionMixin, admin.ModelAdmin):
    readonly_fields = ('ext_id', 'title', 'description', 'uuid')
    form = EventTypeForm
    list_display = ('title', 'visible')

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        obj.save()
        data = obj.trace_data
        if data:
            traces = {}
            for t in Trace.objects.filter(event_type=obj, ext_id__isnull=True):
                traces[t.id] = (t.trace_type, t.name)
            added_traces = set()
            for i in data:
                item = (i['trace_type'], i['name'])
                added_traces.add(item)
                if item in traces.values():
                    continue
                Trace.objects.create(event_type=obj, **i)
            for trace_id, item in traces.items():
                if item not in added_traces:
                    Trace.objects.filter(id=trace_id).delete()
                    logging.warning('Trace #%s %s was deleted' % (trace_id, item))
