import os
import random
import tarfile
import time
from django.conf import settings
from django.test import TestCase, RequestFactory
from django.urls import reverse
from isle.models import (Event, User, Team, EventMaterial, EventTeamMaterial, EventOnlyMaterial, EventEntry,
                         LabsTeamResult, LabsUserResult, LabsEventResult)
from isle.views import EventCsvData


class TestGenerationTime(TestCase):
    fixtures = [os.path.join(settings.BASE_DIR, 'isle/tests/fixtures/test_events.json')]

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(cls.fixtures[0]):
            tar = tarfile.open(os.path.join(settings.BASE_DIR, 'isle/tests/fixtures/test_events.json.tar.bz2'), 'r:bz2')
            tar.extract('test_events.json', os.path.join(settings.BASE_DIR, 'isle/tests/fixtures/'))
        super().setUpClass()

    def setUp(self):
        self.filled = int(os.getenv('TEST_CSV_GENERATION_FILLED_EVENTS', 1))

    def generate(self, n, filled):
        users = []
        for i in range(n * 1000):
            users.append(User(
                username='user_{}'.format(i),
                email='user_{}@example.com'.format(i),
                first_name='firstname',
                last_name='lastname',
                second_name='secondname',
                unti_id=i + 1,
                leader_id=i + 1,
            ))
        self._bulk_create(users, User)
        self.assistant = User.objects.create_user('assistant', 'assistant@example.com', 'password', is_assistant=True)

        fill_events = Event.objects.filter(blocks__isnull=False, event_type__isnull=False)[:filled]
        personal_materials, team_materials, event_materials = [], [], []
        self.filled_event_uid = None
        for event in fill_events:
            if self.filled_event_uid is None:
                self.filled_event_uid = event.uid
            users = list(User.objects.order_by('?')[:n])
            traces = list(event.get_traces())
            tmp = []
            event_results = list(LabsEventResult.objects.filter(block__event=event))
            for user in users:
                tmp.append(EventEntry(user=user, event=event))

                for _ in range(10):
                    result = LabsUserResult.objects.create(
                        user=user,
                        result=random.choice(event_results),
                        comment='comment'
                    )
                    personal_materials.append(EventMaterial(
                        user_id=user.id,
                        is_public=True,
                        result_v2_id=result.id,
                        event_id=event.id,
                        url='http://example.com/some_file.csv',
                        initiator=user.unti_id,
                    ))

            self._bulk_create(tmp, EventEntry)
            team_members = [random.sample(users, random.randint(1, len(users))),
                            random.sample(users, random.randint(1, len(users)))]
            teams = []
            for team_n, members in enumerate(team_members, 1):
                t = Team.objects.create(
                    name='team_{}'.format(team_n),
                    event=event,
                    creator=members[0],
                )
                t.users.set(members)
                teams.append(t)
                for _ in range(10):
                    result = LabsTeamResult.objects.create(
                        team=t,
                        result=random.choice(event_results),
                        comment='comment'
                    )
                    team_materials.append(EventTeamMaterial(
                        team_id=t.id,
                        result_v2_id=result.id,
                        event_id=event.id,
                        url='http://example.com/some_file.csv',
                        initiator=members[0].unti_id
                    ))

            for _ in range(2 * n):
                event_materials.append(EventOnlyMaterial(
                    comment='comment',
                    event_id=event.id,
                    url='http://example.com/some_file.csv',
                    trace_id=random.choice(traces).id,
                    initiator=users[0].unti_id,
                ))
        self._bulk_create(personal_materials, EventMaterial)
        self._bulk_create(team_materials, EventTeamMaterial)
        self._bulk_create(event_materials, EventOnlyMaterial)

    def _bulk_create(self, lst, model):
        bulk_size = 100
        for i in range(0, len(lst), bulk_size):
            model.objects.bulk_create(lst[i:(i+bulk_size)])

    def generate_and_check_time(self, n, filled):
        self.generate(n, filled)
        request = RequestFactory().get(reverse('get_event_csv', kwargs={'uid': self.filled_event_uid}))
        request.user = self.assistant
        t = time.time()
        EventCsvData.as_view()(request, uid=self.filled_event_uid)
        print('N = {}, filled events {}, time {}'.format(n, filled, round(time.time() - t, 3)))

    def test_1_users(self):
        self.generate_and_check_time(1, self.filled)

    def test_2_users(self):
        self.generate_and_check_time(2, self.filled)

    def test_5_users(self):
        self.generate_and_check_time(5, self.filled)

    def test_10_users(self):
        self.generate_and_check_time(10, self.filled)

    def test_20_users(self):
        self.generate_and_check_time(20, self.filled)

    def test_50_users(self):
        self.generate_and_check_time(50, self.filled)

    def test_100_users(self):
        self.generate_and_check_time(100, self.filled)
