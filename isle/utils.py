import csv
import json
import logging
import pytz
from collections import defaultdict
from io import StringIO
from datetime import datetime
from django.conf import settings
from django.core.cache import caches
from django.core.files.storage import default_storage
from django.db import models
from django.utils import timezone
from django.utils.dateparse import parse_datetime
import requests
from isle.api import Api, ApiError, ApiNotFound, LabsApi, XLEApi
from isle.models import (Event, EventEntry, User, Trace, EventType, Activity, EventOnlyMaterial, ApiUserChart, Context,
                         LabsEventBlock, LabsEventResult, LabsUserResult, EventMaterial)

DEFAULT_CACHE = caches['default']
EVENT_TYPES_CACHE_KEY = 'EVENT_TYPE_IDS'


def get_allowed_event_type_ids():
    return list(EventType.objects.filter(visible=True).values_list('id', flat=True))


def refresh_events_data():
    """
    Обновление списка эвентов и активностей. Предполагается, что этот список меняется редко (или не меняется вообще).
    В процессе обновления эвент может быть удален, но только если он запланирован как минимум на следующий день.
    """
    def _parse_dt(val):
        try:
            return parse_datetime(val)
        except (AssertionError, TypeError):
            return timezone.now()

    try:
        event_types = {}
        existing_uids = set(Event.objects.values_list('uid', flat=True))
        fetched_events = set()
        filter_dict = lambda d, excl: {k: d.get(k) for k in d if k not in excl}
        ACTIVITY_EXCLUDE_KEYS = ['runs', 'activity_type']
        RUN_EXCLUDE_KEYS = ['events']
        EVENT_EXCLUDE_KEYS = ['time_slot', 'blocks']
        for data in LabsApi().get_activities():
            for activity in data:
                title = activity.get('title', '')
                runs = activity.get('runs') or []
                event_type = None
                activity_types = activity.get('types')
                activity_type = activity_types and activity_types[0]
                activity_json = filter_dict(activity, ACTIVITY_EXCLUDE_KEYS)
                activity_uid = activity.get('uuid')
                if activity_uid:
                    main_author = ''
                    authors = activity.get('authors') or []
                    for author in authors:
                        if author.get('is_main'):
                            main_author = author.get('title')
                            break
                    current_activity = Activity.objects.update_or_create(
                        uid=activity_uid,
                        defaults={
                            'title': title,
                            'main_author': main_author,
                            'is_deleted': bool(activity.get('is_deleted')),
                        }
                    )[0]
                else:
                    continue
                if activity_type and activity_type.get('uuid'):
                    event_type = event_types.get(activity_type['uuid'])
                    if not event_type:
                        event_type = EventType.objects.update_or_create(
                            uuid=activity_type['uuid'],
                            defaults={'title': activity_type.get('title'),
                                      'description': activity_type.get('description') or ''}
                        )[0]
                for run in runs:
                    run_json = filter_dict(run, RUN_EXCLUDE_KEYS)
                    events = run.get('events') or []
                    for event in events:
                        event_json = filter_dict(event, EVENT_EXCLUDE_KEYS)
                        uid = event['uuid']
                        timeslot = event.get('timeslot')
                        is_active = False if event.get('is_deleted') else True
                        dt_start, dt_end = datetime.now(), datetime.now()
                        if timeslot:
                            dt_start = _parse_dt(timeslot['start'])
                            dt_end = _parse_dt(timeslot['end'])
                        e, e_created = Event.objects.update_or_create(uid=uid, defaults={
                            'is_active': is_active,
                            'activity': current_activity,
                            'data': {'event': event_json, 'run': run_json, 'activity': activity_json},
                            'dt_start': dt_start, 'dt_end': dt_end, 'title': title, 'event_type': event_type})
                        update_event_structure(
                            event.get('blocks', []),
                            e,
                            e.blocks.values_list('uuid', flat=True) if not e_created else []
                        )
                        fetched_events.add(e.uid)
        delete_events = existing_uids - fetched_events - {getattr(settings, 'API_DATA_EVENT', '')}
        Event.objects.filter(uid__in=delete_events).update(is_active=False)
        # если произошли изменения в списке будущих эвентов
        dt = timezone.now() + timezone.timedelta(days=1)
        delete_qs = Event.objects.filter(uid__in=delete_events, dt_start__gt=dt)
        delete_events = delete_qs.values_list('uid', flat=True)
        if delete_events:
            logging.warning('Event(s) with uuid: {} were deleted'.format(', '.join(delete_events)))
            delete_qs.delete()
        return True
    except ApiError:
        return
    except Exception:
        logging.exception('Failed to handle events data')


