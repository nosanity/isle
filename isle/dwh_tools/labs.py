import json
from collections import defaultdict
from django.conf import settings
from django.utils import timezone
from isle.models import UpdateTimes, Context, Activity, Run, Event, EventType, Author, User, EventAuthor, MetaModel, \
    DpCompetence, CircleItem, LabsEventBlock, LabsEventResult
from isle.utils import create_traces_for_event_type, pull_sso_user, create_circle_items_for_result
from .utils import get_dwh_connect, parse_dt, change_update_time


@change_update_time(UpdateTimes.CONTEXTS)
def update_contexts(dt=None):
    db = get_dwh_connect('labs')
    cur = db.cursor()
    query = 'select uuid, guid, timezone, title from context'
    if dt:
        query = "{query} where createDt >= '{dt}' or dt >= '{dt}'".format(query=query, dt=dt)
    cur.execute(query)
    data = cur.fetchall()
    for item in data:
        Context.objects.update_or_create(uuid=item[0], defaults={
            'guid': item[1],
            'timezone': item[2],
            'title': item[3],
        })


@change_update_time(UpdateTimes.EVENT_RUN_ACTIVITY)
def update_events(dt=None):
    db = get_dwh_connect('labs')
    cur = db.cursor()
    query = 'select E.uuid, R.uuid, A.uuid, A.title, E.isDeleted, R.isDeleted, A.isDeleted, T.startDT, T.endDT, ' \
            'P.title ' \
            'from event E ' \
            'inner join run R on R.id=E.runID ' \
            'inner join activity A on A.id=R.activityID ' \
            'left outer join timeslot T on T.id=E.timeslotID ' \
            'left outer join place P on P.id=E.placeID'
    if dt:
        query = "{query} where E.createDt >= '{dt}' or E.dt >= '{dt}' or R.createDt >= '{dt}' or R.dt >= '{dt}' " \
                "or A.createDt >= '{dt}' or A.dt >= '{dt}'".format(query=query, dt=dt)
    cur.execute(query)
    data = cur.fetchall()
    activity_uuid_to_id = {}
    run_uuid_to_id = {}
    for item in data:
        activity_id = activity_uuid_to_id.get(item[2])
        if not activity_id:
            activity_id = Activity.objects.update_or_create(uid=item[2], defaults={
                'title': item[3],
                'is_deleted': item[6],
            })[0].id
            activity_uuid_to_id[item[2]] = activity_id
        run_id = run_uuid_to_id.get(item[1])
        if not run_id:
            run_id = Run.objects.update_or_create(uuid=item[1], defaults={
                'deleted': item[5] or item[6],
                'activity_id': activity_id,
            })[0].id
        dt_start = parse_dt(item[7], default=timezone.now())
        dt_end = parse_dt(item[8], default=timezone.now())
        Event.objects.update_or_create(uid=item[0], defaults={
            'is_active': not (item[4] or item[5] or item[6]),
            'activity_id': activity_id,
            'run_id': run_id,
            'dt_start': dt_start,
            'dt_end': dt_end,
            'title': item[3],
            'data': {'place_title': item[9]},
        })


