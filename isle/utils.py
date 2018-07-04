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
        activities = data.get('Activity', [])
        for activity in activities:
            runs = activity.get('Run', [])
            for run in runs:
                events = run.get('Event', [])
                for event in events:
                    ### uid
                    uid = event['event_uid']
                    if refresh_for_events and uid not in refresh_for_events:
                        continue
                    dt_start = parse_datetime(event['time_start_replace'])
                    dt_end = parse_datetime(event['time_end_replace'])
                    e = Event.objects.update_or_create(uid=uid, defaults={'dt_start': dt_start, 'dt_end': dt_end})[0]
                    if not refresh_participants:
                        continue
                    participants = event.get('CheckIn', [])
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
