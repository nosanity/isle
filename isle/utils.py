import logging
from django.conf import settings
from django.core.cache import caches
from django.utils import timezone
from django.utils.dateparse import parse_datetime
import requests
from isle.api import Api, ApiError
from isle.models import Event, EventEntry, User, Trace, EventType

DEFAULT_CACHE = caches['default']
EVENT_TYPES_CACHE_KEY = 'EVENT_TYPE_IDS'


def get_allowed_event_type_ids():
    ids = DEFAULT_CACHE.get(EVENT_TYPES_CACHE_KEY)
    if ids is None:
        ids = [i.id for i in EventType.objects.all() if i.title.lower() in settings.VISIBLE_EVENT_TYPES]
        DEFAULT_CACHE.set(EVENT_TYPES_CACHE_KEY, ids)
    return ids


def refresh_events_data(force=False, refresh_participants=False, refresh_for_events=()):
    """
    Обновление списка эвентов. Предполагается, что этот список меняется редко (или не меняется вообще).
    В процессе обновления эвент может быть удален, но только если он запланирован как минимум на следующий день.
    """
    try:
        data, updated = Api().get_events_data(force=force)
    except ApiError:
        return
    if not updated:
        return True
    try:
        DEFAULT_CACHE.delete(EVENT_TYPES_CACHE_KEY)
        event_types = {}
        existing_uids = set(Event.objects.values_list('uid', flat=True))
        fetched_events = set()
        unti_id_to_user_id = dict(User.objects.values_list('unti_id', 'id'))
        activities = data.get('activities') or []
        for activity in activities:
            title = activity.get('title', '')
            runs = activity.get('runs') or []
            event_type = None
            activity_type = activity.get('activity_type')
            if activity_type and activity_type.get('id'):
                event_type = event_types.get(int(activity_type['id']))
                if not event_type:
                    event_type = EventType.objects.update_or_create(
                        ext_id=int(activity_type['id']),
                        defaults={'title': activity_type.get('title'),
                                  'description': activity_type.get('description') or ''}
                    )[0]
            for run in runs:
                events = run.get('events') or []
                assignments = run.get('assignments') or []
                participant_ids = []
                for assignment in assignments:
                    unti_id = (assignment.get('user') or {}).get('unti_id')
                    if unti_id:
                        participant_ids.append(int(unti_id))
                for event in events:
                    uid = event['uuid']
                    if refresh_for_events and uid not in refresh_for_events:
                        continue
                    timeslot = event.get('time_slot')
                    dt_start, dt_end = None, None
                    if timeslot:
                        dt_start = parse_datetime(timeslot['time_start'])
                        dt_end = parse_datetime(timeslot['time_end'])
                    e = Event.objects.update_or_create(uid=uid, defaults={
                        'ile_id': event.get('id'),
                        'dt_start': dt_start, 'dt_end': dt_end, 'title': title, 'event_type': event_type})[0]
                    fetched_events.add(e.uid)
                    if not refresh_participants:
                        continue
                    for ptcpt in participant_ids:
                        user_id = unti_id_to_user_id.get(ptcpt)
                        if not user_id:
                            logging.error('User with unti_id %s not found' % ptcpt)
                            continue
                        EventEntry.objects.get_or_create(user_id=user_id, event_id=e.id)
                    check_ins = event.get('check_ins') or []
                    for check_in in check_ins:
                        user_id = unti_id_to_user_id.get(check_in['user']['unti_id'])
                        if not user_id:
                            continue
                        EventEntry.objects.filter(event_id=e.id, user_id=user_id).update(
                            is_active=check_in['is_confirmed'])
        if not refresh_for_events:
            delete_events = existing_uids - fetched_events
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
        assert resp.ok
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
    try:
        data = Api().get_check_ins_data(event.ile_id)
        unti_id_to_user_id = dict(User.objects.values_list('unti_id', 'id'))
        active, inactive = [], []
        for check_in in data:
            user_id = unti_id_to_user_id.get(check_in['user']['unti_id'])
            if not user_id:
                continue
            if check_in['is_confirmed']:
                active.append(user_id)
            else:
                inactive.append(user_id)
        EventEntry.objects.filter(event_id=event.id, user_id__in=active).update(is_active=True)
        EventEntry.objects.filter(event_id=event.id, user_id__in=inactive).update(is_active=False)
        return True
    except ApiError:
        return False


def set_check_in(event, user, confirmed):
    try:
        Api().set_check_in(event.ile_id, user.unti_id, confirmed)
        return True
    except ApiError:
        return False
