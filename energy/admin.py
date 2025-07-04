from django.contrib import admin
from .models import BankingOrder, District, GeneratorHourlyDemand, GeneratorMonthlyConsumption, NationalHoliday, NegotiationInvitation, OfflinePayment, PeakHours, State, Industry, PaymentTransaction, SolarPortfolio, StateTimeSlot, SubIndustry, WindPortfolio, ESSPortfolio, ConsumerRequirements, MonthlyConsumptionData, HourlyDemand, Combination, StandardTermsSheet, MatchingIPP, SubscriptionType, SubscriptionEnrolled, Notifications, Tariffs,GeneratorOffer, NegotiationWindow, MasterTable, GridTariff, ScadaFile, RETariffMasterTable, PerformaInvoice
from django.conf import settings
import requests
from datetime import datetime
from rest_framework_simplejwt.tokens import RefreshToken
import traceback
import logging
traceback_logger = logging.getLogger('django')
logger = logging.getLogger('debug_logger')

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
admin.site.register(NegotiationInvitation)
admin.site.register(MasterTable)
admin.site.register(GridTariff)
admin.site.register(ScadaFile)
admin.site.register(PaymentTransaction)
admin.site.register(RETariffMasterTable)
admin.site.register(State)
admin.site.register(District)
admin.site.register(Industry)
admin.site.register(SubIndustry)
admin.site.register(PerformaInvoice)
admin.site.register(StateTimeSlot)
admin.site.register(GeneratorHourlyDemand)
admin.site.register(PeakHours)
admin.site.register(NationalHoliday)

@admin.register(GeneratorMonthlyConsumption)
class GeneratorMonthlyConsumptionAdmin(admin.ModelAdmin):
    list_display = ('generator', 'month', 'monthly_consumption', 'peak_consumption', 'off_peak_consumption', 'monthly_bill_amount')

@admin.register(OfflinePayment)
class OfflinePaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'invoice', 'transaction_id', 'payment_date', 'payment_mode', 'status', 'created_at')

    def save_model(self, request, obj, form, change):
        # Check if status field changed
        if 'status' in form.changed_data:
            # Status is Approved
            if obj.status == 'Approved':
                # Update linked Invoice to Paid
                if obj.invoice:
                    obj.invoice.payment_status = 'Paid'
                    obj.invoice.save()

                    # Call Subscription API to create a subscription
                    subscription_data = {
                        "user": obj.invoice.user.id,
                        "subscription": obj.invoice.subscription.id,
                        "start_date": str(datetime.today().date())
                    }
                    
                    # Generate token manually for the current Admin user
                    refresh = RefreshToken.for_user(request.user)
                    access_token = str(refresh.access_token)

                    headers = {
                        "X-Internal-Token": settings.INTERNAL_API_SECRET,
                        "Content-Type": "application/json"
                    }

                    # Select API URL
                    if settings.ENVIRONMENT == 'local':
                        url = "http://127.0.0.1:8000/api/energy/subscriptions"
                    else:
                        url = "https://ext.exgglobal.com/api/api/energy/subscriptions"

                    try:
                        response = requests.post(url, json=subscription_data, headers=headers)
                        logger.debug(response.text)
                        logger.debug(response.json())
                        if response.status_code != 201:
                            self.message_user(request, f"Subscription creation failed: {response.json()}", level='error')
                        else:
                            self.message_user(request, "Subscription created successfully.", level='success')
                    except Exception as e:
                        tb = traceback.format_exc()  # Get the full traceback
                        traceback_logger.error(f"Exception: {str(e)}\nTraceback:\n{tb}")
                        self.message_user(request, f"Subscription creation error: {str(e)}", level='error')

            # Status is Rejected
            elif obj.status == 'Rejected':
                if obj.invoice:
                    obj.invoice.payment_status = 'Failed'
                    obj.invoice.save()

        # Save OfflinePayment
        super().save_model(request, obj, form, change)

@admin.register(BankingOrder)
class DemandOrderAdmin(admin.ModelAdmin):
    list_display = ['name', 'order']