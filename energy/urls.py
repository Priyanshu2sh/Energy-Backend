from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path('energy-profiles/', views.EnergyProfilesAPI.as_view(), name='energy_profiles'),
]
