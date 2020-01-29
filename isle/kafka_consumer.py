from .tasks import handle_kafka_message


def handle_message(topic, message):
    handle_kafka_message.delay(topic, message)