@change_update_time(UpdateTimes.EVENT_CONTEXTS)
def update_event_contexts(dt=None):
    # TODO: поддержка нескольких контекстов для мероприятий
    # пока, если для тех редких мероприятий, для которых задано более 1 контекста,
    # выбирается первый отсортированный по id
    db = get_dwh_connect('labs')
    cur = db.cursor()
    query = "select C.uuid, R.uuid, R.activityID from context_run CR " \
            "inner join context C on C.id=CR.contextID " \
            "inner join run R on R.id=CR.runID"
    if dt:
        query = "{query} where R.createDT >= '{dt}' or R.dt >= '{dt}'".format(query=query, dt=dt)
    cur.execute(query)
    run_context_raw = cur.fetchall()
    query = "select C.uuid, R.uuid from context_activity CA " \
            "inner join context C on C.id=CA.contextID " \
            "inner join activity A on CA.activityID=A.id " \
            "left outer join run R on R.activityID=CA.activityID "
    if dt:
        query = "{query} where A.createDT >= '{dt}' or A.dt >= '{dt}'".format(query=query, dt=dt)
        if run_context_raw:
            activity_ids = set(map(lambda x: x[2], run_context_raw))
            query = "{query} or CA.activityID in ({ids})".format(
                query=query, ids=', '.join(map(lambda x: str(x), activity_ids)))
    cur.execute(query)
    activity_context_raw = cur.fetchall()
    run_uuid_to_id = dict(Run.objects.values_list('uuid', 'id'))
    context_uuid_to_id = dict(Context.objects.values_list('uuid', 'id'))
    run_contexts = defaultdict(list)
    for context_uuid, run_uuid, _ in run_context_raw:
        run_id = run_uuid_to_id.get(run_uuid)
        context_id = context_uuid_to_id.get(context_uuid)
        if run_id and context_id:
            run_contexts[run_id].append(context_id)
    activity_contexts = defaultdict(list)
    for context_uuid, run_uuid in activity_context_raw:
        context_id = context_uuid_to_id.get(context_uuid)
        run_id = run_uuid_to_id.get(run_uuid)
        if run_id and context_id:
            activity_contexts[run_id].append(context_id)
    # контексты рана переопределяют контексты активности
    activity_contexts.update(run_contexts)
    for run_id, context_ids in activity_contexts.items():
        context_id = context_ids[0] if len(context_ids) == 1 else sorted(context_ids)[0]
        Event.objects.filter(run_id=run_id).update(context_id=context_id)


@change_update_time(UpdateTimes.EVENT_TYPES)
def update_event_types(dt=None):
    db = get_dwh_connect('labs')
    cur = db.cursor()
    query = 'select uuid, title, description from type'
    if dt:
        query = "{query} where createDt >= '{dt}' or dt >= '{dt}'".format(query=query, dt=dt)
    cur.execute(query)
    data = cur.fetchall()
    for item in data:
        et, created = EventType.objects.update_or_create(uuid=item[0], defaults={
            'title': item[1],
            'description': item[2] or '',
        })
        if created:
            et.trace_data = settings.DEFAULT_TRACE_DATA_JSON
            et.save(update_fields=['trace_data'])
            create_traces_for_event_type(et)


@change_update_time(UpdateTimes.EVENT_TYPE_CONNECTIONS)
def update_event_type_connections(dt=None):
    db = get_dwh_connect('labs')
    cur = db.cursor()
    query = 'select A.uuid, T.uuid from activity_type AT ' \
            'inner join activity A on AT.activityID=A.id ' \
            'inner join type T on AT.typeID=T.id'
    if dt:
        query = "{query} where A.createDt >= '{dt}' or A.dt >= '{dt}'".format(query=query, dt=dt)
    cur.execute(query)
    data = cur.fetchall()
    activity_uuid_to_id = dict(Activity.objects.values_list('uid', 'id'))
    event_type_uuid_to_id = dict(EventType.objects.values_list('uuid', 'id'))
    for item in data:
        activity_id = activity_uuid_to_id.get(item[0])
        event_type_id = event_type_uuid_to_id.get(item[1])
        if not activity_id or not event_type_id:
            continue
        Event.objects.filter(activity_id=activity_id).update(event_type_id=event_type_id)


