import logging
from collections import defaultdict
from django.conf import settings
from django.core.management.base import BaseCommand
import requests
from isle.models import Activity, Event


class Command(BaseCommand):
    help = 'Создание объектов Activity по json из эвентов и подтаскивание главных лекторов из LABS'

    def add_arguments(self, parser):
        parser.add_argument('--only_authors', action='store_true', default=False)

    def handle(self, *args, **options):
        if not options.get('only_authors'):
            self.create_activities()
        self.fetch_authors()

    def create_activities(self):
        print('creating activities')
        activities = {}
        activity_events = defaultdict(list)
        for e in Event.objects.all().iterator():
            activity_data = (e.data or {}).get('activity') or {}
            if not activity_data:
                continue
            activity_uuid = activity_data.get('uuid')
            activity = activities.get(activity_uuid)
            if not activity:
                activity = Activity.objects.get_or_create(
                    uid=activity_uuid,
                    defaults=dict(
                        ile_id=activity_data.get('id'),
                        ext_id=activity_data.get('ext_id'),
                        title=activity_data.get('title') or '',
                    )
                )[0]
                activities[activity.uid] = activity
            activity_events[activity.id].append(e.id)
        print('binding events to activities')
        cnt = 0
        len_activities = len(activity_events)
        for a_id, events in activity_events.items():
            if cnt % 10 == 0:
                print('{}/{} activities'.format(cnt, len_activities))
            cnt += 1
            Event.objects.filter(id__in=events).update(activity_id=a_id)

    def fetch_authors(self):
        print('fetching authors')
        try:
            resp = requests.get('{}/api/v1/activity?app_token={}'.
                                format(settings.LABS_URL.strip('/'), settings.LABS_TOKEN))
            for a in resp.json():
                authors = a.get('authors') or []
                for author in authors:
                    if author.get('is_main'):
                        Activity.objects.filter(uid=a.get('uuid')).update(main_author=author.get('title'))
                        break
        except Exception as e:
            logging.exception('failed to fetch info from LABS')
