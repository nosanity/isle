import json
import os
from unittest.mock import patch
from django.conf import settings
from django.test import TestCase
from isle.api import LabsApi
from isle.models import Activity, Event, EventType
from isle.utils import refresh_events_data


class TestAPI(TestCase):
    def test_initial_events_load(self):
        """
        тест первичной загрузки всех эвентов и активностей
        """
        with patch.object(LabsApi, 'get_activities', return_value=self.load_test_data('api_data.json')):
            self.assertTrue(refresh_events_data())
            self.assertEqual(Event.objects.count(), 3)
            self.assertEqual(Activity.objects.count(), 2)
            self.assertEqual(Activity.objects.filter(is_deleted=True).count(), 1)
            self.assertEqual(Activity.objects.filter(main_author='').count(), 1)
            self.assertEqual(EventType.objects.count(), 1)

    def test_events_load_with_changed_data(self):
        """
        тест обновления эвентов и активностей при условии, что внешние id и некоторые другие данные изменились
        """
        with patch.object(LabsApi, 'get_activities', return_value=self.load_test_data('api_data.json')):
            self.assertTrue(refresh_events_data())
        old_data = {
            'title': "Спортивные активности",
        }
        new_data = {
            'title': "Спортивные активности changed",
        }
        self.assertDictEqual(
            old_data,
            self._get_obj_dict(Activity.objects.get(uid='12d2ee3f-3dcf-42f6-979a-47be9b7e0b01'), 'title')
        )
        self.assertDictEqual(
            old_data,
            self._get_obj_dict(Event.objects.get(uid='cd602dd7-4fef-440b-82bf-013b5817e3dd'), 'title')
        )
        with patch.object(LabsApi, 'get_activities', return_value=self.load_test_data('changed_api_data.json')):
            self.assertTrue(refresh_events_data())
            self.assertEqual(Event.objects.count(), 4)
            self.assertEqual(Activity.objects.count(), 2)
            self.assertEqual(EventType.objects.count(), 1)

            self.assertDictEqual(
                new_data,
                self._get_obj_dict(Activity.objects.get(uid='12d2ee3f-3dcf-42f6-979a-47be9b7e0b01'), 'title')
            )
            self.assertDictEqual(
                new_data,
                self._get_obj_dict(Event.objects.get(uid='cd602dd7-4fef-440b-82bf-013b5817e3dd'), 'title')
            )

    def _get_obj_dict(self, obj, *attrs):
        return {attr: getattr(obj, attr) for attr in attrs}

    def load_test_data(self, file_name):
        with open(os.path.join(settings.BASE_DIR, 'isle/tests/data', file_name)) as f:
            return json.load(f)