@change_update_time(UpdateTimes.ACTIVITY_AUTHORS)
def update_authors(dt=None):
    db = get_dwh_connect('labs')
    cur = db.cursor()
    query = 'select uuid, title from author where id in (select authorID from activity_author)'
    if dt:
        query = "{query} and (createDt >= '{dt}' or dt >= '{dt}')".format(query=query, dt=dt)
    cur.execute(query)
    data = cur.fetchall()
    for item in data:
        Author.objects.update_or_create(uuid=item[0], defaults={
            'title': item[1],
            'is_main': None,
        })

    author_uuid_to_id = dict(Author.objects.values_list('uuid', 'id'))
    activities = {i.uid: i for i in Activity.objects.all()}
    query = 'select A.uuid, AA.isMain, AU.uuid, AU.title from activity_author AA ' \
            'inner join activity A on A.id=AA.activityID ' \
            'inner join author AU on AU.id=AA.authorID'
    if dt:
        query = "{query} where A.createDt >= '{dt}' or A.dt >= '{dt}'".format(query=query, dt=dt)
    query = '{} order by AA.activityID'.format(query)
    cur.execute(query)
    data = cur.fetchall()
    authors = []
    key, prev_key = None, None
    main_author = ''
    for item in data:
        key = item[0]
        if prev_key is not None and prev_key != key:
            activity = activities.get(prev_key)
            if activity:
                activity.authors.set(authors)
                Activity.objects.filter(id=activity.id).update(main_author=main_author)
            authors = []
            main_author = ''
        author_id = author_uuid_to_id.get(item[2])
        if author_id:
            authors.append(author_id)
        if item[1]:
            main_author = item[3]
        prev_key = key
    activity = activities.get(prev_key)
    if activity:
        activity.authors.set(authors)
        Activity.objects.filter(id=activity.id).update(main_author=main_author)


@change_update_time(UpdateTimes.EVENT_AUTHORS)
def update_event_authors(dt=None):
    db = get_dwh_connect('labs')
    cur = db.cursor()
    if not dt:
        query = "select A.uuid, UI.untiID from activity_author AA " \
                "inner join activity A on AA.activityID=A.id " \
                "inner join author AU on AU.id=AA.authorID " \
                "inner join user U on AU.userID=U.id " \
                "inner join user_info UI on UI.userID=U.id"
        query2 = "select E.uuid, UI.untiID from event_author EA " \
                 "inner join event E on EA.eventID=E.id " \
                 "inner join author AU on AU.id=EA.authorID " \
                 "inner join user U on AU.userID=U.id " \
                 "inner join user_info UI on UI.userID=U.id"
    else:
        query = "select A.uuid, UI.untiID from activity_author AA " \
                "inner join activity A on AA.activityID=A.id " \
                "inner join author AU on AU.id=AA.authorID " \
                "inner join user U on AU.userID=U.id " \
                "inner join user_info UI on UI.userID=U.id " \
                "where A.createDT >= '{dt}' or A.dt >= '{dt}' or A.id in (" \
                "select R.activityID from event E " \
                "inner join run R on E.runID=R.id " \
                "where E.createDT >= '{dt}' or E.dt >= '{dt}')".format(dt=dt)
        query2 = "select E.uuid, UI.untiID from event_author EA " \
                 "inner join event E on EA.eventID=E.id " \
                 "inner join author AU on AU.id=EA.authorID " \
                 "inner join user U on AU.userID=U.id " \
                 "inner join user_info UI on UI.userID=U.id " \
                 "where E.createDT >= '{dt}' or E.dt >= '{dt}'".format(dt=dt)
    cur.execute(query)
    activity_authors = cur.fetchall()
    cur.execute(query2)
    event_authors_raw = cur.fetchall()
    event_authors = set()
    event_uuid_to_id = dict(Event.objects.values_list('uid', 'id'))
    for e_uuid, unti_id in event_authors_raw:
        event_id = event_uuid_to_id.get(e_uuid)
        if event_id:
            event_authors.add((event_id, unti_id))
    event_activity = defaultdict(list)
    for a_uuid, e_id in Event.objects.filter(activity__isnull=False).values_list('activity__uid', 'id').iterator():
        event_activity[a_uuid].append(e_id)
    transformed_activity_authors = set()
    for item in activity_authors:
        for e_id in event_activity.get(item[0], []):
            transformed_activity_authors.add((e_id, item[1]))
    by_event = defaultdict(set)
    for container in (transformed_activity_authors, event_authors):
        for e_id, unti_id in container:
            by_event[e_id].add(unti_id)
    failed_users = set()
    unti_id_to_id = dict(User.objects.filter(unti_id__isnull=False).values_list('unti_id', 'id'))
    for e_id, unti_ids in by_event.items():
        user_ids = []
        for unti_id in unti_ids:
            user_id = unti_id_to_id.get(unti_id)
            if not user_id:
                if unti_id in failed_users:
                    continue
                user = pull_sso_user(unti_id)
                if not user:
                    failed_users.add(unti_id)
                    continue
                user_id = user.id
                unti_id_to_id[unti_id] = user_id
            user_ids.append(user_id)
            source = EventAuthor.SOURCE_EVENT if (e_id, unti_id) in event_authors else EventAuthor.SOURCE_ACTIVITY
            EventAuthor.objects.update_or_create(event_id=e_id, user_id=user_id, defaults={
                'is_active': True,
                'source': source,
            })
        EventAuthor.objects.filter(event_id=e_id).exclude(user_id__in=user_ids).update(is_active=False)


