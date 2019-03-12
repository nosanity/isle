import json
import os
from unittest.mock import patch
from urllib.parse import urlparse, parse_qsl
from uuid import uuid4
from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from django.utils.dateparse import parse_datetime
import responses
from isle.api import LabsApi, BaseApi, XLEApi
from isle.models import Activity, Event, EventType, LabsEventBlock, LabsEventResult, User, EventEntry
from isle.utils import refresh_events_data, update_event_entries


def load_test_data(file_name):
    with open(os.path.join(settings.BASE_DIR, 'isle/tests/data', file_name)) as f:
        return json.load(f)


class TestApi(BaseApi):
    name = 'test'
    base_url = 'http://example.com'
    app_token = '123456'


class TestPagination(TestCase):
    """
    Тест корректной работы пагинации
    """
    @responses.activate
    def test_pagination(self):
        def return_val(request):
            params = dict(parse_qsl(urlparse(request.url).query))
            self.assertEqual(params.get('app_token'), TestApi.app_token)
            page = params.get('page', 1)
            headers = {'X-Pagination-Page-Count': '2', 'Content-Type': 'application/json'}
            resp_body = json.dumps(load_test_data('test_pagination_page{}.json'.format(page)))
            return 200, headers, resp_body

        responses.add_callback(
            responses.GET, 'http://example.com/', callback=return_val
        )

        app = TestApi()
        num_pages = 0
        for page, data in enumerate(app.make_request('/'), 1):
            self.assertEqual(data, load_test_data('test_pagination_page{}.json'.format(page)))
            num_pages += 1
        self.assertEqual(num_pages, 2)


class TestActivityAPI(TestCase):
    def test_initial_events_load(self):
        """
        тест первичной загрузки всех эвентов и активностей
        """
        with patch.object(LabsApi, 'get_activities', return_value=iter([load_test_data('api_data.json')])):
            self.assertTrue(refresh_events_data())
            self.assertEqual(Event.objects.count(), 3)
            self.assertEqual(Event.objects.filter(is_active=True).count(), 2)
            self.assertEqual(Activity.objects.count(), 2)
            self.assertEqual(Activity.objects.filter(is_deleted=True).count(), 1)
            self.assertEqual(Activity.objects.filter(main_author='').count(), 1)
            self.assertEqual(EventType.objects.count(), 1)
            self.assertEqual(LabsEventBlock.objects.count(), 5)
            self.assertEqual(Event.objects.filter(blocks__isnull=True).count(), 0)
            self.assertEqual(LabsEventResult.objects.count(), 6)
            self.assertEqual(LabsEventBlock.objects.filter(results__isnull=True).count(), 0)

    def test_events_load_with_changed_data(self):
        """
        тест обновления эвентов и активностей
        """
        with patch.object(LabsApi, 'get_activities', return_value=iter([load_test_data('api_data.json')])):
            self.assertTrue(refresh_events_data())
        old_data = {
            'title': "НТИ Global. 9-дневная лаборатория по выводу бизнеса на азиатские рынки",
        }
        new_data = {
            'title': "НТИ Global",
        }
        self.assertDictEqual(
            old_data,
            self._get_obj_dict(Activity.objects.get(uid='fd37d2a7-2d26-4321-bcb9-2b09025d38a3'), 'title')
        )
        self.assertDictEqual(
            old_data,
            self._get_obj_dict(Event.objects.get(uid='d18093f5-dd5c-41e3-a772-0103402ddf2c'), 'title')
        )
        self.assertEqual(
            timezone.localdate(Event.objects.get(uid='d18093f5-dd5c-41e3-a772-0103402ddf2c').dt_start),
            timezone.localdate(parse_datetime('2028-07-11T02:00:00+03:00'))
        )
        self.assertEqual(
            LabsEventResult.objects.filter(
                block__event__uid='d18093f5-dd5c-41e3-a772-0103402ddf2c', deleted=False
            ).count(), 4
        )
        self.assertEqual(
            LabsEventBlock.objects.filter(
                event__uid='d18093f5-dd5c-41e3-a772-0103402ddf2c', deleted=False
            ).count(), 3
        )
        with patch.object(LabsApi, 'get_activities', return_value=iter([load_test_data('changed_api_data.json')])):
            self.assertTrue(refresh_events_data())
            self.assertEqual(Event.objects.count(), 3)
            self.assertEqual(Event.objects.filter(is_active=True).count(), 1)
            self.assertEqual(Activity.objects.count(), 2)
            self.assertEqual(EventType.objects.count(), 2)

            self.assertDictEqual(
                new_data,
                self._get_obj_dict(Activity.objects.get(uid='fd37d2a7-2d26-4321-bcb9-2b09025d38a3'), 'title')
            )
            self.assertDictEqual(
                new_data,
                self._get_obj_dict(Event.objects.get(uid='d18093f5-dd5c-41e3-a772-0103402ddf2c'), 'title')
            )
            self.assertEqual(
                timezone.localdate(Event.objects.get(uid='d18093f5-dd5c-41e3-a772-0103402ddf2c').dt_start),
                timezone.localdate(timezone.now())
            )
            self.assertEqual(
            LabsEventResult.objects.filter(
                block__event__uid='d18093f5-dd5c-41e3-a772-0103402ddf2c', deleted=False
            ).count(), 3
        )
        self.assertEqual(
            LabsEventBlock.objects.filter(
                event__uid='d18093f5-dd5c-41e3-a772-0103402ddf2c', deleted=False
            ).count(), 2
        )
        self.assertEqual(
            LabsEventResult.objects.filter(
                block__event__uid='d18093f5-dd5c-41e3-a772-0103402ddf2c'
            ).count(), 4
        )
        self.assertEqual(
            LabsEventBlock.objects.filter(
                event__uid='d18093f5-dd5c-41e3-a772-0103402ddf2c'
            ).count(), 3
        )

    def test_delete_events(self):
        with patch.object(LabsApi, 'get_activities', return_value=iter([load_test_data('api_data.json')])):
            self.assertTrue(refresh_events_data())
        self.assertTrue(Event.objects.filter(uid='d18093f5-dd5c-41e3-a772-0103402ddf2c').exists() and
                        Event.objects.get(uid='d18093f5-dd5c-41e3-a772-0103402ddf2c').is_active)
        self.assertTrue(Event.objects.filter(uid='ce8e85de-48f8-42fc-9f61-8b8eea04cc24').exists() and
                        Event.objects.get(uid='ce8e85de-48f8-42fc-9f61-8b8eea04cc24').is_active)
        with patch.object(LabsApi, 'get_activities', return_value=iter([load_test_data('api_data_delete_events.json')])):
            self.assertTrue(refresh_events_data())
        self.assertTrue(Event.objects.filter(uid='ce8e85de-48f8-42fc-9f61-8b8eea04cc24').exists() and
                        not Event.objects.get(uid='ce8e85de-48f8-42fc-9f61-8b8eea04cc24').is_active)
        self.assertFalse(Event.objects.filter(uid='d18093f5-dd5c-41e3-a772-0103402ddf2c').exists())

    def _get_obj_dict(self, obj, *attrs):
        return {attr: getattr(obj, attr) for attr in attrs}


