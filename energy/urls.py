from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path('generation-portfolio', views.GenerationPortfolioAPI.as_view(), name='generation_portfolio'),
    path('generation-portfolio/<int:pk>', views.GenerationPortfolioAPI.as_view(), name='update_generation_portfolio'),
    path('consumer-requirements', views.ConsumerRequirementsAPI.as_view(), name='consumer_requirements'),
    path('consumer-requirements/<int:pk>', views.ConsumerRequirementsAPI.as_view(), name='consumer_requirements'),
    path('monthly-consumption', views.MonthlyConsumptionDataAPI.as_view(), name='monthly_consumption'),
    path('monthly-consumption/<int:pk>', views.MonthlyConsumptionDataAPI.as_view(), name='monthly_consumption'),
    path('matching-ipp/<int:pk>', views.MatchingIPPAPI.as_view(), name='matching_ipp'),
    path('matching-consumer/<int:pk>', views.MatchingConsumerAPI.as_view(), name='matching_consumer'),
    path('portfolio_update_status/<int:user_id>',views.PortfolioUpdateStatusView.as_view(),name='portfolio_update_status'),
    path('optimize-capactiy', views.OptimizeCapacityAPI.as_view(), name='optimize_capactiy'),
    path('consumption-pattern/<int:pk>', views.ConsumptionPatternAPI.as_view(), name='consumption_pattern'),
    path('terms-sheet', views.StandardTermsSheetAPI.as_view(), name='terms-sheet-list'),
    path('terms-sheet/<int:pk>', views.StandardTermsSheetAPI.as_view(), name='terms-sheet-detail'),
    path('subscription-plans/<str:user_type>', views.SubscriptionTypeAPIView.as_view(), name='subscription_plans'),
    path('subscriptions', views.SubscriptionEnrolledAPIView.as_view(), name='subscriptions'),
    path('subscriptions/<int:pk>', views.SubscriptionEnrolledAPIView.as_view(), name='subscriptions'),
    path('notifications/<int:user_id>', views.NotificationsAPI.as_view(), name='notifications'),
    path('negotiate-tariff-view/<int:terms_sheet_id>', views.NegotiateTariffView.as_view(), name='negotiate_tariff_view'),
    path('negotiate-tariff-view', views.NegotiateTariffView.as_view(), name='negotiate_tariff_view'),
    path('negotiate-window/<int:user_id>', views.NegotiationWindowStatusView.as_view(), name='negotiate_window'),
]
