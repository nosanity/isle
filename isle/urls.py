from django.urls import path
from isle import views


urlpatterns = [
    path('', views.Index.as_view(), name='index'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('refresh/', views.RefreshDataView.as_view(), name='refresh-view'),
    path('refresh/<str:uid>', views.RefreshDataView.as_view(), name='refresh-event-view'),
    path('refresh-checkin/<str:uid>', views.RefreshCheckInView.as_view(), name='refresh-checkin-view'),
    path('update-attendance/<str:uid>', views.UpdateAttendanceView.as_view(), name='update-attendance-view'),
    path('create-team/<str:uid>/', views.CreateTeamView.as_view(), name='create-team'),
    path('load-team/<str:uid>/<int:team_id>/', views.LoadTeamMaterials.as_view(), name='load-team-materials'),
    path('load-event/<str:uid>/', views.LoadEventMaterials.as_view(), name='load-event-materials'),
    path('add-user/<str:uid>/', views.AddUserToEvent.as_view(), name='add-user'),
    path('remove-user/<str:uid>/', views.RemoveUserFromEvent.as_view(), name='remove-user'),
    path('is_public/<str:uid>/', views.IsMaterialPublic.as_view(), name='is-material-public'),
    path('autocomplete/user/', views.UserAutocomplete.as_view(), name='user-autocomplete'),
    path('api/attendance/', views.AttendanceApi.as_view()),
    path('<str:uid>/', views.EventView.as_view(), name='event-view'),
    path('<str:uid>/<int:unti_id>/', views.LoadMaterials.as_view(), name='load-materials'),
]

# from django.conf.urls import url
# from django.views.static import serve
# from django.conf import settings
# if settings.DEBUG:
#     urlpatterns += [
#         url(r'^media/(?P<path>.*)$', serve, {
#             'document_root': settings.MEDIA_ROOT,
#         })]
