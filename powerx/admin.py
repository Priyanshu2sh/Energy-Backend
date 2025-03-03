from django.contrib import admin
from .models import *
# Register your models here.
@admin.register(ConsumerDayAheadDemand)
class ConsumerTradingDemandAdmin(admin.ModelAdmin):
    list_display = ['consumer', 'energy_type', 'start_time', 'end_time', 'demand']

@admin.register(CleanData)
class ConsumerTradingDemandAdmin(admin.ModelAdmin):
    list_display = ['date', 'hour', 'purchase_bid', 'total_sell_bid', 'sell_bid_solar', 'sell_bid_non_solar', 'sell_bid_hydro', 'mcv_total', 'mcv_solar', 'mcv_non_solar', 'mcv_hydro', 'mcp', 'year', 'month', 'day']

@admin.register(NextDayPrediction)
class ConsumerTradingDemandAdmin(admin.ModelAdmin):
    list_display = ['date', 'hour', 'mcv_prediction', 'mcp_prediction']