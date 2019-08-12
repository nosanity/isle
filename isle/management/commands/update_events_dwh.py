from django.conf import settings
from django.core.management.base import BaseCommand
from isle.dwh_tools.dp import update_metamodels, update_competences
from isle.dwh_tools.labs import update_events, update_contexts, update_event_contexts, update_event_types, \
    update_event_type_connections, update_authors, update_event_authors, update_event_structure
from isle.dwh_tools.pt import update_pt_teams
from isle.dwh_tools.xle import update_event_entries, update_run_enrollments


class Command(BaseCommand):
    def handle(self, *args, **options):
        update_metamodels()
        update_competences()

        update_events()
        update_contexts()
        update_event_contexts()
        update_event_types()
        update_event_type_connections()
        update_authors()
        update_event_authors()
        update_event_structure()

        update_event_entries()
        update_run_enrollments()

        if settings.ENABLE_PT_TEAMS:
            update_pt_teams()
