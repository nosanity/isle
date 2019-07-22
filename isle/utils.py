import csv
import json
import io
import logging
import os
import pytz
from collections import defaultdict, OrderedDict
from io import StringIO
from urllib.parse import quote
from datetime import datetime
from django.conf import settings
from django.core.cache import caches
from django.core.files.storage import default_storage
from django.db import models
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.functional import cached_property
from django.utils.translation import ugettext as _
import xlsxwriter
from celery.task.control import inspect
from isle.api import ApiError, LabsApi, XLEApi, DpApi, SSOApi, PTApi
from isle.cache import UserAvailableContexts
from isle.models import (Event, EventEntry, User, Trace, EventType, Activity, EventOnlyMaterial, ApiUserChart, Context,
                         LabsEventBlock, LabsEventResult, LabsUserResult, EventMaterial, MetaModel, EventTeamMaterial,
                         Team, Author, DpCompetence, CasbinData, Run, RunEnrollment, DTraceStatistics,
                         DTraceStatisticsHistory, CircleItem, LabsTeamResult)


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
            return parse_datetime(val) or timezone.now()
        except (AssertionError, TypeError):
            return timezone.now()

    try:
        event_types = {}
        existing_uids = set(Event.objects.values_list('uid', flat=True))
        competences = {}
        fetched_events = set()
        metamodels = {}
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
                    update_authors(current_activity, authors)
                else:
                    continue
                if activity_type and activity_type.get('uuid'):
                    event_type = event_types.get(activity_type['uuid'])
                    if not event_type:
                        event_type, created = EventType.objects.update_or_create(
                            uuid=activity_type['uuid'],
                            defaults={'title': activity_type.get('title'),
                                      'description': activity_type.get('description') or ''}
                        )
                        if created:
                            event_type.trace_data = settings.DEFAULT_TRACE_DATA_JSON
                            event_type.save(update_fields=['trace_data'])
                            create_traces_for_event_type(event_type)
                        event_types[activity_type['uuid']] = event_type
                for run in runs:
                    run_json = filter_dict(run, RUN_EXCLUDE_KEYS)
                    if not run.get('uuid'):
                        logging.error('run has no uuid')
                        continue
                    current_run = Run.objects.update_or_create(
                        uuid=run['uuid'],
                        defaults={'activity': current_activity, 'deleted': run.get('is_deleted')}
                    )[0]
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
                            'run': current_run,
                            'data': {'event': event_json, 'run': run_json, 'activity': activity_json},
                            'dt_start': dt_start, 'dt_end': dt_end, 'title': title, 'event_type': event_type})
                        update_event_structure(
                            event.get('blocks', []),
                            e,
                            e.blocks.values_list('uuid', flat=True) if not e_created else [],
                            metamodels,
                            competences,
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


def update_authors(activity, data):
    authors = []
    for item in data:
        uid = item.get('uuid')
        if not uid:
            continue
        authors.append(Author.objects.update_or_create(uuid=uid, defaults={
            'title': item.get('title') or '',
            'is_main': item.get('is_main'),
        })[0])
    activity.authors.set(authors)


def update_event_structure(data, event, event_blocks_uuid, metamodels, competences):
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
                'deleted': False,
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
                meta = _parse_meta(result.get('meta'))
                r, r_created = LabsEventResult.objects.update_or_create(uuid=result_uuid, defaults={
                    'block_id': b.id,
                    'title': result.get('title') or '',
                    'result_format': result.get('format') or '',
                    'fix': result.get('fix') or '',
                    'check': result.get('check') or '',
                    'order': result_order,
                    'meta': meta,
                    'deleted': False
                })
                if meta and isinstance(meta, list):
                    for model in meta:
                        # подтягивание информации о метамодели, указанной в метаданных, если такая метамодель
                        # еще не подтягивалась в рамках данного запуска обновления данных активностей и эвентов
                        if isinstance(model, dict) and model.get('model') and model['model'] not in metamodels:
                            try:
                                meta_data = DpApi().get_metamodel(model['model'])
                                if isinstance(meta_data, dict) and all(i in meta_data for i in ['title', 'guid']):
                                    metamodel = MetaModel.objects.update_or_create(uuid=model['model'], defaults={
                                        'guid': meta_data['guid'], 'title': meta_data['title']
                                    })[0]
                                    parse_competences(meta_data, competences)
                                    metamodels[model['model']] = metamodel.id
                            except ApiError:
                                pass
                    create_circle_items_for_result(
                        r.id,
                        [] if r_created else list(r.circle_items.values_list('id', flat=True)),
                        meta,
                        metamodels,
                        competences
                    )
                created_results.append(r.uuid)
            if set(block_results) - set(created_results):
                b.results.exclude(uuid__in=created_results).update(deleted=True)
        if set(event_blocks_uuid) - set(created_blocks):
            event.blocks.exclude(uuid__in=created_blocks).update(deleted=True)
    except Exception:
        logging.exception('Failed to parse event structure')


def create_circle_items_for_result(result_id, current_circle_items_ids, meta, metamodels, competences):
    from isle.kafka import send_object_info, KafkaActions
    real_items_ids = []
    for meta_item in meta:
        tools = meta_item.get('tools')
        if not isinstance(tools, list):
            tools = [None]
        for tool in tools:
            circle_item = CircleItem.objects.get_or_create(
                level=meta_item.get('level'),
                sublevel=meta_item.get('sublevel'),
                competence_id=competences.get(meta_item.get('competence')),
                model_id=metamodels.get(meta_item.get('model')),
                result_id=result_id,
                tool=tool,
            )[0]
            real_items_ids.append(circle_item.id)
    deleted_circle_items = set(current_circle_items_ids) - set(real_items_ids)
    if deleted_circle_items:
        # удалили какой-то элемент круга из разметки мероприятия, надо обновить связанные с ним
        # пользовательские и командные результаты
        results_to_update = []
        for result_model in (LabsUserResult, LabsTeamResult):
            results_to_update.extend(
                list(result_model.objects.filter(circle_items__id__in=deleted_circle_items)
                     .distinct())
            )
        CircleItem.objects.filter(id__in=deleted_circle_items).delete()
        for _result in results_to_update:
            send_object_info(_result, _result.id, KafkaActions.UPDATE)
    return real_items_ids


def parse_competences(data, competences):
    if not isinstance(data.get('competences'), list):
        logging.error('Failed to parse competences for meta model %s' % data.get('uuid'))
        return
    for item in data['competences']:
        if item['uuid'] in competences:
            continue
        try:
            comp = DpCompetence.objects.update_or_create(uuid=item['uuid'], defaults={'title': item['title']})[0]
            competences[comp.uuid] = comp.id
        except KeyError:
            logging.exception('Wrong competence structure')


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
                    if unti_id in failed_unti_ids:
                        continue
                    created_user = pull_sso_user(unti_id)
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


def update_run_enrollments():
    run_uuid_to_id = dict(Run.objects.values_list('uuid', 'id'))
    unti_id_to_id = dict(User.objects.filter(unti_id__isnull=False).values_list('unti_id', 'id'))
    failed_unti_ids = set()
    ids = []
    try:
        for data in XLEApi().get_timetable():
            for item in data:
                run_id = run_uuid_to_id.get(item['run_uuid'])
                if not run_id:
                    logging.error('run with uuid %s not found' % item['run_uuid'])
                    continue
                if item['unti_id'] in failed_unti_ids:
                    continue
                user_id = unti_id_to_id.get(int(item['unti_id']))
                if not user_id:
                    user = pull_sso_user(item['unti_id'])
                    if not user:
                        logging.error('user with unti_id %s not found' % item['unti_id'])
                        failed_unti_ids.add(item['unti_id'])
                        continue
                    user_id = user.id
                    unti_id_to_id[int(item['unti_id'])] = user_id
                enr = RunEnrollment.all_objects.update_or_create(
                    user_id=user_id, run_id=run_id, defaults={'deleted': False}
                )[0]
                ids.append(enr.id)
        RunEnrollment.objects.exclude(id__in=ids).update(deleted=True)
    except ApiError:
        return False
    except Exception:
        logging.exception('Failed to get timetable')


def pull_sso_user(unti_id):
    """
    запрос в sso на пропушивание пользователя с указанным unti id
    """
    try:
        resp = SSOApi().push_user_to_uploads(unti_id)
        assert resp.get('status') is not None, 'SSO push_to_uploads failed'
    except ApiError:
        pass
    except Exception:
        logging.exception('Failed to pull user from sso')
    return User.objects.filter(unti_id=unti_id).first()


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
                c = Context.objects.update_or_create(uuid=uuid, defaults={'timezone': timezone,
                                                                          'title': context.get('title') or '',
                                                                          'guid': context.get('guid') or ''})[0]
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


def update_teams():
    """
    обновление команд из pt, если включена соответствующая настройка
    """
    if not settings.ENABLE_PT_TEAMS:
        return
    try:
        context_uuid_to_id = dict(Context.objects.values_list('uuid', 'id'))
        unti_id_to_id = dict(User.objects.filter(unti_id__isnull=False).values_list('unti_id', 'id'))
        failed_unti_ids = set()
        for resp in PTApi().fetch_teams():
            for item in resp:
                context_ids = set()
                for ct in item['contexts']:
                    ct_id = context_uuid_to_id.get(ct['uuid'])
                    if ct_id is None:
                        logging.error('Context with uuid %s not found', ct['uuid'])
                        continue
                    context_ids.add(ct_id)
                user_ids = set()
                for u in item['users']:
                    if u['unti_id'] in failed_unti_ids:
                        continue
                    user_id = unti_id_to_id.get(u['unti_id'])
                    if user_id is None:
                        user = pull_sso_user(u['unti_id'])
                        if not user:
                            failed_unti_ids.add(u['unti_id'])
                            logging.error('User with unti_id %s not found', u['unti_id'])
                            continue
                        unti_id_to_id[u['unti_id']] = user.id
                        user_id = user.id
                    user_ids.add(user_id)
                if not context_ids:
                    logging.error('PT team %s has no valid contexts', item['uuid'])
                    continue
                if not user_ids:
                    logging.error('PT team %s has no valid users', item['uuid'])
                    continue
                team = Team.objects.update_or_create(uuid=item['uuid'], defaults={
                    'name': item['title'],
                    'system': Team.SYSTEM_PT
                })[0]
                team_contexts = set(team.contexts.values_list('id', flat=True))
                if context_ids != team_contexts:
                    team.contexts.set(context_ids)
                team_users = set(team.users.values_list('id', flat=True))
                if user_ids != team_users:
                    team.users.set(user_ids)
    except Exception:
        logging.exception('Failed to fetch teams')


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


def get_release_version():
    try:
        with open(os.path.join(settings.BASE_DIR, 'release')) as f:
            return f.read().strip()
    except:
        logging.exception('Failed to read release version')


def check_mysql_connection():
    try:
        Context.objects.first()
        return 'ok'
    except:
        logging.exception('Mysql check failed')


class EventMaterialsCSV:
    """
    класс, генерирующий строки для csv выгрузки всех файлов мероприятия
    """
    TYPE_PERSONAL = 1
    TYPE_TEAM = 2
    TYPE_EVENT = 3
    DT_FORMAT = '%d/%m/%Y %H:%M:%S'

    def __init__(self, event):
        self.event = event
        self.teams_data_cache = {}
        self.model_names = dict(MetaModel.objects.values_list('uuid', 'title'))
        self.competence_names = dict(DpCompetence.objects.values_list('uuid', 'title'))

    def field_names(self):
        return OrderedDict([
            ('type', _('Тип результатов')),
            ('title', _('Название активности')),
            ('dt_start', _('Дата начала')),
            ('dt_end', _('Дата окончания')),
            ('initiator', _('Кто загрузил (UntiID)')),
            ('team_id', _('ID команды')),
            ('team_title', _('Название команды')),
            ('unti_id', _('UntiID пользователя')),
            ('leader_id', _('LeaderID')),
            ('last_name', _('Фамилия')),
            ('first_name', _('Имя')),
            ('second_name', _('Отчество')),
            ('block_title', _('Название блока')),
            ('result_title', _('Ожидаемый результат')),
            ('file_url', _('Ссылка на артефакт')),
            ('file_extension', _('Расширение файла артефакта')),
            ('comment', _('Комментарий')),
            ('sector', _('сектор')),
            ('level', _('уровень')),
            ('sublevel', _('подуровень')),
            ('meta_instruments', _('Инструменты')),
            ('meta_model', _('Модель цифрового профиля')),
            ('meta_activity', _('Деятельность из свойств блока')),
            ('meta_type', _('Тип из свойств блока')),
            ('meta_sector_name', _('Название сектора')),
            ('lines_num', _('Количество строк с файлом')),
        ])

    def default_line(self):
        d = OrderedDict([(k, '') for k in self.field_names()])
        self.populate_common_data(d)
        return d

    def generate_headers(self):
        return self.field_names().values()

    def generate(self):
        yield self.generate_headers()
        for line in self.generate_for_event():
            yield line

    def generate_for_event(self):
        personal_materials = EventMaterial.objects.filter(event=self.event).\
            select_related('result_v2', 'result_v2__result', 'result_v2__result__block', 'user').\
            prefetch_related('result_v2__result__circle_items')
        team_materials = EventTeamMaterial.objects.filter(event=self.event).\
            select_related('result_v2', 'result_v2__result', 'result_v2__result__block').\
            prefetch_related('result_v2__result__circle_items')
        event_materials = EventOnlyMaterial.objects.filter(event=self.event)

        for m in personal_materials.iterator():
            for line in self.lines_for_personal_material(m):
                yield line.values()
        for m in team_materials.iterator():
            for line in self.lines_for_team_material(m):
                yield line.values()
        for m in event_materials.iterator():
            for line in self.lines_for_event_material(m):
                yield line.values()

    def lines_for_personal_material(self, m):
        default = self.default_line()
        self.populate_material_data(default, m, self.TYPE_PERSONAL)
        self.populate_user_data(default, m.user)
        self.populate_result_data(default, m)
        meta = self.get_meta(m)
        meta_objects_num = max(len(meta), 1)
        default['lines_num'] = meta_objects_num
        if meta:
            for item in meta:
                line = default.copy()
                self.populate_meta(line, item)
                yield line
        else:
            yield default

    def lines_for_team_material(self, m):
        default = self.default_line()
        self.populate_material_data(default, m, self.TYPE_TEAM)
        self.populate_result_data(default, m)
        meta = self.get_meta(m)
        meta_objects_num = max(len(meta), 1)
        team_data = self._get_team_data(m.team_id)
        default.update({
            'lines_num': meta_objects_num * len(team_data['members']),
            'team_id': m.team_id,
            'team_title': team_data['title'],
        })
        for user in team_data['members']:
            user_line = default.copy()
            self.populate_user_data(user_line, user)
            if meta:
                for item in meta:
                    line = user_line.copy()
                    self.populate_meta(line, item)
                    yield line
            else:
                yield user_line

    def lines_for_event_material(self, m):
        default = self.default_line()
        self.populate_material_data(default, m, self.TYPE_EVENT)
        default['lines_num'] = 1
        yield default

    def populate_common_data(self, d):
        d.update({
            'title': self.event.title,
            'dt_start': self.dt_start,
            'dt_end': self.dt_end,
        })

    def populate_material_data(self, d, m, material_type):
        d.update({
            'initiator': m.initiator or '',
            'file_url': m.get_url(),
            'file_extension': m.get_extension(),
            'comment': self.get_comment(m, material_type),
            'type': self.get_type(material_type),
        })

    def populate_user_data(self, d, user):
        d.update({
            'unti_id': user.unti_id or '',
            'leader_id': user.leader_id or '',
            'last_name': user.last_name,
            'first_name': user.first_name,
            'second_name': user.second_name,
        })

    def populate_result_data(self, d, m):
        d.update({
            'block_title': m.result_v2 and m.result_v2.result.block.title or '',
            'result_title': m.result_v2 and m.result_v2.result.title or '',
            'meta_type': m.result_v2 and m.result_v2.result.block.block_type,
            'meta_activity': m.result_v2 and m.result_v2.result.block.description,
        })

    def populate_meta(self, d, meta_item):
        d.update({
            'sector': meta_item.get('sector', ''),
            'level': meta_item.get('level', ''),
            'sublevel': meta_item.get('sublevel', ''),
            'meta_instruments': self.format_tools(meta_item.get('tools')),
            'meta_model': self.model_names.get(meta_item.get('model'), ''),
            'meta_sector_name': self.competence_names.get(meta_item.get('competence'), ''),
        })

    def format_tools(self, tools):
        if tools:
            if isinstance(tools, list) and all(isinstance(i, str) for i in tools):
                return ', '.join(tools)
            return str(tools)
        return ''

    def get_meta(self, m):
        if m.result_v2 and isinstance(m.result_v2.result.meta, list) and \
                all(isinstance(i, dict) for i in m.result_v2.result.meta):
            return m.result_v2.get_meta()
        return []

    def get_type(self, m_type):
        return {
            self.TYPE_PERSONAL: _('Персональный'),
            self.TYPE_TEAM: _('Групповой'),
            self.TYPE_EVENT: _('Материал мероприятия'),
        }.get(m_type)

    @cached_property
    def dt_start(self):
        return self.get_formatted_dt(self.event.dt_start)

    @cached_property
    def dt_end(self):
        return self.get_formatted_dt(self.event.dt_end)

    def get_formatted_dt(self, dt):
        return dt and dt.strftime(self.DT_FORMAT) or ''

    def get_comment(self, m, m_type):
        if m_type != self.TYPE_EVENT and m.result_v2:
            return m.result_v2.comment
        return m.comment

    def _get_team_data(self, team_id):
        if team_id not in self.teams_data_cache:
            team = Team.objects.prefetch_related('users').get(id=team_id)
            team_data = {'members': list(team.get_members_for_event(self.event)), 'title': team.name}
            self.teams_data_cache[team_id] = team_data
        return self.teams_data_cache[team_id]

    def get_csv_filename(self):
        return quote('{} - {}'.format(self.event.title, self.dt_start))

    def has_contents(self):
        return EventMaterial.objects.filter(event=self.event).count() + \
               EventTeamMaterial.objects.filter(event=self.event).count() + \
               EventOnlyMaterial.objects.filter(event=self.event).count() > 0


class EventGroupMaterialsCSV(EventMaterialsCSV):
    def __init__(self, events_qs, meta_data):
        self.meta_data = meta_data
        self.events_qs = events_qs
        super().__init__(None)

    def field_names(self):
        return OrderedDict([('event_uuid', _('UUID мероприятия'))] + list(super().field_names().items()))

    def populate_common_data(self, d):
        super().populate_common_data(d)
        d.update({'event_uuid': self.event.uid})

    def generate(self):
        yield self.generate_headers()
        for event in self.events_qs:
            self.event = event
            self.teams_data_cache = {}
            for line in self.generate_for_event():
                yield line

    def get_csv_filename(self, do_quote=True):
        f = quote if do_quote else lambda x: x
        guid = str(self.meta_data['context'] and self.meta_data['context'].guid)
        if self.meta_data['activity']:
            return f('{}_{}'.format(guid, self.meta_data['activity'].title))
        date_min = self.meta_data['date_min']
        date_max = self.meta_data['date_max']
        return f('{}_{}-{}'.format(
            guid,
            date_min.strftime('%d-%m-%Y') if date_min else 'null',
            date_max.strftime('%d-%m-%Y') if date_max else 'null'
        ))

    def count_materials(self):
        ids = list([i.id for i in self.events_qs])
        return EventMaterial.objects.filter(event_id__in=ids).count() + \
               EventTeamMaterial.objects.filter(event_id__in=ids).count() + \
               EventOnlyMaterial.objects.filter(event_id__in=ids).count()


class BytesCsvStreamWriter:
    def __init__(self, encoding):
        self.encoding = encoding

    def write(self, value):
        return value.encode(self.encoding)


class BytesCsvObjWriter:
    def __init__(self, encoding):
        self.file = io.BytesIO()
        self.encoding = encoding

    def write(self, value):
        self.file.write(value.encode(self.encoding))


def get_csv_encoding_for_request(request):
    try:
        os_family = request.user_agent.os.family or ''
    except AttributeError:
        os_family = ''
    overridden_encoding = settings.CSV_ENCODING_FOR_OS.get(os_family.lower())
    return overridden_encoding or settings.DEFAULT_CSV_ENCODING


def update_casbin_data():
    try:
        data = SSOApi().get_casbin_data()
        cdata = CasbinData.objects.first()
        if cdata:
            CasbinData.objects.filter(id=cdata.id).update(model=data['model'], policy=data['policy'])
        else:
            CasbinData.objects.create(model=data['model'], policy=data['policy'])
        UserAvailableContexts.discard_many(User.objects.all().iterator())
    except ApiError:
        pass
    except (TypeError, KeyError):
        logging.exception('Unexpected format for casbin data')


class XLSWriter:
    def __init__(self, f):
        self.workbook = xlsxwriter.Workbook(f)
        self.worksheet = self.workbook.add_worksheet()
        self.current_row = 0

    def writerow(self, row):
        for pos, item in enumerate(row):
            self.worksheet.write(self.current_row, pos, item)
        self.current_row += 1

    def close(self):
        self.workbook.close()


def check_celery_active():
    if settings.DEBUG and getattr(settings, 'CELERY_ALWAYS_EAGER', False):
        return True
    try:
        stat = inspect().stats()
        if not stat:
            return False
        return True
    except IOError:
        return False


def create_traces_for_event_type(obj):
    data = obj.trace_data
    if data:
        traces = {}
        for t in Trace.objects.filter(event_type=obj, ext_id__isnull=True):
            traces[(t.trace_type, t.name)] = t.id
        added_traces = set()
        active_traces = set()
        for i in data:
            item = (i['trace_type'], i['name'])
            added_traces.add(item)
            if item in traces:
                active_traces.add(traces[item])
                continue
            Trace.objects.create(event_type=obj, **i)
        Trace.objects.filter(id__in=active_traces).update(deleted=False)
        for item, trace_id in traces.items():
            if item not in added_traces:
                Trace.objects.filter(id=trace_id).update(deleted=True)
                logging.warning('Trace #%s %s was deleted' % (trace_id, item))


def calculate_user_context_statistics(user, context):
    """
    Пересчет статистики для пользователя в контексте
    """
    stat = DTraceStatistics(user_id=user.id, context_id=context.id, updated_at=timezone.now())
    context_event_ids = list(Event.objects.filter(context=context).values_list('id', flat=True))
    event_entries = set(
        EventEntry.objects.filter(user=user, event_id__in=context_event_ids).values_list('event_id', flat=True)
    )
    stat.n_entry = len(event_entries)
    stat.n_run_entry = RunEnrollment.objects.filter(
        user=user,
        run_id__in=Event.objects.filter(context=context, run__isnull=False).values('run_id')
    ).count()
    stat.n_personal = EventMaterial.objects.filter(user=user, event_id__in=context_event_ids).count()
    user_context_events = set(Event.objects.filter(
        run_id__in=RunEnrollment.objects.filter(user=user).values_list('run_id'), context=context
    ).values_list('id', flat=True)) | event_entries
    uploads_team_files = EventTeamMaterial.objects.filter(
        team__system=Team.SYSTEM_UPLOADS, team__users=user, event_id__in=context_event_ids
    ).count()
    pt_team_files = EventTeamMaterial.objects.filter(
        team__system=Team.SYSTEM_PT, team__users=user, event_id__in=user_context_events
    ).count()
    stat.n_team = uploads_team_files + pt_team_files
    if user.unti_id:
        stat.n_event = EventOnlyMaterial.objects.filter(initiator=user.unti_id, event_id__in=context_event_ids).count()
    else:
        stat.n_event = 0
    if DTraceStatistics.update_entry(stat):
        DTraceStatisticsHistory.copy_from_statistics(stat).save()


def calculate_context_statistics(context):
    """
    Пересчет статистики по всем пользователям контекста
    """
    now = timezone.now()
    by_user = defaultdict(DTraceStatistics)

    # сбор статистики по записям на мероприятия контекста и пополнение словаря участников мероприятий
    event_participants = defaultdict(set)
    qs = EventEntry.objects.filter(event__context=context).values_list('user_id', 'event_id')
    for user_id, event_id in qs.iterator():
        by_user[user_id].n_entry += 1
        event_participants[event_id].add(user_id)

    # пополнение словаря мероприятий прогона
    run_events = defaultdict(list)
    for event_id, run_id in Event.objects.filter(context=context, run__isnull=False).values_list('id', 'run_id'):
        run_events[run_id].append(event_id)

    # сбор статистики по записям на прогоны контекста и пополнение словаря участников мероприятий
    qs = RunEnrollment.objects.filter(run_id__in=run_events.keys()).values_list('user_id', 'run_id')
    for user_id, run_id in qs.iterator():
        by_user[user_id].n_run_entry += 1
        for event_id in run_events.get(run_id, []):
            event_participants[event_id].add(user_id)

    # сбор статистики по персональному цс
    qs = EventMaterial.objects.filter(event__context=context).values_list('user_id', flat=True).iterator()
    for user_id in qs:
        by_user[user_id].n_personal += 1

    # сбор статистики по командному цс
    team_users = defaultdict(set)
    TeamUser = Team._meta.get_field('users').remote_field.through
    qs = TeamUser.objects.filter(
        models.Q(team__system=Team.SYSTEM_UPLOADS, team__event__context=context) |
        models.Q(team__system=Team.SYSTEM_PT, team__contexts=context)
    ).values_list('team_id', 'user_id')
    for team_id, user_id in qs.iterator():
        team_users[team_id].add(user_id)
    qs = EventTeamMaterial.objects.filter(team_id__in=team_users.keys())\
        .values_list('team_id', 'event_id', 'team__system')
    for team_id, event_id, system in qs.iterator():
        for user_id in team_users.get(team_id, []):
            if system == Team.SYSTEM_UPLOADS:
                by_user[user_id].n_team += 1
            # если это команда, полученная из pt, командный материал засчитывается для пользователя только
            # в том случае, если он записан на мероприятие или его прогон
            elif system == Team.SYSTEM_PT and user_id in event_participants[event_id]:
                by_user[user_id].n_team += 1

    # сбор статистики по загрузкам материалов мероприятия
    unti_id_to_user_id = dict(User.objects.filter(unti_id__isnull=False).values_list('unti_id', 'id'))
    qs = EventOnlyMaterial.objects.filter(event__context=context, initiator__isnull=False)\
        .values_list('initiator', flat=True)
    for unti_id in qs.iterator():
        user_id = unti_id_to_user_id.get(unti_id)
        if user_id:
            by_user[user_id].n_event += 1

    bulk = []
    for user_id, stat in by_user.items():
        stat.updated_at = now
        stat.user_id = user_id
        stat.context_id = context.id
        if DTraceStatistics.update_entry(stat):
            bulk.append(DTraceStatisticsHistory.copy_from_statistics(stat))
    bulk_size = 100
    for i in range(0, len(bulk), bulk_size):
        DTraceStatisticsHistory.objects.bulk_create(bulk[i:(i+bulk_size)])
