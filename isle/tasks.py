import csv
import logging
import tempfile
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
import requests
from isle.celery import app
from isle.kafka import send_object_info, KafkaActions, KAFKA_MESSAGE_HANDLERS
from isle.models import Event, CSVDump, Activity, Context, LabsTeamResult, UserFile, PLEUserResult
from isle.utils import EventGroupMaterialsCSV, BytesCsvObjWriter, XLSWriter
from isle.serializers import UserResultSerializer


@app.task
def generate_events_csv(dump_id, event_ids, file_format, meta):
    CSVDump.objects.filter(id=dump_id).update(status=CSVDump.STATUS_IN_PROGRESS)
    events = Event.objects.filter(id__in=event_ids).order_by('id')
    try:
        if meta['activity']:
            meta['activity'] = Activity.objects.get(id=meta['activity'])
        if meta['context']:
            meta['context'] = Context.objects.get(id=meta['context'])
        obj = EventGroupMaterialsCSV(events, meta)
        if file_format == 'xls':
            with tempfile.TemporaryFile() as f:
                writer = XLSWriter(f)
                for line in obj.generate():
                    writer.writerow(line)
                writer.close()
                save_result_file(dump_id, f, 'xlsx')
        else:
            b = BytesCsvObjWriter('utf-8')
            c = csv.writer(b, delimiter=';')
            for line in obj.generate():
                c.writerow(list(map(str, line)))
            save_result_file(dump_id, b.file, 'csv')
    except Exception:
        logging.exception('Failed to generate events csv')
        CSVDump.objects.filter(id=dump_id).update(status=CSVDump.STATUS_ERROR)


def save_result_file(dump_id, result_file, extension):
    csv_dump = CSVDump.objects.get(id=dump_id)
    csv_dump.csv_file.save('.{}'.format(extension), content=result_file)
    csv_dump.datetime_ready = timezone.now()
    csv_dump.status = CSVDump.STATUS_COMPLETE
    csv_dump.save()


@app.task
def team_members_set_changed(team_id):
    for result in LabsTeamResult.objects.filter(team_id=team_id).iterator():
        send_object_info(result, result.id, KafkaActions.UPDATE)


@app.task
def handle_ple_user_result(data):
    """
    создание пользовательского результата и загрузка файлов с последующим обращением по callback_url
    с информацией о созданном результате
    :param data: сырые данные запроса, прошедшие валидацию сериализатором isle.serializers.UserResultSerializer
    :return:
    """
    callback_url = data.get('callback_url')
    result = {}
    added_files = 0
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
                    material = UserFile.objects.create(
                        ple_result=user_result,
                        file_type=file_type,
                        file_size=file_size,
                        user=serializer.validated_data['user'],
                        source='PLE',
                    )
                    material.file.save(
                        'ple_results/{}/{}/{}'.format(
                            serializer.validated_data['user'].unti_id,
                            user_result.id,
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
                material = UserFile.objects.create(
                    ple_result=user_result,
                    file_type=file_type,
                    file_size=file_size,
                    url=url,
                    user=serializer.validated_data['user'],
                    source='PLE',
                )
            item.update(
                {'status': 'success', 'id': material.id, 'uploads_url': material.get_url()}
            )
            added_files += 1
        if added_files == 0:
            user_result.delete()
            result = {'materials': result['materials']}
        else:
            send_object_info(user_result, user_result.id, KafkaActions.CREATE)
    except:
        logging.exception('Handling of PLE user result failed')
    finally:
        try:
            r = requests.post(callback_url, json=result, timeout=settings.CONNECTION_TIMEOUT, verify=False)
            assert r.ok, 'ple responded with %s' % r.status_code
        except (AssertionError, requests.RequestException):
            logging.exception('Failed to send user result report to PLE. Result: {}. Initial data: {}'.
                              format(result, data))


@app.task
def handle_kafka_message(topic, msg):
    for obj in KAFKA_MESSAGE_HANDLERS:
        try:
            obj.handle_message(topic, msg)
        except Exception:
            logging.exception('Kafka handler %s failed', str(obj))