def update_event_structure(data, event, event_blocks_uuid):
    """
    Обновление структуры эвента
    :param data json со структурой
    :param event объект Event
    :param event_blocks_uuid список текущих uuid-ов блоков мероприятия
    """
    def _parse_meta(meta):
        if isinstance(meta, str):
            try:
                return json.loads(meta)
            except:
                return
        elif isinstance(meta, list):
            return meta
        return

    created_blocks = []
    try:
        for block_order, block in enumerate(data, 1):
            block_uuid = block.get('uuid')
            if not block_uuid:
                logging.error("Didn't get uuid for block: %s" % block)
                continue
            b, created = LabsEventBlock.objects.update_or_create(uuid=block_uuid, defaults={
                'event_id': event.id,
                'title': block.get('title') or '',
                'description': block.get('description') or '',
                'block_type': block.get('type') or '',
                'order': block_order,
            })
            created_blocks.append(b.uuid)
            results = block.get('results') or []
            block_results = b.results.values_list('uuid', flat=True) if not created else []
            created_results = []
            for result_order, result in enumerate(results, 1):
                result_uuid = result.get('uuid')
                if not result_uuid:
                    logging.error("Didn't get uuid for result: %s" % result)
                    continue
                r, r_created = LabsEventResult.objects.update_or_create(uuid=result_uuid, defaults={
                    'block_id': b.id,
                    'title': result.get('title') or '',
                    'result_format': result.get('format') or '',
                    'fix': result.get('fix') or '',
                    'check': result.get('check') or '',
                    'order': result_order,
                    'meta': _parse_meta(result.get('meta')),
                })
                created_results.append(r.uuid)
            if set(block_results) - set(created_results):
                b.results.exclude(uuid__in=created_results).delete()
        if set(event_blocks_uuid) - set(created_blocks):
            event.blocks.exclude(uuid__in=created_blocks).delete()
    except Exception:
        logging.exception('Failed to parse event structure')


def update_event_entries():
    """
    добавление EventEntry по данным из xle
    """
    try:
        by_event = defaultdict(list)
        unti_id_to_id = dict(User.objects.filter(unti_id__isnull=False).values_list('unti_id', 'id'))
        events = dict(Event.objects.values_list('uid', 'id'))
        # список пользователей, которых не удалось найти по unti id, и для которых запрос на пропушивание в sso
        # не удался, чтобы не пытаться их пропушивать еще раз
        failed_unti_ids = set()
        for data in XLEApi().get_attendance():
            for item in data:
                if (item.get('attendance') or item.get('checkin')) and item.get('event_uuid') and item.get('unti_id'):
                    by_event[item['event_uuid']].append(item['unti_id'])
        for event_uuid, unti_ids in by_event.items():
            event_id = events.get(event_uuid)
            if not event_id:
                logging.error('Event with uuid %s not found' % event_uuid)
                continue
            users = []
            for unti_id in unti_ids:
                user_id = unti_id_to_id.get(unti_id)
                if not user_id:
                    created_user = pull_sso_user(unti_id) if unti_id not in failed_unti_ids else None
                    if not created_user:
                        logging.error('User with unti_id %s not found' % unti_id)
                        failed_unti_ids.add(unti_id)
                        continue
                    user_id = created_user.id
                    unti_id_to_id[unti_id] = user_id
                users.append(user_id)
            existing = list(EventEntry.objects.filter(event__uid=event_uuid).values_list('user_id', flat=True))
            create = set(users) - set(existing)
            for user_id in create:
                EventEntry.all_objects.update_or_create(event_id=event_id, user_id=user_id, defaults={'deleted': False})
        return True
    except ApiError:
        return False
    except Exception:
        logging.exception('Failed to parse xle attendance')


