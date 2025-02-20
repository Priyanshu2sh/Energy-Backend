from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    path('day-ahead', views.DayAheadAPI.as_view(), name='day_ahead'),
]