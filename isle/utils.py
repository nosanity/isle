import logging
from django.utils.dateparse import parse_datetime
from isle.api import Api, ApiError
from isle.models import Event, EventEntry, User


def refresh_events_data(force=False, refresh_participants=False, refresh_for_events=()):
    """
    обновление данных по всем эвентам или по участникам определенных эвентов
    используется для периодического обновления данных или для принудительного обновления
    """
    try:
        data, updated = Api().get_events_data(force=force)
    except ApiError:
        return
    if not updated:
        return True
    try:
        unti_id_to_user_id = dict(User.objects.values_list('unti_id', 'id'))
        activities = data.get('activities') or []
        for activity in activities:
            title = activity.get('title', '')
            runs = activity.get('runs') or []
            for run in runs:
                events = run.get('events') or []
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
                        'dt_start': dt_start, 'dt_end': dt_end, 'title': title})[0]
                    if not refresh_participants:
                        continue
                    participants = event.get('check_ins') or []
                    for ptcpt in participants:
                        user_id = unti_id_to_user_id.get(ptcpt['user_id'])
                        if not user_id:
                            logging.error('User with unti_id %s not found' % ptcpt['user_id'])
                            continue
                        EventEntry.objects.update_or_create(user_id=user_id, event_id=e.id,
                                                            defaults={'is_active': ptcpt['is_presence_confirmed']})
        return True
    except Exception:
        logging.exception('Failed to handle events data')
