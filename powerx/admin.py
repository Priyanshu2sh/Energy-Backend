from django.contrib import admin
from .models import *
# Register your models here.
@admin.register(ConsumerTradingDemand)
class ConsumerTradingDemandAdmin(admin.ModelAdmin):
    list_display = ['consumer', 'energy_type', 'start_time', 'end_time', 'demand']