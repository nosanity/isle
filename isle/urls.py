from django.urls import path
from isle import views


urlpatterns = [
    path('', views.Index.as_view(), name='index'),
    path('logout/', views.logout, name='logout'),
    path('refresh/', views.RefreshDataView.as_view(), name='refresh-view'),
    path('refresh/<str:uid>', views.RefreshDataView.as_view(), name='refresh-event-view'),
    path('<str:uid>/', views.EventView.as_view(), name='event-view'),
    path('<str:uid>/<int:unti_id>/', views.LoadMaterials.as_view(), name='load-materials'),
]
