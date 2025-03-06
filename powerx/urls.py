from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from .views import NextDayPredictionAPI, MonthAheadPredictionAPI, ConsumerDayAheadDemandAPI, ConsumerMonthAheadDemandAPI, NotificationsAPI, run_day_ahead_model, run_mcv_model, CleanDataAPI, DayAheadGenerationAPI, MonthAheadGenerationAPI

urlpatterns = [
    path('next-day-predictions', NextDayPredictionAPI.as_view(), name='next-day-predictions'),
    path('month-ahead-predictions', MonthAheadPredictionAPI.as_view(), name='month-ahead-predictions'),
    path('consumer-day-ahead-demand/<int:user_id>', ConsumerDayAheadDemandAPI.as_view(), name='consumer-day-ahead-demand'),
    path('consumer-day-ahead-demand', ConsumerDayAheadDemandAPI.as_view(), name='consumer-day-ahead-demand'),
    path('consumer-month-ahead-demand/<int:user_id>', ConsumerMonthAheadDemandAPI.as_view(), name='consumer-month-ahead-demand'),
    path('consumer-month-ahead-demand', ConsumerMonthAheadDemandAPI.as_view(), name='consumer-month-ahead-demand'),
    path('notifications/<int:user_id>', NotificationsAPI.as_view(), name='notifications'),
    path('run_day_ahead_model', run_day_ahead_model, name='run_day_ahead_model'),
    path('run_mcv_model', run_mcv_model, name='run_mcv_model'),
    path('clean-data', CleanDataAPI.as_view(), name='clean-data'),
    path('day-ahead-generation', DayAheadGenerationAPI.as_view(), name='day-ahead-generation'),
    path('day-ahead-generation/<int:user_id>', DayAheadGenerationAPI.as_view(), name='day-ahead-generation'),
    path('month-ahead-generation/<int:user_id>', MonthAheadGenerationAPI.as_view(), name='month-ahead-generation'),
    path('month-ahead-generation', MonthAheadGenerationAPI.as_view(), name='month-ahead-generation'),
]