def pull_sso_user(unti_id):
    """
    запрос в sso на пропушивание пользователя с указанным unti id
    """
    try:
        r = requests.post(
            '{}/api/push-user-to-uploads/'.format(settings.SSO_UNTI_URL),
            json={'unti_id': int(unti_id)},
            headers={'X-SSO-API-KEY': settings.SSO_API_KEY},
            timeout=settings.CONNECTION_TIMEOUT
        )
        assert r.ok, 'SSO status code %s' % r.status_code
        assert r.json().get('status') is not None, 'SSO push_to_uploads failed'
    except Exception:
        logging.exception('Failed to pull user from sso')
    return User.objects.filter(unti_id=unti_id).first()


def update_events_traces():
    """
    обновление трейсов по всем эвентам
    """
    return
    events = {e.uid: e for e in Event.objects.all()}
    try:
        resp = requests.get(settings.LABS_TRACES_API_URL, timeout=settings.CONNECTION_TIMEOUT)
        assert resp.ok, 'status_code %s' % resp.status_code
        for trace in resp.json():
            t = Trace.objects.update_or_create(
                ext_id=trace['id'], defaults={'trace_type': trace['title'], 'name': trace['description']}
            )[0]
            trace_events = list(filter(None, [events.get(uid) for uid in trace.get('events', [])]))
            # test_e = Event.objects.get(uid='b94f4320-8111-4f37-95cb-a7d4f10a1ae6')
            # if not trace_events:
            #     trace_events = [test_e]
            t.events.set(trace_events)
    except Exception:
        logging.exception('failed to update traces')


def update_check_ins_for_event(event):
    return False


def set_check_in(event, user, confirmed):
    try:
        Api().set_check_in(event.ext_id, user.unti_id, confirmed)
        return True
    except ApiError:
        return False


def recalculate_user_chart_data(user):
    """
    обновление данных для чарта компетенций пользователя
    """
    if not getattr(settings, 'API_DATA_EVENT', ''):
        logging.error('settings do not define API_DATA_EVENT')
        return []

    try:
        api_event = Event.objects.get(uid=settings.API_DATA_EVENT)
    except Event.DoesNotExist:
        logging.error('event for api chart data does not exist')
        return []

    existing_data = ApiUserChart.objects.filter(user=user, event=api_event).first()
    # выбираем материалы, добавленные позже даты последнего обновления данных для чарта, или все, в случае,
    # если данные еще не были посчитаны, или параметр updated == None
    if not existing_data or not existing_data.updated:
        files = EventOnlyMaterial.objects.filter(event=api_event)
        append = False
    else:
        files = EventOnlyMaterial.objects.filter(event=api_event, created_at__gt=existing_data.updated)
        append = True

    event_ids = {}
    delimiter = getattr(settings, 'API_CHART_DATA_DELIMITER', ';')
    result = []
    headers = ['user_id', 'group_user_ids', 'event_id', 'act_event_title', 'url', 'comment', 'audio', 'level',
               'sector', 'tool', 'sublevel', 'group']
    update_time = timezone.now()
    for item in files:
        if not item.file:
            logging.error('%s api data file has no file associated with it' % item.id)
            continue
        with default_storage.open(item.file.name, 'rb') as f:
            try:
                s = StringIO()
                s.write(f.read().decode('utf8'))
                s.seek(0)
                reader = csv.reader(s, delimiter=delimiter)
                for row in reader:
                    if not any(i.strip() for i in [j.strip() for j in row]):
                        # пустая строка
                        continue
                    line = dict(zip(headers, row))
                    user_id = line.get('user_id')
                    group_user_ids = [i.strip() for i in line.get('group_user_ids', '').split(',')]
                    event_id = line.get('event_id')
                    if not event_id or not event_id.isdigit():
                        logging.error('api chart data got wrong event_id: %s' % event_id)
                        continue
                    if not event_id in event_ids:
                        event = Event.objects.filter(ext_id=event_id).first()
                        if not event:
                            logging.error('api chart data error: event with ext_id %s does not exist' % event_id)
                            continue
                        event_ids[event_id] = event
                    if user_id and user_id == str(user.leader_id) or str(user.leader_id) in group_user_ids:
                        result.append(line)
            except UnicodeDecodeError:
                logging.error('api chart data file %s contains bad csv file' % item.id)

    # оставляем значимые поля
    exclude = ['user_id', 'group_user_ids', 'audio']
    for item in result:
        for field in exclude:
            item.pop(field, None)
        item['event_title'] = event_ids[item['event_id']].title

    user_data = existing_data.data if append else []
    user_data.extend(result)
    ApiUserChart.objects.update_or_create(user=user, event=api_event,
                                          defaults={'data': user_data, 'updated': update_time})
    return user_data


