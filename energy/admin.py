from django.contrib import admin
from .models import SolarPortfolio, WindPortfolio, ESSPortfolio, ConsumerRequirements, MonthlyConsumptionData, HourlyDemand, Combination, StandardTermsSheet, MatchingIPP, SubscriptionType, SubscriptionEnrolled, Notifications, Tariffs,GeneratorOffer, NegotiationWindow, MasterTable, GridTariff, ScadaFile

# Register your models here.
admin.site.register(SolarPortfolio)
admin.site.register(WindPortfolio)
admin.site.register(ESSPortfolio)
admin.site.register(ConsumerRequirements)
admin.site.register(MonthlyConsumptionData)
admin.site.register(HourlyDemand)
admin.site.register(Combination)
admin.site.register(StandardTermsSheet)
admin.site.register(MatchingIPP)
admin.site.register(SubscriptionType)
admin.site.register(SubscriptionEnrolled)
admin.site.register(Notifications)
admin.site.register(Tariffs)
admin.site.register(GeneratorOffer)
admin.site.register(NegotiationWindow)
admin.site.register(MasterTable)
admin.site.register(GridTariff)
admin.site.register(ScadaFile)