def mock_pull_sso_user(unti_id):
    return User.objects.create(
        username='user{}'.format(unti_id),
        email='user{}@example.com'.format(unti_id),
        unti_id=unti_id
    )


class TestAttendanceAPI(TestCase):
    def setUp(self):
        a = Activity.objects.create(uid=str(uuid4()), title='title')
        self.event_uuid = 'd18093f5-dd5c-41e3-a772-0103402ddf2c'
        self.event_uuid2 = 'd18093f5-dd5c-41e3-a772-0103402ddf2d'
        Event.objects.create(activity=a, is_active=True, uid=self.event_uuid, dt_start=timezone.now(),
                             dt_end=timezone.now())
        Event.objects.create(activity=a, is_active=True, uid=self.event_uuid2, dt_start=timezone.now(),
                             dt_end=timezone.now())
        mock_pull_sso_user(1)

    def test_fetch_event_entries(self):
        with patch.object(XLEApi, 'get_attendance', return_value=iter([load_test_data('attendance.json')])):
            with patch('isle.utils.pull_sso_user', new=mock_pull_sso_user):
                self.assertTrue(update_event_entries())
                self.assertEqual(User.objects.count(), 2)
                self.assertEqual(EventEntry.objects.count(), 3)

    def test_fetch_event_entries_with_sso_fail(self):
        with patch.object(XLEApi, 'get_attendance', return_value=iter([load_test_data('attendance.json')])):
            with patch('isle.utils.pull_sso_user', new=lambda x: None):
                with self.assertLogs('', level='ERROR') as log:
                    self.assertTrue(update_event_entries())
                    self.assertEqual(User.objects.count(), 1)
                    self.assertEqual(EventEntry.objects.count(), 1)
                    self.assertEqual(len(log.output), 1)
