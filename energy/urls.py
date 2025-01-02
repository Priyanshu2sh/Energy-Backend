from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path('generation-portfolio', views.GenerationPortfolioAPI.as_view(), name='generation_portfolio'),
    path('generation-portfolio/<int:pk>', views.GenerationPortfolioAPI.as_view(), name='update_generation_portfolio'),
    path('consumer-requirements/<int:pk>', views.ConsumerRequirementsAPI.as_view(), name='consumer_requirements'),
    path('monthly-consumption', views.MonthlyConsumptionDataAPI.as_view(), name='monthly_consumption'),
    path('monthly-consumption/<int:pk>', views.MonthlyConsumptionDataAPI.as_view(), name='monthly_consumption'),
    path('matching-ipp', views.MatchingIPPAPI.as_view(), name='matching_ipp'),
    path('matching-consumer', views.MatchingConsumerAPI.as_view(), name='matching_consumer'),
    path('optimize-capactiy', views.OptimizeCapacityAPI.as_view(), name='optimize_capactiy'),
    path('consumption-pattern/<int:pk>', views.ConsumptionPatternAPI.as_view(), name='consumption_pattern'),
    path('terms-sheet', views.StandardTermsSheetAPI.as_view(), name='terms-sheet-list'),
    path('terms-sheet/<int:pk>', views.StandardTermsSheetAPI.as_view(), name='terms-sheet-detail'),
]
