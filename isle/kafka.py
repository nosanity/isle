import logging
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from carrier_client.manager import MessageManager, MessageManagerException
from carrier_client.message import OutgoingMessage
from django_carrier_client.helpers import MessageManagerHelper
from isle.api import SSOApi, ApiError
from isle.models import LabsUserResult, LabsTeamResult
from isle.utils import update_context_manager


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


def get_payload(obj, obj_id, action):
    def for_type(payload_type):
        return {
            'action': action,
            'type': payload_type,
            'id': {
                payload_type: {'id': obj_id}
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


def send_object_info(obj, obj_id, action):
    """
    отправка в кафку сообщения, составленного исходя из типа объекта obj и действия
    """
    if not getattr(settings, 'KAFKA_HOST'):
        logging.warning('KAFKA_HOST is not defined')
        return
    payload = get_payload(obj, obj_id, action)
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
    actions = (KafkaActions.CREATE, KafkaActions.UPDATE, KafkaActions.DELETE)
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


class PLEContextUserChanged(KafkaBaseListener):
    topic = settings.KAFKA_TOPIC_PLE
    msg_type = 'context_user'

    def _handle_for_id(self, obj_id, action):
        try:
            assert isinstance(obj_id, dict)
            unti_id = obj_id.get('user')
            context_uuid = obj_id.get('context')
            assert unti_id and context_uuid
            update_context_manager(context_uuid, unti_id)
        except (AssertionError, AttributeError):
            logging.error('Got wrong object id from kafka: %s' % obj_id)


MessageManagerHelper.set_manager_to_listen(SSOUserChangeListener())
MessageManagerHelper.set_manager_to_listen(PLEContextUserChanged())
