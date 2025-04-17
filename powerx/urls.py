from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from .views import NextDayPredictionAPI, MonthAheadPredictionAPI, ConsumerDayAheadDemandAPI, ConsumerMonthAheadDemandAPI, NotificationsAPI, TrackDemandStatusAPI, TrackGenerationStatusAPI, run_day_ahead_model, run_month_ahead_model_mcv_mcp, CleanDataAPI, DayAheadGenerationAPI, MonthAheadGenerationAPI, ConsumerDashboardAPI, GeneratorDashboardAPI, ModelStatisticsAPI, ModelStatisticsMonthAPI

urlpatterns = [
    path('next-day-predictions', NextDayPredictionAPI.as_view(), name='next-day-predictions'),
    path('month-ahead-predictions', MonthAheadPredictionAPI.as_view(), name='month-ahead-predictions'),
    path('consumer-day-ahead-demand/<int:user_id>', ConsumerDayAheadDemandAPI.as_view(), name='consumer-day-ahead-demand'),
    path('consumer-day-ahead-demand', ConsumerDayAheadDemandAPI.as_view(), name='consumer-day-ahead-demand'),
    path('consumer-month-ahead-demand/<int:user_id>', ConsumerMonthAheadDemandAPI.as_view(), name='consumer-month-ahead-demand'),
    path('consumer-month-ahead-demand', ConsumerMonthAheadDemandAPI.as_view(), name='consumer-month-ahead-demand'),
    path('notifications/<int:user_id>', NotificationsAPI.as_view(), name='notifications'),
    path('run_day_ahead_model', run_day_ahead_model, name='run_day_ahead_model'),
    path('run_mcv_model', run_month_ahead_model_mcv_mcp, name='run_mcv_model'),
    path('clean-data', CleanDataAPI.as_view(), name='clean-data'),
    path('day-ahead-generation', DayAheadGenerationAPI.as_view(), name='day-ahead-generation'),
    path('day-ahead-generation/<int:user_id>', DayAheadGenerationAPI.as_view(), name='day-ahead-generation'),
    path('month-ahead-generation/<int:user_id>', MonthAheadGenerationAPI.as_view(), name='month-ahead-generation'),
    path('month-ahead-generation', MonthAheadGenerationAPI.as_view(), name='month-ahead-generation'),
    path('consumer-dashboard/<int:user_id>', ConsumerDashboardAPI.as_view(), name='consumer-dashboard'),
    path('generator-dashboard/<int:user_id>', GeneratorDashboardAPI.as_view(), name='generator-dashboard'),
    path('model-statistics', ModelStatisticsAPI.as_view(), name='model-statistics'),
    path('model-statistics-month', ModelStatisticsMonthAPI.as_view(), name='model-statistics-month'),
    path('track-demand-status/<int:user_id>', TrackDemandStatusAPI.as_view(), name='track-demand-status'),
    path('track-generation-status/<int:user_id>', TrackGenerationStatusAPI.as_view(), name='track-generation-status'),
]