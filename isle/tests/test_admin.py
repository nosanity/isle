import json
from uuid import uuid4
from django.contrib.admin.sites import AdminSite
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from isle.admin import EventAdmin, EventTypeAdmin
from isle.models import Event, EventType, User, Activity, Context, Trace


class MockRequest:
    pass


class MockSuperUser:
    def has_perm(self, perm):
        return True


class OnlyChangePermissionTestMixin:
    def setUp(self):
        self.user = User.objects.create_superuser('user', 'user@example.com', 'password')
        self.client.login(username='user', password='password')

    def get_request(self):
        request = MockRequest()
        request.user = MockSuperUser()
        return request

    def test_has_no_add_permission(self):
        self.assertFalse(self.admin.has_add_permission(self.get_request()))

    def test_has_no_delete_permission(self):
        self.assertFalse(self.admin.has_delete_permission(self.get_request()))

    def test_has_change_permission(self):
        self.assertTrue(self.admin.has_change_permission(self.get_request()))


class TestEventAdmin(OnlyChangePermissionTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.admin = EventAdmin(Event, AdminSite())
        self.event_type1 = EventType.objects.create(uuid=str(uuid4()), title='title1')
        self.event_type2 = EventType.objects.create(uuid=str(uuid4()), title='title2')
        self.activity1 = Activity.objects.create(uid=str(uuid4()), title='title1')
        self.activity2 = Activity.objects.create(uid=str(uuid4()), title='title2')
        self.context1 = Context.objects.create(uuid=str(uuid4()), timezone='Europe/Moscow')
        self.context2 = Context.objects.create(uuid=str(uuid4()), timezone='Asia/Vladivostok')

    def test_changeable_fields(self):
        init_data = {
            'uid': str(uuid4()),
            'dt_start': timezone.now(),
            'dt_end': timezone.now(),
            'title': 'title',
            'is_active': True,
            'data': {'key': 'val'},
            'event_type': self.event_type1,
            'activity': self.activity1,
            'context': self.context1,
        }
        e = Event.objects.create(**init_data)
        dt = timezone.now() + timezone.timedelta(days=1)
        dt_0 = dt.strftime('%d.%m.%Y')
        dt_1 = dt.strftime('%H:%M:%S')
        new_data = {
            'uid': str(uuid4()),
            'dt_start_0': dt_0,
            'dt_start_1': dt_1,
            'dt_end_0': dt_0,
            'dt_end_1': dt_1,
            'title': 'title2',
            'is_active': False,
            'data': json.dumps({'key2': 'val2'}),
            'event_type': self.event_type2.id,
            'activity': self.activity2.id,
            'context': self.context2.id,

        }
        self.client.post(reverse('admin:isle_event_change', kwargs={'object_id': e.id}), new_data)
        self.assertEqual(Event.objects.get(id=e.id).uid, init_data['uid'])
        self.assertEqual(Event.objects.get(id=e.id).dt_start, init_data['dt_start'])
        self.assertEqual(Event.objects.get(id=e.id).dt_end, init_data['dt_end'])
        self.assertEqual(Event.objects.get(id=e.id).title, init_data['title'])
        self.assertEqual(Event.objects.get(id=e.id).is_active, False)
        self.assertEqual(Event.objects.get(id=e.id).data, init_data['data'])
        self.assertEqual(Event.objects.get(id=e.id).event_type, init_data['event_type'])
        self.assertEqual(Event.objects.get(id=e.id).activity, init_data['activity'])
        self.assertEqual(Event.objects.get(id=e.id).context, init_data['context'])


class TestEventTypeAdmin(OnlyChangePermissionTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.admin = EventTypeAdmin(EventType, AdminSite())

    def test_changeable_fields(self):
        init_data = {
            'uuid': str(uuid4()),
            'title': 'title',
            'description': 'description',
            'visible': True,
            'trace_data': None,
        }
        et = EventType.objects.create(**init_data)
        new_data = {
            'uuid': str(uuid4()),
            'title': 'title2',
            'description': 'description2',
            'visible': False,
            'trace_data': json.dumps([{"trace_type": "Презентация2", "name": "Презентация продукта2"}]),

        }
        self.client.post(reverse('admin:isle_eventtype_change', kwargs={'object_id': et.id}), new_data)
        self.assertEqual(EventType.objects.get(id=et.id).uuid, init_data['uuid'])
        self.assertEqual(EventType.objects.get(id=et.id).title, init_data['title'])
        self.assertEqual(EventType.objects.get(id=et.id).description, init_data['description'])
        self.assertEqual(EventType.objects.get(id=et.id).visible, new_data['visible'])
        self.assertEqual(EventType.objects.get(id=et.id).trace_data, json.loads(new_data['trace_data']))

    def test_delete_trace(self):
        et_uuid = str(uuid4())
        init_data = {
            'uuid': et_uuid,
            'title': 'title',
            'description': 'description',
            'visible': True,
            'trace_data': '',
        }
        et = EventType.objects.create(**init_data)
        new_data = init_data
        new_data['trace_data'] = json.dumps([
            {"trace_type": "Презентация1", "name": "Презентация продукта1"},
            {"trace_type": "Презентация2", "name": "Презентация продукта2"}
        ])
        self.client.post(reverse('admin:isle_eventtype_change', kwargs={'object_id': et.id}), new_data)
        self.assertEqual(Trace.objects.filter(deleted=False).count(), 2)

        new_data['trace_data'] = json.dumps([
            {"trace_type": "Презентация1", "name": "Презентация продукта1"},
        ])
        with self.assertLogs('', level='WARNING') as log:
            self.client.post(reverse('admin:isle_eventtype_change', kwargs={'object_id': et.id}), new_data)
            self.assertEqual(len(log.output), 1)
        self.assertEqual(Trace.objects.filter(deleted=False).count(), 1)
        self.assertEqual(Trace.objects.count(), 2)
