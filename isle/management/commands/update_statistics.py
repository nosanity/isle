import logging
from django.core.management.base import BaseCommand
from isle.models import Context
from isle.utils import calculate_context_statistics


class Command(BaseCommand):
    help = 'Пересчет статистики для контекстов'

    def add_arguments(self, parser):
        parser.add_argument('--context', required=False, type=str, action='append',
                            help='uuid контекста, можно указать несколько раз')

    def handle(self, *args, **options):
        if not options['context']:
            contexts = Context.objects.all()
        else:
            contexts = Context.objects.filter(uuid__in=options['context'])
        updated_contexts = []
        for c in contexts:
            calculate_context_statistics(c)
            updated_contexts.append(c.uuid)
        if options['context'] and set(options['context']) != set(updated_contexts):
            logging.error('Context(s) with uuid not found: %s',
                          ', '.join(set(options['context']) - set(updated_contexts)))
