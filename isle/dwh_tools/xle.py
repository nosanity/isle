import logging
from django.utils.dateparse import parse_datetime
from isle.models import UpdateTimes, Event, EventEntry, Run, RunEnrollment, User
from isle.utils import pull_sso_user
from .utils import get_dwh_connect, change_update_time, parse_dt


@change_update_time(UpdateTimes.DWH_CHECKINS)
def update_event_entries(dt=None):
    db = get_dwh_connect('xle')
    cur = db.cursor()
    query = 'select C.attendance, C.checkin, E.uuid, UI.untiID from checkin C ' \
            'inner join event E on C.eventID=E.id ' \
            'inner join user U on C.userID=U.id ' \
            'inner join user_info UI on U.id=UI.userID'
    if dt:
        query = "{query} where C.id in (select checkinID from checkin_log where createDT >= '{dt}')".\
            format(query=query, dt=dt)
    cur.execute(query)
    data = cur.fetchall()
    event_uuid_to_id = dict(Event.objects.values_list('uid', 'id'))
    user_unti_id_to_id = dict(User.objects.filter(unti_id__isnull=False).values_list('unti_id', 'id'))
    failed_users = set()
    existing = set(EventEntry.objects.values_list('event_id', 'user_id'))
    for item in data:
        if not (item[0] or item[1]):
            continue
        user_id = user_unti_id_to_id.get(item[3])
        event_id = event_uuid_to_id.get(item[2])
        if not user_id:
            if item[3] in failed_users:
                continue
            else:
                user = pull_sso_user(item[3])
                if not user:
                    failed_users.add(item[3])
                    continue
                user_id = user.id
                user_unti_id_to_id[item[3]] = user_id
        if user_id and event_id and (event_id, user_id) not in existing:
            EventEntry.all_objects.update_or_create(event_id=event_id, user_id=user_id, defaults={
                'deleted': False
            })


@change_update_time(UpdateTimes.DWH_RUN_ENROLLMENTS)
def update_run_enrollments(dt=None):
    db = get_dwh_connect('xle')
    cur = db.cursor()
    query = "select R.uuid, UI.untiID from timetable T " \
            "inner join run R on R.id=T.runID " \
            "inner join user U on T.userID=U.id " \
            "inner join user_info UI on U.id=UI.userID "
    if dt:
        query = "{query} where T.createDT  >= '{dt}'".format(query=query, dt=dt)
    cur.execute(query)
    data = cur.fetchall()
    run_uuid_to_id = dict(Run.objects.values_list('uuid', 'id'))
    user_unti_id_to_id = dict(User.objects.filter(unti_id__isnull=False).values_list('unti_id', 'id'))
    failed_users = set()
    existing = set(RunEnrollment.objects.values_list('run_id', 'user_id'))
    for item in data:
        user_id = user_unti_id_to_id.get(item[1])
        run_id = run_uuid_to_id.get(item[0])
        if not user_id:
            if item[1] in failed_users:
                continue
            else:
                user = pull_sso_user(item[1])
                if not user:
                    failed_users.add(item[1])
                    continue
                user_id = user.id
                user_unti_id_to_id[item[1]] = user_id
        if user_id and run_id and (run_id, user_id) not in existing:
            RunEnrollment.all_objects.update_or_create(run_id=run_id, user_id=user_id, defaults={
                'deleted': False,
            })


@change_update_time(UpdateTimes.DELETE_RUN_ENROLLMENTS, pass_current_time=True)
def clear_deleted_run_enrollments(dt=None, now=None):
    db = get_dwh_connect('xle')
    cur = db.cursor()
    query = "select R.uuid, UI.untiID from timetable T " \
            "inner join run R on R.id=T.runID " \
            "inner join user U on T.userID=U.id " \
            "inner join user_info UI on U.id=UI.userID"
    if dt:
        query = "{query} where T.createDT  >= '{dt}'".format(query=query, dt=dt)
    cur.execute(query)
    data = cur.fetchall()
    filter_dict = {'created__lt': now}
    if dt:
        filter_dict['created__gte'] = parse_dt(parse_datetime(dt))
    qs = RunEnrollment.objects.exclude(created__isnull=True).filter(**filter_dict)
    created_enrollments = {(i[0], i[1]): i[2] for i in qs.values_list('run__uuid', 'user__unti_id', 'id').iterator()}
    ids = set()
    for item in data:
        if not item[1]:
            continue
        run_enrollment_id = created_enrollments.get((item[0], item[1]))
        if run_enrollment_id:
            ids.add(run_enrollment_id)
    res = qs.exclude(id__in=ids).update(deleted=True)
    logging.info('%s RunEnrollment entries marked as deleted', res)
