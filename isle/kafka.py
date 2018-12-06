import logging
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from carrier_client.manager import MessageManager
from carrier_client.message import OutgoingMessage
from isle.models import LabsUserResult, LabsTeamResult


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