def update_contexts():
    """
    апдейт контекстов и привязка к ним эвентов
    """
    try:
        for data in LabsApi().get_contexts():
            for context in data:
                timezone = context.get('timezone')
                uuid = context.get('uuid')
                if not timezone:
                    logging.error('context has no timezone')
                    continue
                try:
                    pytz.timezone(timezone)
                except pytz.UnknownTimeZoneError:
                    logging.error('unknown timezone %s' % timezone)
                    continue
                c = Context.objects.update_or_create(uuid=uuid, defaults={'timezone': timezone})[0]
                events = []
                for run in (context.get('runs') or []):
                    for event in (run.get('events') or []):
                        uuid = event.get('uuid')
                        if uuid:
                            events.append(uuid)
                Event.objects.filter(uid__in=events).update(context=c)
    except ApiError:
        return
    except Exception:
        logging.exception('Failed to parse contexts')


def get_results_list(event=None):
    """
    возвращает генератор списков вида
    untiID - UUID мероприятия - Уровень - Подуровень - Сектор - ссылка на первый файл или  url первой ссылки -
        название блока - название результата
    логика такая, что для каждой связки (LabsEventResult, User) будет n ссылок по количеству ячеек этого результата,
    и эта ссылка - первая загруженная в рамках результата
    """
    # результаты мероприятий нужного контекста или определенного мероприятия, для которых указаны ячейки
    if event:
        results = LabsEventResult.objects.filter(block__event_id=event.id, meta__isnull=False)
    else:
        context = Context.objects.get(uuid=getattr(settings, 'SPECIAL_CONTEXT_UUID', ''))
        results = LabsEventResult.objects.filter(block__event__context_id=context.id, meta__isnull=False)

    # первый "пользовательский результат", загруженный в рамках лабсовского результата,
    # т.е. первый набор файлов с общим комментарием
    user_results = list(LabsUserResult.objects.filter(result__in=results).values('user', 'result').\
        annotate(id=models.Min('id')).values_list('id', flat=True))

    # последние ссылки
    qs = EventMaterial.objects.filter(result_v2_id__in=user_results).values('user', 'result_v2').\
        annotate(material=models.Max('id'))
    materials_mapper = dict([((i['user'], i['result_v2']), i['material']) for i in qs])
    for m in EventMaterial.objects.filter(id__in=materials_mapper.values()).iterator():
        materials_mapper[(m.user_id, m.result_v2_id)] = m.get_url()

    qs2 = LabsUserResult.objects.filter(result__in=results).values('user', 'result').\
        annotate(id=models.Min('id')).\
        values('id', 'user_id', 'user__unti_id', 'result__block__event__uid', 'result__meta', 'result__title',
               'result__block__title')
    for i in qs2.iterator():
        material_link = materials_mapper.get((i['user_id'], i['id'])) or ''
        cells = json.loads(i['result__meta'])
        for cell in cells:
            yield list(map(str, [
                i['user__unti_id'],
                i['result__block__event__uid'],
                cell.get('level') or '',
                cell.get('sublevel') or '',
                cell.get('competence') or '',
                material_link,
                i['result__block__title'],
                i['result__title'],
            ]))
