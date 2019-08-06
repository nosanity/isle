from django.conf import settings
from django.conf.urls import url
from django.urls import path, include
from drf_swagger_docs.views import get_schema_view
from rest_framework.documentation import include_docs_urls
from isle import views

urlpatterns = [
    path('carrier-django/', include('django_carrier_client.urls')),
    path('api/docs/', include_docs_urls()),
    url(r'^api/swagger(?P<format>\.json)$', get_schema_view().without_ui(cache_timeout=0)),
    path('', views.ActivitiesView.as_view(), name='index'),
    path('events/', views.Events.as_view(), name='events'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('update-attendance/<str:uid>', views.UpdateAttendanceView.as_view(), name='update-attendance-view'),
    path('create-team/<str:uid>/', views.CreateTeamView.as_view(), name='create-team'),
    path('edit-team/<str:uid>/<int:team_id>/', views.EditTeamView.as_view(), name='edit-team'),
    path('load-team/<str:uid>/<int:team_id>/', views.LoadTeamMaterialsResult.as_view(), name='load-team-materials'),
    path('confirm-team-material/<str:uid>/<int:team_id>/', views.ConfirmTeamMaterial.as_view(),
         name='confirm-team-material'),
    path('load-event/<str:uid>/', views.LoadEventMaterials.as_view(), name='load-event-materials'),
    path('add-user/<str:uid>/', views.AddUserToEvent.as_view(), name='add-user'),
    path('remove-user/<str:uid>/', views.RemoveUserFromEvent.as_view(), name='remove-user'),
    path('is_public/<str:uid>/', views.IsMaterialPublic.as_view(), name='is-material-public'),
    path('autocomplete/user/', views.UserAutocomplete.as_view(), name='user-autocomplete'),
    path('autocomplete/event-user/', views.EventUserAutocomplete.as_view(), name='event-user-autocomplete'),
    path('autocomplete/event-team/', views.EventTeamAutocomplete.as_view(), name='event-team-autocomplete'),
    path('api/attendance/', views.AttendanceApi.as_view()),
    path('api/user-chart/', views.UserChartApiView.as_view()),
    path('owner/team-material/<str:uid>/<int:team_id>/<int:material_id>/', views.TeamMaterialOwnership.as_view(),
         name='team-material-owner'),
    path('owner/event-material/<str:uid>/<int:material_id>/', views.EventMaterialOwnership.as_view(),
         name='event-material-owner'),
    path('transfer-material/<str:uid>/', views.TransferView.as_view(), name='transfer'),
    path('statistics/', views.Statistics.as_view()),
    path('approve-text-edit/<str:event_entry_id>/', views.ApproveTextEdit.as_view(), name='approve-text-edit'),
    path('get_event_csv/<str:uid>/', views.EventCsvData.as_view(), name='get_event_csv'),
    path('get_events_csv', views.EventsCsvData.as_view(), name='get_filtered_events_csv'),
    path('get_activities_csv', views.ActivitiesCsvData.as_view(), name='get_activities_csv'),
    path('load_dump/<int:dump_id>/', views.LoadCsvDump.as_view(), name='load_csv_dump'),
    path('csv-dumps/', views.CSVDumpsList.as_view(), name='csv-dumps-list'),
    path('switch-context/', views.switch_context, name='switch_context'),
    path('<str:uid>/delete-team/<int:team_id>/', views.DeleteTeamView.as_view(), name='delete-team'),
    path('<str:uid>/', views.EventView.as_view(), name='event-view'),
    path('<str:uid>/<int:unti_id>/', views.LoadUserMaterialsResult.as_view(), name='load-materials'),
    path('<str:uid>/enroll/', views.EventSelfEnroll.as_view(), name='event-self-enroll'),
    path('api/user-materials/', views.UserMaterialsListView.as_view()),
    path('api/user-result-info/', views.UserResultInfoView.as_view()),
    path('api/team-result-info/', views.TeamResultInfoView.as_view()),
    path('api/all-user-results/', views.AllUserResultsView.as_view()),
    path('api/all-team-results/', views.AllTeamResultsView.as_view()),
    path('api/get-dp-data/', views.GetDpData.as_view()),
    path('api/check/', views.ApiCheckHealth.as_view()),
    path('api/upload-user-file/', views.UploadUserFile.as_view()),
    path('api/upload/create-user-result/', views.CreateUserResultAPI.as_view()),
    path('api/get-ple-user-result/<int:result_id>/', views.GetPLEUserResultApi.as_view(), name='api-ple-result'),
    path('api/check-user-trace/', views.CheckUserTraceApi.as_view()),
    path('api/event-materials/', views.EventMaterialsApi.as_view()),
    path('api/context-user-statistics/<uuid:context_uuid>/', views.ContextUserStatistics.as_view()),
    path('<str:uid>/<int:unti_id>/<str:result_type>/<int:result_id>', views.ResultPage.as_view(), name='result-page'),
]

if settings.DEBUG:
    from django.conf.urls import url
    from django.views.static import serve
    urlpatterns += [
        url(r'^media/(?P<path>.*)$', serve, {
            'document_root': settings.MEDIA_ROOT,
        })]
