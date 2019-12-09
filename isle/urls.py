from django.conf import settings
from django.conf.urls import url
from django.contrib.auth.views import logout
from django.urls import path, include
from drf_swagger_docs.views import get_schema_view
from rest_framework.documentation import include_docs_urls

from isle.views import api_views, autocomplete, common, csv, event, statistics, team, upload

urlpatterns = [
    path('carrier-django/', include('django_carrier_client.urls')),
    path('api/docs/', include_docs_urls()),
    url(r'^api/swagger(?P<format>\.json)$', get_schema_view().without_ui(cache_timeout=0)),
    path('', event.ActivitiesView.as_view(), name='index'),
    path('events/', event.Events.as_view(), name='events'),
    path('login/', common.login, name='login'),
    path('logout/', logout, name='logout'),
    path('update-attendance/<str:uid>', event.UpdateAttendanceView.as_view(), name='update-attendance-view'),
    path('create-team/<str:uid>/', team.CreateTeamView.as_view(), name='create-team'),
    path('edit-team/<str:uid>/<int:team_id>/', team.EditTeamView.as_view(), name='edit-team'),
    path('load-team/<str:uid>/<int:team_id>/', upload.LoadTeamMaterialsResult.as_view(), name='load-team-materials'),
    path('confirm-team-material/<str:uid>/<int:team_id>/', upload.ConfirmTeamMaterial.as_view(),
         name='confirm-team-material'),
    path('load-event/<str:uid>/', upload.LoadEventMaterials.as_view(), name='load-event-materials'),
    path('add-user/<str:uid>/', event.AddUserToEvent.as_view(), name='add-user'),
    path('remove-user/<str:uid>/', event.RemoveUserFromEvent.as_view(), name='remove-user'),
    path('is_public/<str:uid>/', upload.IsMaterialPublic.as_view(), name='is-material-public'),
    path('autocomplete/user/', autocomplete.UserAutocomplete.as_view(), name='user-autocomplete'),
    path('autocomplete/event-user/', autocomplete.EventUserAutocomplete.as_view(), name='event-user-autocomplete'),
    path('autocomplete/event-team/', autocomplete.EventTeamAutocomplete.as_view(), name='event-team-autocomplete'),
    path('autocomplete/model/', autocomplete.MetaModelAutocomplete.as_view(), name='metamodel-autocomplete'),
    path('autocomplete/competence/', autocomplete.CompetenceAutocomplete.as_view(), name='competences-autocomplete'),
    path('autocomplete/tool/', autocomplete.ToolAutocomplete.as_view(), name='tools-autocomplete'),
    path('autocomplete/sublevel/', autocomplete.SublevelAutocomplete.as_view(), name='sublevel-autocomplete'),
    path('api/attendance/', api_views.AttendanceApi.as_view()),
    path('api/user-chart/', api_views.UserChartApiView.as_view()),
    path('transfer-material/<str:uid>/', upload.TransferView.as_view(), name='transfer'),
    path('statistics/', statistics.Statistics.as_view()),
    path('approve-text-edit/<str:event_entry_id>/', event.ApproveTextEdit.as_view(), name='approve-text-edit'),
    path('get_event_csv/<str:uid>/', csv.EventCsvData.as_view(), name='get_event_csv'),
    path('get_events_csv', csv.EventsCsvData.as_view(), name='get_filtered_events_csv'),
    path('get_activities_csv', csv.ActivitiesCsvData.as_view(), name='get_activities_csv'),
    path('load_dump/<int:dump_id>/', csv.LoadCsvDump.as_view(), name='load_csv_dump'),
    path('csv-dumps/', csv.CSVDumpsList.as_view(), name='csv-dumps-list'),
    path('switch-context/', event.switch_context, name='switch_context'),
    path('<str:uid>/delete-team/<int:team_id>/', team.DeleteTeamView.as_view(), name='delete-team'),
    path('<str:uid>/', event.EventView.as_view(), name='event-view'),
    path('<str:uid>/<int:unti_id>/', upload.LoadUserMaterialsResult.as_view(), name='load-materials'),
    path('<str:uid>/enroll/', event.EventSelfEnroll.as_view(), name='event-self-enroll'),
    path('api/user-materials/', api_views.UserMaterialsListView.as_view()),
    path('api/user-result-info/', api_views.UserResultInfoView.as_view()),
    path('api/team-result-info/', api_views.TeamResultInfoView.as_view()),
    path('api/all-user-results/', api_views.AllUserResultsView.as_view()),
    path('api/all-team-results/', api_views.AllTeamResultsView.as_view()),
    path('api/get-dp-data/', api_views.GetDpData.as_view()),
    path('api/check/', api_views.ApiCheckHealth.as_view()),
    path('api/upload-user-file/', api_views.UploadUserFile.as_view()),
    path('api/upload/create-user-result/', api_views.CreateUserResultAPI.as_view()),
    path('api/get-ple-user-result/<int:result_id>/', api_views.GetPLEUserResultApi.as_view(), name='api-ple-result'),
    path('api/check-user-trace/', api_views.CheckUserTraceApi.as_view()),
    path('api/event-materials/', api_views.EventMaterialsApi.as_view()),
    path('api/context-user-statistics/<uuid:context_uuid>/', api_views.ContextUserStatistics.as_view()),
    path('<str:uid>/<int:unti_id>/<str:result_type>/<int:result_id>', event.ResultPage.as_view(), name='result-page'),
    path('<str:uid>/dtrace/', upload.EventDigitalTrace.as_view(), name='event-dtrace'),
    path('autocomplete/team-and-user/', autocomplete.TeamAndUserAutocomplete.as_view(),
         name='team-and-user-autocomplete'),
    path('<str:uid>/teams/', team.EventTeams.as_view(), name='event-teams'),
    path('<str:uid>/summary/autosave/', upload.SummaryAutosave.as_view(), name='summary-autosave'),
    path('<str:uid>/summary/delete/', upload.SummaryDelete.as_view(), name='summary-delete'),
]

if settings.DEBUG:
    from django.conf.urls import url
    from django.views.static import serve
    urlpatterns += [
        url(r'^media/(?P<path>.*)$', serve, {
            'document_root': settings.MEDIA_ROOT,
        })]
