from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path('generation-portfolio/', views.GenerationPortfolioAPI.as_view(), name='generation_portfolio'),
    path('generation-portfolio/<int:pk>/', views.GenerationPortfolioAPI.as_view(), name='update_generation_portfolio'),
    path('consumer-requirements/', views.ConsumerRequirementsAPI.as_view(), name='consumer_requirements'),
    path('monthly-consumption/', views.MonthlyConsumptionDataAPI.as_view(), name='monthly_consumption'),
    path('matching-ipp/', views.MatchingIPPAPI.as_view(), name='matching_ipp'),
    path('matching-consumer/', views.MatchingConsumerAPI.as_view(), name='matching_consumer'),
]
