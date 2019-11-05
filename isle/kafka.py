import logging
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from carrier_client.manager import MessageManager, MessageManagerException
from carrier_client.message import OutgoingMessage
from django_carrier_client.helpers import MessageManagerHelper
from isle.api import SSOApi, ApiError, XLEApi
from isle.models import LabsUserResult, LabsTeamResult, PLEUserResult, EventEntry, User, Event
from isle.utils import update_casbin_data, update_user_token


message_manager = MessageManager(
    topics=[settings.KAFKA_TOPIC],
    host=settings.KAFKA_HOST,
    port=settings.KAFKA_PORT,
    protocol=settings.KAFKA_PROTOCOL,
    auth=settings.KAFKA_TOKEN,
)


class KafkaActions:
    CREATE = 'create'
    UPDATE = 'update'
    DELETE = 'delete'


def get_payload(obj, obj_id, action, additional_data=None):
    def for_type(payload_type):
        id_dict = {'id': obj_id}
        if additional_data:
            id_dict.update(additional_data)
        return {
            'action': action,
            'type': payload_type,
            'id': {
                payload_type: id_dict
            },
            'timestamp': datetime.isoformat(timezone.now()),
            'title': str(obj),
            'source': settings.KAFKA_TOPIC,
            'version': None,
        }
    if isinstance(obj, LabsUserResult):
        return for_type('user_result')
    if isinstance(obj, LabsTeamResult):
        return for_type('team_result')
    if isinstance(obj, PLEUserResult):
        return for_type('user_result_ple')


def send_object_info(obj, obj_id, action, additional_data=None):
    """
    отправка в кафку сообщения, составленного исходя из типа объекта obj и действия
    """
    if not getattr(settings, 'KAFKA_HOST'):
        logging.warning('KAFKA_HOST is not defined')
        return
    payload = get_payload(obj, obj_id, action, additional_data=additional_data)
    if not payload:
        logging.error("Can't get payload for %s action %s" % (obj, action))
        return
    outgoing_message = OutgoingMessage(
        topic=settings.KAFKA_TOPIC,
        payload=payload
    )
    try:
        message_manager.send_one(outgoing_message)
    except Exception:
        logging.exception('Kafka communication failed with payload %s' % payload)


def check_kafka():
    return False


class KafkaBaseListener:
    topic = ''
    actions = []
    msg_type = ''

    def handle_message(self, msg):
        if msg.get_topic() == self.topic:
            try:
                payload = msg.get_payload()
                if payload.get('type') == self.msg_type and payload.get('action') in self.actions and payload.get('id'):
                    self._handle_for_id(payload['id'], payload['action'])
            except MessageManagerException:
                logging.error('Got incorrect json from kafka: %s' % msg._value)

    def _handle_for_id(self, obj_id, action):
        raise NotImplementedError


class SSOUserChangeListener(KafkaBaseListener):
    topic = settings.KAFKA_TOPIC_SSO
    actions = (KafkaActions.CREATE, KafkaActions.UPDATE)
    msg_type = 'user'

    def _handle_for_id(self, obj_id, action):
        try:
            assert isinstance(obj_id, dict)
            user_id = obj_id.get('user', {}).get('id')
            try:
                SSOApi().push_user_to_uploads(user_id)
            except ApiError:
                pass
        except (AssertionError, AttributeError):
            logging.error('Got wrong object id from kafka: %s' % obj_id)


class XLECheckinListener(KafkaBaseListener):
    topic = settings.XLE_TOPIC
    actions = (KafkaActions.CREATE, KafkaActions.UPDATE)
    msg_type = 'checkin'

    def _handle_for_id(self, obj_id, action):
        try:
            assert isinstance(obj_id, dict)
            checkin_uuid = obj_id.get('checkin', {}).get('uuid')
            unti_id = obj_id.get('user', {}).get('unti_id')
            assert checkin_uuid and unti_id
            user = User.objects.filter(unti_id=unti_id).first()
            if not user:
                try:
                    SSOApi().push_user_to_uploads(unti_id)
                    user = User.objects.filter(unti_id=unti_id).first()
                except ApiError:
                    pass
            if not user:
                logging.error('Failed to create user for unti_id %s' % unti_id)
                return
            try:
                checkin_data = XLEApi().get_checkin(checkin_uuid)
            except ApiError:
                return
            else:
                if not (checkin_data.get('checkin') or checkin_data.get('attendance')):
                    return
                if checkin_data.get('unti_id') != user.unti_id:
                    logging.error('Inconsistent data: kafka object id %s, xle checkin api returned %s' %
                                  (obj_id, checkin_data))
                    return
                try:
                    event = Event.objects.get(uid=checkin_data.get('event_uuid'))
                except (Event.DoesNotExist, TypeError):
                    logging.error('Event with uuid "%s" not found' % checkin_data.get('event_uuid'))
                    return
                EventEntry.objects.update_or_create(user=user, event=event, defaults={'deleted': False})
        except (AssertionError, AttributeError):
            logging.error('Got wrong object id from kafka: %s' % obj_id)


class CasbinPolicyListener(KafkaBaseListener):
    topic = settings.KAFKA_TOPIC_SSO
    actions = (KafkaActions.CREATE, KafkaActions.DELETE, KafkaActions.UPDATE)
    msg_type = 'casbin_policy'

    def handle_message(self, msg):
        if msg.get_topic() == self.topic:
            try:
                payload = msg.get_payload()
                if payload.get('type') == self.msg_type and payload.get('action') in self.actions and payload.get('id'):
                    policy = payload['title']
                    update_casbin_data(update_rule=policy)
            except MessageManagerException:
                logging.error('Got incorrect json from kafka: %s' % msg._value)


class CasbinModelListener(KafkaBaseListener):
    topic = settings.KAFKA_TOPIC_SSO
    actions = (KafkaActions.CREATE, KafkaActions.UPDATE)
    msg_type = 'casbin_model'

    def _handle_for_id(self, obj_id, action):
        update_casbin_data()


class OpenapiTokenListener(KafkaBaseListener):
    topic = settings.KAFKA_TOPIC_OPENAPI
    actions = (KafkaActions.CREATE, KafkaActions.UPDATE)
    msg_type = 'token'

    def _handle_for_id(self, obj_id, action):
        try:
            token_id = obj_id.get(self.msg_type, {}).get('id')
            assert token_id, 'Failed to get token id'
            update_user_token(token_id)
        except (AssertionError, AttributeError):
            logging.error('Got wrong object id from kafka: %s' % obj_id)


MessageManagerHelper.set_manager_to_listen(SSOUserChangeListener())
MessageManagerHelper.set_manager_to_listen(XLECheckinListener())
MessageManagerHelper.set_manager_to_listen(CasbinPolicyListener())
MessageManagerHelper.set_manager_to_listen(CasbinModelListener())
MessageManagerHelper.set_manager_to_listen(OpenapiTokenListener())
