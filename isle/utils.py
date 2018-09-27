import logging
from datetime import datetime
from django.conf import settings
from django.core.cache import caches
from django.utils import timezone
from django.utils.dateparse import parse_datetime
import requests
from isle.api import Api, ApiError, ApiNotFound, LabsApi
from isle.models import Event, EventEntry, User, Trace, EventType, Activity

DEFAULT_CACHE = caches['default']
EVENT_TYPES_CACHE_KEY = 'EVENT_TYPE_IDS'


def get_allowed_event_type_ids():
    ids = DEFAULT_CACHE.get(EVENT_TYPES_CACHE_KEY)
    if ids is None:
        ids = [i.id for i in EventType.objects.all() if i.title.lower() in settings.VISIBLE_EVENT_TYPES]
        DEFAULT_CACHE.set(EVENT_TYPES_CACHE_KEY, ids)
    return ids


def refresh_events_data():
    """
    Обновление списка эвентов и активностей. Предполагается, что этот список меняется редко (или не меняется вообще).
    В процессе обновления эвент может быть удален, но только если он запланирован как минимум на следующий день.
    """
    try:
        data = LabsApi().get_activities()
    except ApiError:
        return
    try:
        event_types = {}
        existing_uids = set(Event.objects.values_list('uid', flat=True))
        fetched_events = set()
        activities = data
        filter_dict = lambda d, excl: {k: d.get(k) for k in d if k not in excl}
        ACTIVITY_EXCLUDE_KEYS = ['runs', 'activity_type']
        RUN_EXCLUDE_KEYS = ['events']
        EVENT_EXCLUDE_KEYS = ['time_slot']
        for activity in activities:
            title = activity.get('title', '')
            runs = activity.get('runs') or []
            event_type = None
            activity_types = activity.get('type')
            activity_type = activity_types and activity_types[0]
            activity_json = filter_dict(activity, ACTIVITY_EXCLUDE_KEYS)
            activity_json['ext_id'] = activity_json.get('id')
            activity_uid = activity.get('uuid')
            if activity_uid:
                main_author = ''
                authors = activity.get('authors') or []
                for author in authors:
                    if author.get('is_main'):
                        main_author = author.get('title')
                        break
                Activity.objects.update_or_create(
                    uid=activity_uid,
                    defaults={
                        'ext_id': activity.get('id'),
                        'title': title,
                        'main_author': main_author,
                        'is_deleted': bool(activity.get('is_deleted')),
                    }
                )
            if activity_type and activity_type.get('id'):
                event_type = event_types.get(int(activity_type['id']))
                if not event_type:
                    event_type = EventType.objects.update_or_create(
                        ext_id=int(activity_type['id']),
                        defaults={'title': activity_type.get('title'),
                                  'description': activity_type.get('description') or ''}
                    )[0]
            for run in runs:
                run_json = filter_dict(run, RUN_EXCLUDE_KEYS)
                run_json['ext_id'] = run_json.get('id')
                events = run.get('events') or []
                for event in events:
                    event_json = filter_dict(event, EVENT_EXCLUDE_KEYS)
                    event_json['ext_id'] = event_json.get('id')
                    uid = event['uuid']
                    timeslot = event.get('time_slot')
                    is_active = False if event.get('is_delete') else True
                    dt_start, dt_end = datetime.now(), datetime.now()
                    if timeslot:
                        dt_start = parse_datetime(timeslot['start']) or datetime.now()
                        dt_end = parse_datetime(timeslot['end']) or datetime.now()
                    e = Event.objects.update_or_create(uid=uid, defaults={
                        'is_active': is_active,
                        'ext_id': event.get('id'),
                        'data': {'event': event_json, 'run': run_json, 'activity': activity_json},
                        'dt_start': dt_start, 'dt_end': dt_end, 'title': title, 'event_type': event_type})[0]
                    fetched_events.add(e.uid)
        delete_events = existing_uids - fetched_events
        Event.objects.filter(uid__in=delete_events).update(is_active=False)
        # если произошли изменения в списке будущих эвентов
        dt = timezone.now() + timezone.timedelta(days=1)
        delete_qs = Event.objects.filter(uid__in=delete_events, dt_start__gt=dt)
        delete_events = delete_qs.values_list('uid', flat=True)
        if delete_events:
            logging.warning('Event(s) with uuid: {} were deleted'.format(', '.join(delete_events)))
            delete_qs.delete()
        return True
    except Exception:
        logging.exception('Failed to handle events data')


def update_events_traces():
    """
    обновление трейсов по всем эвентам
    """
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
