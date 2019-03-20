import csv
import logging
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
import requests
from celery import task
from isle.api import PLEApi, ApiError
from isle.models import Event, CSVDump, Activity, Context, Material, PLEUserResult
from isle.utils import EventGroupMaterialsCSV, BytesCsvObjWriter
from isle.serializers import UserResultSerializer


@task
def generate_events_csv(dump_id, event_ids, encoding, meta):
    CSVDump.objects.filter(id=dump_id).update(status=CSVDump.STATUS_IN_PROGRESS)
    events = Event.objects.filter(id__in=event_ids).order_by('id')
    try:
        if meta['activity']:
            meta['activity'] = Activity.objects.get(id=meta['activity'])
        if meta['context']:
            meta['context'] = Context.objects.get(id=meta['context'])
        obj = EventGroupMaterialsCSV(events, meta)
        b = BytesCsvObjWriter(encoding)
        c = csv.writer(b, delimiter=';')
        for line in obj.generate():
            c.writerow(list(map(str, line)))
        csv_dump = CSVDump.objects.get(id=dump_id)
        csv_dump.csv_file.save('', content=b.file)
        csv_dump.datetime_ready = timezone.now()
        csv_dump.status = CSVDump.STATUS_COMPLETE
        csv_dump.save()
    except Exception:
        logging.exception('Failed to generate events csv')
        CSVDump.objects.filter(id=dump_id).update(status=CSVDump.STATUS_ERROR)


@task
def handle_ple_user_result(data):
    """
    создание пользовательского результата и загрузка файлов с последующим обращением по callback_url
    с информацией о созданном результате
    :param data: сырые данные запроса, прошедшие валидацию сериализатором isle.serializers.UserResultSerializer
    :return:
    """
    callback_url = data.get('callback_url')
    result = {}
    try:
        serializer = UserResultSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        user_result = PLEUserResult.objects.create(
            user=serializer.validated_data['user'],
            comment=serializer.validated_data.get('comment') or '',
            meta=serializer.validated_data['meta'],
        )
        result_materials = serializer.validated_data['materials'][:]
        for i in result_materials:
            i.update({'status': 'error'})
        result = user_result.get_json(with_materials=False)
        result['materials'] = result_materials
        for item in result_materials:
            url = item.get('file') or item.get('url')
            if 'file' in item:
                try:
                    resp = requests.get(url)
                    file_type = resp.headers.get('content-type', '')
                    file_size = resp.headers.get('Content-Length')
                    material = Material.objects.create(
                        ple_result=user_result,
                        file_type=file_type,
                        file_size=file_size,
                    )
                    material.file.save(
                        'ple_results/{}/{}/{}'.format(
                            user_result.id,
                            serializer.validated_data['user'].unti_id,
                            url.split('/')[-1]
                        ), ContentFile(resp.content))
                except requests.RequestException:
                    continue
            else:
                try:
                    resp = requests.head(url, timeout=settings.HEAD_REQUEST_CONNECTION_TIMEOUT)
                    file_type = resp.headers.get('content-type', '')
                    file_size = resp.headers.get('Content-Length')
                except requests.RequestException:
                    file_type, file_size = '', None
                material = Material.objects.create(
                    ple_result=user_result,
                    file_type=file_type,
                    file_size=file_size,
                    url=url,
                )
            item.update(
                {'status': 'success', 'id': material.id, 'uploads_url': material.get_url()}
            )
    except:
        logging.exception('Handling of PLE user result failed')
    finally:
        try:
            PLEApi().send_user_result_report(callback_url, result)
        except ApiError:
            logging.error('Failed to send user result report to PLE. Result: {}. Initial data: {}'.
                          format(result, data))
