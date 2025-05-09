from django.contrib import admin
from .models import *
# Register your models here.
@admin.register(ConsumerDayAheadDemand)
class ConsumerDayAheadDemandAdmin(admin.ModelAdmin):
    list_display = ['requirement', 'date', 'demand', 'price_details']

@admin.register(ConsumerMonthAheadDemand)
class ConsumerMonthAheadDemandAdmin(admin.ModelAdmin):
    list_display = ['requirement', 'date', 'demand', 'price_details']

@admin.register(ConsumerMonthAheadDemandDistribution)
class ConsumerMonthAheadDemandDistributionAdmin(admin.ModelAdmin):
    list_display = ['month_ahead_demand', 'start_time', 'end_time', 'distributed_demand']

@admin.register(CleanData)
class CleanDataAdmin(admin.ModelAdmin):
    list_display = ['date', 'hour', 'purchase_bid', 'total_sell_bid', 'sell_bid_solar', 'sell_bid_non_solar', 'sell_bid_hydro', 'mcv_total', 'mcv_solar', 'mcv_non_solar', 'mcv_hydro', 'mcp', 'year', 'month', 'day']

@admin.register(NextDayPrediction)
class NextDayPredictionAdmin(admin.ModelAdmin):
    list_display = ['date', 'hour', 'mcv_prediction', 'mcp_prediction']

@admin.register(MonthAheadPrediction)
class MonthAheadPredictionAdmin(admin.ModelAdmin):
    list_display = ['date', 'hour', 'mcv_prediction', 'mcp_prediction']

admin.site.register(Notifications)
admin.site.register(MonthAheadGeneration)
admin.site.register(MonthAheadGenerationDistribution)
admin.site.register(ExecutedDayDemandTrade)
admin.site.register(ExecutedDayGenerationTrade)
admin.site.register(ConsumerDayAheadDemandDistribution)
admin.site.register(DayAheadGeneration)
admin.site.register(DayAheadGenerationDistribution)


@admin.register(UploadedTradeFile)
class UploadedTradeFileAdmin(admin.ModelAdmin):
    list_display = ['trade_type', 'uploaded_at']