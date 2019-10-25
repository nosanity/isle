from isle.models import UpdateTimes, MetaModel, DpCompetence
from .utils import get_dwh_connect, change_update_time


@change_update_time(UpdateTimes.METAMODELS)
def update_metamodels(dt=None):
    db = get_dwh_connect('dp')
    cur = db.cursor()
    query = "select uuid, guid, title from model"
    if dt:
        query = "{query} where createDt >= '{dt}' or dt >= '{dt}'".format(query=query, dt=dt)
    cur.execute(query)
    data = cur.fetchall()
    for item in data:
        MetaModel.objects.update_or_create(uuid=item[0], defaults={
            'guid': item[1],
            'title': item[2],
        })


@change_update_time(UpdateTimes.COMPETENCES)
def update_competences(dt=None):
    db = get_dwh_connect('dp')
    cur = db.cursor()
    query = "select uuid, title from competence"
    if dt:
        query = "{query} where createDt >= '{dt}' or dt >= '{dt}'".format(query=query, dt=dt)
    cur.execute(query)
    data = cur.fetchall()
    for item in data:
        DpCompetence.objects.update_or_create(uuid=item[0], defaults={
            'title': item[1],
        })