@change_update_time(UpdateTimes.EVENT_STRUCTURE)
def update_event_structure(dt=None):
    db = get_dwh_connect('labs')
    cur = db.cursor()
    query = "select E.uuid, B.uuid, B.title, B.description, TYPE.title, B.order, RES.uuid, RES.title, " \
            "RES.format, FIX.title, CHCK.title, RES.id, RES.meta from block_result RES " \
            "left outer join block_meta FIX on FIX.id=RES.fixID " \
            "left outer join block_meta CHCK on CHCK.id=RES.checkID " \
            "inner join block B on B.id=RES.blockID " \
            "left outer join block_meta TYPE on TYPE.id=B.typeID " \
            "inner join event E on E.id=B.eventID"
    if dt:
        event_ids_query = "select B.eventID from block_result R " \
                          "inner join block B on R.blockID=B.id " \
                          "where R.createDT >= '{dt}' or R.dt >= '{dt}' or B.createDT >= '{dt}' or B.dt >= '{dt}'".\
            format(dt=dt)
        cur.execute(event_ids_query)
        event_ids = cur.fetchall()
        query = "{query} where E.createDt >= '{dt}' or E.dt >= '{dt}'".format(query=query, dt=dt)
        if event_ids:
            query = '{query} or E.id in ({ids})'.format(
                query=query,
                ids=', '.join(map(lambda x: str(x[0]), event_ids)),
            )
    cur.execute(query)
    data = cur.fetchall()
    event_uuid_to_id = dict(Event.objects.values_list('uid', 'id'))
    block_uuid_to_id = {}
    events, blocks, results = set(), [], []
    metamodels = dict(MetaModel.objects.values_list('uuid', 'id'))
    competences = dict(DpCompetence.objects.values_list('uuid', 'id'))
    event_blocks, block_results = defaultdict(int), defaultdict(int)
    for item in data:
        event_id = event_uuid_to_id.get(item[0])
        events.add(event_id)
        if not event_id:
            continue
        if item[1] not in block_uuid_to_id:
            event_blocks[event_id] += 1
            block_id = LabsEventBlock.objects.update_or_create(
                uuid=item[1],
                defaults={
                    'title': item[2],
                    'description': item[3] or '',
                    'block_type': item[4] or '',
                    'order': event_blocks[event_id],
                    'deleted': False,
                    'event_id': event_id,
                }
            )[0].id
            blocks.append(block_id)
        else:
            block_id = block_uuid_to_id[item[1]]
        try:
            meta = json.loads(item[12])
        except (ValueError, TypeError):
            meta = None
        block_results[block_id] += 1
        result, new = LabsEventResult.objects.update_or_create(
            uuid=item[6],
            defaults={
                'title': item[7],
                'result_format': item[8] or '',
                'fix': item[9] or '',
                'check': item[10] or '',
                'order': block_results[block_id],
                'meta': meta,
                'block_id': block_id,
            }
        )
        results.append(result.id)
        if meta and isinstance(meta, list):
            create_circle_items_for_result(
                result.id,
                list(CircleItem.objects.filter(result_id=result.id).values_list('id', flat=True)) if not new else [],
                meta,
                metamodels,
                competences
            )
    LabsEventBlock.objects.filter(event_id__in=events).exclude(id__in=blocks).update(deleted=True)
    LabsEventResult.objects.filter(block_id__in=blocks).exclude(id__in=results).update(deleted=True)
