from django.urls import path

from board import views

app_name = 'board'

urlpatterns = [
    path('<int:hid>/agenda', views.CalendarView.as_view(), name='board'),
    path('<int:hid>/agenda/occupancies.json', views.occupancies_json_view, name='occupancies-json'),
    path('<int:hid>/agenda/reservations.json', views.ReservationsJsonView.as_view(), name='reservations-json'),
    path('<int:hid>/reservation/new', views.ReservationCreateRequestView.as_view(), name='create-reservation'),
    path(
        '<int:hid>/reservation/new/calculate', views.ReservationCalculateView.as_view(), name='calculate-reservation'
    ),
    path('<int:hid>/reservation/new/save', views.ReservationCreateView.as_view(), name='save-reservation'),
    path('<int:hid>/reservation/close', views.RoomCloseCreateView.as_view(), name='create-close'),
    path('<int:hid>/reservation/close/update', views.RoomCloseUpdateView.as_view(), name='update-close'),
    path('<int:hid>/reservation/close/delete', views.RoomCLoseDeleteView.as_view(), name='delete-close'),
    path('<int:hid>/reservation/move', views.ReservationMoveView.as_view(), name='move-reservation'),
    path('<int:hid>/reservation/<int:pk>/details', views.ReservationDetailsView.as_view(), name='reservation'),
    path('<int:hid>/reservation/<int:pk>/accept', views.ReservationAcceptView.as_view(), name='accept-reservation'),
    path('<int:hid>/reservation/<int:pk>/cancel', views.ReservationCancelView.as_view(), name='cancel-reservation'),
    path('<int:hid>/reservation/<int:pk>/verify', views.VerifyFormView.as_view(), name='verify-changes'),
    path('<int:hid>/reservation/<int:pk>/verify/save', views.VerifyFormSaveView.as_view(), name='accept-changes'),
    path('<int:hid>/reservation/<int:pk>/<int:rid>/prices', views.UpdatePricesFormView.as_view(), name='show-prices'),
    path(
        '<int:hid>/reservation/<int:pk>/<int:rid>/prices/save',
        views.UpdatePricesFormSaveView.as_view(),
        name='save-prices',
    ),
]
