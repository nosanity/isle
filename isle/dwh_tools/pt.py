from isle.models import UpdateTimes, Context, User, Team
from isle.utils import pull_sso_user
from .utils import get_dwh_connect, change_update_time


@change_update_time(UpdateTimes.PT_TEAMS)
def update_pt_teams(dt=None):
    db = get_dwh_connect('pt')
    cur = db.cursor()
    query = "select T.uuid, T.title, C.uuid, UI.untiID from team_user TU " \
            "left outer join context_team CT on TU.teamID=CT.teamID " \
            "inner join team T on TU.teamID=T.id " \
            "inner join user U on TU.userID=U.id " \
            "inner join user_info UI on UI.userID=U.id " \
            "inner join context C on C.id=CT.contextID"
    if dt:
        query = "{query} where T.createDT >= '{dt}' or T.dt >= '{dt}'".format(query=query, dt=dt)
    query = "{query} order by TU.teamID".format(query=query)
    cur.execute(query)
    data = cur.fetchall()
    context_uuid_to_id = dict(Context.objects.values_list('uuid', 'id'))
    unti_id_to_id = dict(User.objects.filter(unti_id__isnull=False).values_list('unti_id', 'id'))
    failed_unti_ids = set()
    current_users = []
    current_contexts = []
    current_team = None
    for team_uuid, team_title, context_uuid, unti_id in data:
        if current_team is not None and current_team.uuid != team_uuid:
            current_team.users.set(current_users)
            current_team.contexts.set(current_contexts)
            current_team, current_users, current_contexts = None, [], []
        if current_team is None:
            current_team = Team.objects.update_or_create(uuid=team_uuid, defaults={
                'name': team_title,
                'system': Team.SYSTEM_PT,
            })[0]
        context_id = context_uuid_to_id.get(context_uuid)
        if context_id and context_id not in current_contexts:
            current_contexts.append(context_id)
        user_id = unti_id_to_id.get(unti_id)
        if not user_id and unti_id not in failed_unti_ids:
            user = pull_sso_user(unti_id)
            if user:
                user_id = user.id
                unti_id_to_id[unti_id] = user_id
        if user_id and user_id not in current_users:
            current_users.append(user_id)
    if current_team:
        current_team.users.set(current_users)
        current_team.contexts.set(current_contexts)
