import shutil
import tempfile
from uuid import uuid4
from django.conf import settings
from django.core.files.storage import default_storage
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from isle.models import (
    Event, User, EventMaterial, EventEntry, LabsEventBlock, LabsEventResult, LabsUserResult, Team,
    LabsTeamResult, EventTeamMaterial, Context, UserContextRole, Tag, ContextRole
)


class BaseUpload:
    material_model = EventMaterial
    result_model = LabsUserResult
    goal_template = 'personal_results.html'
    xle_template_name = 'to_xle.html'
    lookup_keyword = 'user'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_temp_dir = tempfile.mkdtemp()
        settings.MEDIA_ROOT = cls.media_temp_dir
        settings.DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
        settings.KAFKA_HOST = ''

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.media_temp_dir, ignore_errors=True)

    def setUp(self):
        context1 = Context.objects.create(
            timezone='Europe/Moscow', uuid=str(uuid4()), title='context1', guid='context1',
        )
        context2 = Context.objects.create(
            timezone='Europe/Moscow', uuid=str(uuid4()), title='context2', guid='context2',
        )
        self.event = Event.objects.create(uid='11111111-1111-1111-11111111', title='title', is_active=True,
                                          dt_start=timezone.now(), dt_end=timezone.now(), context=context1)
        self.event_block = LabsEventBlock.objects.create(
            event=self.event, uuid=str(uuid4()), title='title', order=1
        )
        self.event_block_result = LabsEventResult.objects.create(
            block=self.event_block, uuid=str(uuid4()), title='title', order=1
        )
        self.assistant_tag = Tag.objects.create(slug=settings.CONTEXT_MANAGER_TAG)
        self.context1_assistant_role = ContextRole.objects.create(context_uuid=context1.uuid, tag=self.assistant_tag)
        self.context2_assistant_role = ContextRole.objects.create(context_uuid=context2.uuid, tag=self.assistant_tag)

        self.assistant_user = User.objects.create_user('assistant', 'assistant@exmaple.com', 'password', unti_id=3)
        UserContextRole.objects.create(user=self.assistant_user, role=self.context1_assistant_role, is_active=True)
        self.wrong_assistant_user = User.objects.create_user(
            'assistant2', 'assistant2@exmaple.com', 'password', unti_id=4
        )
        UserContextRole.objects.create(
            user=self.wrong_assistant_user, role=self.context2_assistant_role, is_active=True
        )

    def login(self, user):
        self.client.login(username=user.username, password='password')

    def test_assistant_can_see_upload_page(self):
        self.login(self.assistant_user)
        with self.assertTemplateUsed(self.goal_template):
            resp = self.client.get(self.page_url)
            self.assertEqual(resp.status_code, 200)

    def test_user_can_see_upload_page(self):
        self.login(self.user)
        with self.assertTemplateUsed(self.goal_template):
            resp = self.client.get(self.page_url)
            self.assertEqual(resp.status_code, 200)

    def test_random_user_can_not_see_upload_page(self):
        self.login(self.random_user)
        with self.assertTemplateUsed(self.xle_template_name):
            resp = self.client.get(self.page_url)
            self.assertEqual(resp.status_code, 200)

    def test_anonymous_user_can_not_see_upload_page(self):
        resp = self.client.get(self.page_url)
        self.assertEqual(resp.status_code, 302)

    def test_assistant_can_upload_file(self):
        self.login(self.assistant_user)
        resp = self.client.post(self.page_url, {
            'action': 'init_result',
            'labs_result_id': str(self.event_block_result.id),
        })
        self.assertEqual(resp.status_code, 200)
        result_id = resp.json()['result_id']
        with open('isle/tests/data/attendance.json') as f:
            resp = self.client.post(self.page_url, {
                'add_btn': '',
                'labs_result_id': str(self.event_block_result.id),
                'result_item_id': result_id,
                'file_field': f
            })
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(self.material_model.objects.count(), 1)
            self.assertEqual(self.material_model.objects.first().initiator, self.assistant_user.unti_id)
            self.assertEqual(self.result_model.objects.count(), 1)
            self.assertTrue(default_storage.exists(self.material_model.objects.first().file.name))

    def test_another_context_assistant_can_not_see_upload_page(self):
        self.login(self.wrong_assistant_user)
        with self.assertTemplateUsed(self.xle_template_name):
            resp = self.client.get(self.page_url)
            self.assertEqual(resp.status_code, 200)

    def test_user_can_upload_file(self):
        self.login(self.user)
        resp = self.client.post(self.page_url, {
            'action': 'init_result',
            'labs_result_id': str(self.event_block_result.id),
        })
        self.assertEqual(resp.status_code, 200)
        result_id = resp.json()['result_id']
        with open('isle/tests/data/attendance.json') as f:
            resp = self.client.post(self.page_url, {
                'add_btn': '',
                'labs_result_id': str(self.event_block_result.id),
                'result_item_id': result_id,
                'file_field': f
            })
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(self.material_model.objects.count(), 1)
            self.assertEqual(self.material_model.objects.first().initiator, self.user.unti_id)
            self.assertEqual(self.result_model.objects.count(), 1)
            self.assertTrue(default_storage.exists(self.material_model.objects.first().file.name))

    def test_random_user_can_not_upload_file(self):
        self.login(self.random_user)
        with self.assertTemplateUsed(self.xle_template_name):
            resp = self.client.post(self.page_url, {
                'action': 'init_result',
                'labs_result_id': str(self.event_block_result.id),
            })
            self.assertEqual(resp.status_code, 200)

    def test_deleted_material_file_remains(self):
        self.login(self.user)
        resp = self.client.post(self.page_url, {
            'action': 'init_result',
            'labs_result_id': str(self.event_block_result.id),
        })
        self.assertEqual(resp.status_code, 200)
        result_id = resp.json()['result_id']
        with open('isle/tests/data/attendance.json') as f:
            resp = self.client.post(self.page_url, {
                'add_btn': '',
                'labs_result_id': str(self.event_block_result.id),
                'result_item_id': result_id,
                'file_field': f
            })
            material_id = resp.json()['material_id']
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(self.material_model.objects.count(), 1)
            file_path = self.material_model.objects.first().file.name

        with self.assertLogs('', level='WARNING') as log:
            resp = self.client.post(self.page_url, {
                'labs_result_id': str(self.event_block_result.id),
                'material_id': material_id,
                'result_item_id': result_id,
            })
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(self.material_model.objects.count(), 0)
            self.assertEqual(len(log.output), 1)
        self.assertTrue(default_storage.exists(file_path))

    def upload_file_as_user(self, user, data):
        self.login(user)
        resp = self.client.post(self.page_url, {
            'action': 'init_result',
            'labs_result_id': str(self.event_block_result.id),
        })
        self.assertEqual(resp.status_code, 200)
        result_id = resp.json()['result_id']
        data['result_item_id'] = result_id
        resp = self.client.post(self.page_url, data)
        return resp

    def _edit_comment(self, comment):
        return self.client.post(self.page_url, {
            'action': 'edit_comment',
            'labs_result_id': self.event_block_result.id,
            'result_item_id': self.result_model.objects.first().id,
            'comment': comment,
        })

    def test_result_comment_edit(self):
        comment = ''
        with open('isle/tests/data/attendance.json') as f:
            resp = self.upload_file_as_user(self.user, {
                'add_btn': '',
                'labs_result_id': str(self.event_block_result.id),
                'file_field': f,
            })
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(self.result_model.objects.first().comment, '')

        for i, user in enumerate([self.assistant_user, self.user]):
            self.login(user)
            comment = str(i)
            resp = self._edit_comment(comment)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(self.result_model.objects.first().comment, comment)

        with self.assertTemplateUsed(self.xle_template_name):
            self.login(self.random_user)
            resp = self._edit_comment('comment')
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(self.result_model.objects.first().comment, comment)

        self.client.logout()
        resp = self._edit_comment('comment')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.result_model.objects.first().comment, comment)

    def test_create_result_with_wrong_parameters(self):
        self.login(self.user)
        resp = self.client.post(self.page_url, {
            'action': 'init_result',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.result_model.objects.count(), 0)

        for labs_result_id in ('', 'str', 10):
            resp = self.client.post(self.page_url, {
                'action': 'init_result',
                'labs_result_id': labs_result_id
            })
            self.assertEqual(resp.status_code, 400)
            self.assertEqual(self.result_model.objects.count(), 0)

    def test_upload_to_deleted_result(self):
        self.login(self.user)
        LabsEventResult.objects.filter(id=self.event_block_result.id).update(deleted=True)
        resp = self.client.post(self.page_url, {
            'action': 'init_result',
            'labs_result_id': str(self.event_block_result.id),
        })
        self.assertEqual(resp.status_code, 400)

    def test_upload_to_deleted_block(self):
        self.login(self.user)
        LabsEventBlock.objects.filter(id=self.event_block.id).update(deleted=True)
        resp = self.client.post(self.page_url, {
            'action': 'init_result',
            'labs_result_id': str(self.event_block_result.id),
        })
        self.assertEqual(resp.status_code, 400)


class TestPersonalUpload(BaseUpload, TestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('user', 'user@exmaple.com', 'password', unti_id=1)
        self.random_user = User.objects.create_user('random', 'random@exmaple.com', 'password', unti_id=2)
        self.page_url = reverse('load-materials', kwargs={'uid': self.event.uid, 'unti_id': self.user.unti_id})
        EventEntry.objects.create(event=self.event, user=self.user)

    def test_assistant_can_upload_file(self):
        super().test_assistant_can_upload_file()
        self.assertTrue(self.material_model.objects.first().is_public)
        self.assertEqual(self.result_model.objects.first().user, self.user)

    def test_user_can_upload_file(self):
        super().test_user_can_upload_file()
        self.assertEqual(self.result_model.objects.first().user, self.user)


class TestTeamUpload(BaseUpload, TestCase):
    goal_template = 'team_results.html'
    result_model = LabsTeamResult
    material_model = EventTeamMaterial
    lookup_keyword = 'team'

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('user', 'user@exmaple.com', 'password', unti_id=1)
        self.random_user = User.objects.create_user('random', 'random@exmaple.com', 'password', unti_id=2)
        self.page_url = reverse('load-materials', kwargs={'uid': self.event.uid, 'unti_id': self.user.unti_id})
        self.no_team_user = User.objects.create_user('no_team', 'no_team@example.com', 'password', unti_id=4)
        EventEntry.objects.create(event=self.event, user=self.user)
        EventEntry.objects.create(event=self.event, user=self.no_team_user)
        self.team = Team.objects.create(event=self.event, name='name')
        self.team.users.add(self.user)
        self.page_url = reverse('load-team-materials', kwargs={'uid': self.event.uid, 'team_id': self.team.id})

    def test_assistant_can_upload_file(self):
        super().test_assistant_can_upload_file()
        self.assertEqual(self.result_model.objects.first().team, self.team)

    def test_user_can_upload_file(self):
        super().test_user_can_upload_file()
        self.assertEqual(self.result_model.objects.first().team, self.team)

    def test_no_team_user_can_see_upload_page(self):
        self.login(self.no_team_user)
        with self.assertTemplateUsed(self.goal_template):
            resp = self.client.get(self.page_url)
            self.assertEqual(resp.status_code, 200)

    def test_result_comment_edit(self):
        super().test_result_comment_edit()
        self.login(self.no_team_user)
        comment = 'comment'
        resp = self._edit_comment(comment)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.result_model.objects.first().comment, comment)

    def test_no_team_user_can_not_upload_file(self):
        self.login(self.no_team_user)
        resp = self.client.post(self.page_url, {
            'action': 'init_result',
            'labs_result_id': str(self.event_block_result.id),
        })
        self.assertEqual(resp.status_code, 403)
