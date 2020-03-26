from collections import Counter

from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from isle.models import EventMaterial, EventTeamMaterial, EventOnlyMaterial, User, Event, EventEntry


@method_decorator(login_required, name='dispatch')
class Statistics(TemplateView):
    template_name = 'stat.html'

    def get_context_data(self):
        if not self.request.user.is_assistant:
            return {}
        event_materials = EventMaterial.objects.count()
        event_team_materials = EventTeamMaterial.objects.count()
        event_only_materials = EventOnlyMaterial.objects.count()
        total_elements = event_materials + event_team_materials + event_only_materials

        category_event_materials = Counter(EventMaterial.objects.values_list('event__event_type__title', flat=True))
        category_event_team_materials = Counter(EventTeamMaterial.objects.values_list('event__event_type__title', flat=True))
        category_event_only_materials = Counter(EventOnlyMaterial.objects.values_list('event__event_type__title', flat=True))

        private_elements = EventMaterial.objects.filter(is_public=False).count()
        public_elements = total_elements - private_elements

        fixics = list(User.objects.filter(is_assistant=True).exclude(unti_id__isnull=True).values_list('unti_id', flat=True))

        student_event_materials = (EventMaterial.objects.exclude(initiator__in=fixics) & EventMaterial.objects.filter(initiator__isnull=False)).values_list('initiator', flat=True)
        student_loaders_event_materials = set(student_event_materials)
        student_event_materials_count = len(student_event_materials)

        student_event_team_materials = (EventTeamMaterial.objects.exclude(initiator__in=fixics) & EventTeamMaterial.objects.filter(initiator__isnull=False)).values_list('initiator', flat=True)
        student_loaders_event_team_materials = set(student_event_team_materials)
        student_event_team_materials_count = len(student_event_team_materials)

        student_event_only_materials = (EventOnlyMaterial.objects.exclude(initiator__in=fixics) & EventOnlyMaterial.objects.filter(initiator__isnull=False)).values_list('initiator', flat=True)
        student_loaders_event_only_materials = set(student_event_only_materials)
        student_event_only_materials_count = len(student_event_only_materials)

        student_loaders = len(set(student_loaders_event_materials | student_loaders_event_team_materials | student_loaders_event_only_materials))

        fixics_event_materials = (EventMaterial.objects.filter(initiator__in=fixics) | EventMaterial.objects.filter(initiator__isnull=True)).values_list('initiator', flat=True)
        fixics_loaders_event_materials = set(fixics_event_materials)
        fixics_event_materials_count = len(fixics_event_materials)

        fixics_event_team_materials = (EventTeamMaterial.objects.filter(initiator__in=fixics) | EventTeamMaterial.objects.filter(initiator__isnull=True)).values_list('initiator', flat=True)
        fixics_loaders_event_team_materials = set(fixics_event_team_materials)
        fixics_event_team_materials_count = len(fixics_event_team_materials)

        fixics_event_only_materials = (EventOnlyMaterial.objects.filter(initiator__in=fixics) | EventOnlyMaterial.objects.filter(initiator__isnull=True)).values_list('initiator', flat=True)
        fixics_loaders_event_only_materials = set(fixics_event_only_materials)
        fixics_event_only_materials_count = len(fixics_event_only_materials)

        fixics_loaders = len(set(fixics_loaders_event_materials | fixics_loaders_event_team_materials | fixics_loaders_event_only_materials))

        evs = Event.objects.filter(id__in=set(EventEntry.objects.all().values_list('event', flat=True)), event_type__ext_id__in=[1,2,5,6])
        iterator = (e for e in evs if e.trace_count==0 and EventEntry.objects.filter(is_active=True, event=e).count() > 0)
        without_trace = sum(1 for _ in iterator)

        data = {
            'total_elements': total_elements,
            'event_materials': event_materials,
            'event_team_materials': event_team_materials,
            'event_only_materials': event_only_materials,

            'student_event_materials_count': student_event_materials_count,
            'student_event_team_materials_count': student_event_team_materials_count,
            'student_event_only_materials_count': student_event_only_materials_count,
            'student_loaders': student_loaders,

            'fixics_event_materials_count': fixics_event_materials_count,
            'fixics_event_team_materials_count': fixics_event_team_materials_count,
            'fixics_event_only_materials_count': fixics_event_only_materials_count,
            'fixics_loaders': fixics_loaders,

            'private_elements': private_elements,
            'public_elements': public_elements,

            'category_event_materials': dict(category_event_materials),
            'category_event_team_materials': dict(category_event_team_materials),
            'category_event_only_materials': dict(category_event_only_materials),
            'without_trace': without_trace,

        }
        return data
