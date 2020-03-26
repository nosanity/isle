import csv
import io
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.http import StreamingHttpResponse, FileResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import ListView

from isle.models import CSVDump, Event, Context
from isle.tasks import generate_events_csv
from isle.utils import BytesCsvStreamWriter, get_csv_encoding_for_request, XLSWriter, EventMaterialsCSV, \
    EventGroupMaterialsCSV
from isle.views.common import GetEventMixin
from isle.views.event import IndexPageEventsFilterMixin, ActivitiesFilter


class CSVResponseGeneratorMixin:
    def get_csv_response(self, obj):
        b = BytesCsvStreamWriter(get_csv_encoding_for_request(self.request))
        c = csv.writer(b, delimiter=';')
        resp = StreamingHttpResponse(
            (c.writerow(list(map(str, row))) for row in obj.generate()),
            content_type="text/csv"
        )
        resp['Content-Disposition'] = "attachment; filename*=UTF-8''{}.csv".format(obj.get_csv_filename())
        return resp


class XLSResponseGeneratorMixin:
    def get_xls_response(self, obj):
        out = io.BytesIO()
        writer = XLSWriter(out)
        for row in obj.generate():
            writer.writerow(row)
        writer.close()
        out.seek(0)
        resp = FileResponse(out)
        resp['Content-Disposition'] = "attachment; filename*=UTF-8''{}.xlsx".format(obj.get_csv_filename())
        return resp


class ChooseFormatResponseGeneratorMixin(CSVResponseGeneratorMixin, XLSResponseGeneratorMixin):
    def get_response(self, obj):
        if self.request.GET.get('format') == 'xls':
            return self.get_xls_response(obj)
        return self.get_csv_response(obj)


class EventCsvData(GetEventMixin, ChooseFormatResponseGeneratorMixin, View):
    def get(self, request, *args, **kwargs):
        if not self.current_user_is_assistant:
            raise PermissionDenied
        obj = EventMaterialsCSV(self.event)
        if request.GET.get('check_empty'):
            return JsonResponse({'has_contents': obj.has_contents()})
        return self.get_response(obj)


@method_decorator(login_required, name='dispatch')
class BaseCsvEventsDataView(ChooseFormatResponseGeneratorMixin, View):
    def get(self, request):
        if not request.user.has_assistant_role():
            raise PermissionDenied
        events = self.get_events_for_csv()
        activity_filter = getattr(self, 'activity_filter', None)
        date_min, date_max = self.get_dates()
        meta_data = {
            'activity': activity_filter,
            'date_min': date_min,
            'date_max': date_max,
            'context': request.user.chosen_context,
            'format': 'xlsx' if request.GET.get('format') == 'xls' else 'csv',
        }
        obj = EventGroupMaterialsCSV(events, meta_data)
        num = obj.count_materials()
        if request.GET.get('check_empty'):
            return JsonResponse({
                'has_contents': num > 0,
                'max_num': settings.MAX_MATERIALS_FOR_SYNC_GENERATION,
                'sync': num <= settings.MAX_MATERIALS_FOR_SYNC_GENERATION,
                'max_csv': settings.MAX_PARALLEL_CSV_GENERATIONS,
                'can_generate': CSVDump.current_generations_for_user(request.user) < \
                                settings.MAX_PARALLEL_CSV_GENERATIONS,
                'page_url': reverse('csv-dumps-list'),
            })
        if num <= settings.MAX_MATERIALS_FOR_SYNC_GENERATION:
            return self.get_response(obj)
        if CSVDump.current_generations_for_user(request.user) >= settings.MAX_PARALLEL_CSV_GENERATIONS:
            raise PermissionDenied
        task_meta = meta_data.copy()
        task_meta['activity'] = activity_filter and activity_filter.id
        task_meta['context'] = request.user.chosen_context and request.user.chosen_context.id
        csv_dump = CSVDump.objects.create(
            owner=request.user, header=obj.get_csv_filename(do_quote=False), meta_data=task_meta
        )
        generate_events_csv.delay(csv_dump.id, [i.id for i in events], request.GET.get('format'), task_meta)
        return JsonResponse({'page_url': reverse('csv-dumps-list'), 'dump_id': csv_dump.id})

    def get_events_for_csv(self):
        return Event.objects.none()


class EventsCsvData(IndexPageEventsFilterMixin, BaseCsvEventsDataView):
    """
    Выгрузка csv по нескольким мероприятиям сразу
    """
    def get_events_for_csv(self):
        return self.get_events()


class ActivitiesCsvData(ActivitiesFilter, BaseCsvEventsDataView):
    """
    Выгрузка csv по нескольким активностям сразу
    """
    def get_events_for_csv(self):
        return Event.objects.filter(
            activity_id__in=self.get_activities().order_by().values_list('id', flat=True)
        ).order_by('title', 'dt_start')


@method_decorator(login_required, name='dispatch')
class LoadCsvDump(View):
    def get(self, request, **kwargs):
        if not request.user.has_assistant_role():
            raise PermissionDenied
        obj = get_object_or_404(CSVDump, id=kwargs['dump_id'], status=CSVDump.STATUS_COMPLETE)
        resp = FileResponse(default_storage.open(obj.csv_file.name))
        resp['Content-Disposition'] = "attachment; filename*=UTF-8''{header}".format(header=quote(obj.get_file_name()))
        return resp


@method_decorator(login_required, name='dispatch')
class CSVDumpsList(ListView):
    model = CSVDump
    paginate_by = 50
    template_name = 'my_csv_dumps.html'

    def get_queryset(self):
        return self.model.objects.filter(owner=self.request.user).order_by('-datetime_ordered').select_related('owner')

    def get_context_data(self, *, object_list=None, **kwargs):
        if not self.request.user.has_assistant_role():
            raise PermissionDenied
        data = super().get_context_data(object_list=object_list, **kwargs)
        context_ids = {}
        object_list = data['object_list']
        for obj in object_list:
            meta_data = obj.meta_data if isinstance(obj.meta_data, dict) else {}
            context_ids[obj.id] = meta_data.get('context')
        contexts = dict(Context.objects.filter(id__in=filter(None, context_ids.values())).values_list('id', 'guid'))
        for obj in object_list:
            obj.meta = {
                'context_guid': contexts.get(context_ids[obj.id]),
            }
        return data
