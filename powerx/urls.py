from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from .views import NextDayPredictionAPI, MonthAheadPredictionAPI, ConsumerDayAheadDemandAPI, NotificationsAPI

urlpatterns = [
    path('next-day-predictions', NextDayPredictionAPI.as_view(), name='next-day-predictions'),
    path('month-ahead-predictions', MonthAheadPredictionAPI.as_view(), name='month-ahead-predictions'),
    path('consumer-day-ahead-demand/<int:user_id>', ConsumerDayAheadDemandAPI.as_view(), name='consumer-day-ahead-demand'),
    path('consumer-day-ahead-demand', ConsumerDayAheadDemandAPI.as_view(), name='consumer-day-ahead-demand'),
    path('notifications/<int:user_id>', NotificationsAPI.as_view(), name='notifications'),
]