from datetime import date, timedelta
import random
from django.db import models
from django.utils.timezone import now
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from channels.layers import get_channel_layer
from django.db.models import Count
import json
import asyncio
from datetime import datetime, timedelta

from accounts.models import User
# Create your models here.

class State(models.Model):
    STATE_CHOICES = [
        ('Andhra Pradesh', 'Andhra Pradesh'),
        ("Arunachal Pradesh", "Arunachal Pradesh"),
        ("Assam", "Assam"),
        ("Bihar", "Bihar"),
        ("Chhattisgarh", "Chhattisgarh"),
        ("Goa", "Goa"),
        ("Gujarat", "Gujarat"),
        ("Haryana", "Haryana"),
        ("Himachal Pradesh", "Himachal Pradesh"),
        ("Jharkhand", "Jharkhand"),
        ("Karnataka", "Karnataka"),
        ("Kerala", "Kerala"),
        ("Madhya Pradesh", "Madhya Pradesh"),
        ("Maharashtra", "Maharashtra"),
        ("Manipur", "Manipur"),
        ("Meghalaya", "Meghalaya"),
        ("Mizoram", "Mizoram"),
        ("Nagaland", "Nagaland"),
        ("Odisha", "Odisha"),
        ("Punjab", "Punjab"),
        ("Rajasthan", "Rajasthan"),
        ("Sikkim", "Sikkim"),
        ("Tamil Nadu", "Tamil Nadu"),
        ("Telangana", "Telangana"),
        ("Tripura", "Tripura"),
        ("Uttar Pradesh", "Uttar Pradesh"),
        ("Uttarakhand", "Uttarakhand"),
        ("West Bengal", "West Bengal"),
    ]

    name = models.CharField(max_length=255, choices=STATE_CHOICES)

    def __str__(self):
        return self.name

class District(models.Model):
    name = models.CharField(max_length=255)
    state = models.ForeignKey('State', on_delete=models.CASCADE, related_name='districts')

    def __str__(self):
        return f"{self.name} ({self.state.name})"


class Industry(models.Model):
    INDUSTRY_CHOICES = [
        ("Energy", "Energy"),
        ("Materials", "Materials"),
        ("Industrials", "Industrials"),
        ("Consumer Discretionary", "Consumer Discretionary"),
        ("Consumer Staples", "Consumer Staples"),
        ("Health Care", "Health Care"),
        ("Financials", "Financials"),
        ("Information Technology", "Information Technology"),
        ("Communication Services", "Communication Services"),
        ("Utilities", "Utilities"),
        ("Real Estate", "Real Estate")
    ]

    name = models.CharField(max_length=255, choices=INDUSTRY_CHOICES)

    def __str__(self):
        return self.name
    
class SubIndustry(models.Model):
    industry = models.ForeignKey(Industry, on_delete=models.CASCADE, related_name="sub_industries")
    name = models.CharField(max_length=255)

    class Meta:
        unique_together = ("industry", "name")  # Ensures a sub-industry name is unique within an industry

    def __str__(self):
        return f"{self.name} ({self.industry.name})"

# class State(models.Model):
#     STATE_CHOICES = [
#         ('Andhra Pradesh', 'Andhra Pradesh'),
#         ("Arunachal Pradesh", "Arunachal Pradesh"),
#         ("Assam", "Assam"),
#         ("Bihar", "Bihar"),
#         ("Chhattisgarh", "Chhattisgarh"),
#         ("Goa", "Goa"),
#         ("Gujarat", "Gujarat"),
#         ("Haryana", "Haryana"),
#         ("Himachal Pradesh", "Himachal Pradesh"),
#         ("Jharkhand", "Jharkhand"),
#         ("Karnataka", "Karnataka"),
#         ("Kerala", "Kerala"),
#         ("Madhya Pradesh", "Madhya Pradesh"),
#         ("Maharashtra", "Maharashtra"),
#         ("Manipur", "Manipur"),
#         ("Meghalaya", "Meghalaya"),
#         ("Mizoram", "Mizoram"),
#         ("Nagaland", "Nagaland"),
#         ("Odisha", "Odisha"),
#         ("Punjab", "Punjab"),
#         ("Rajasthan", "Rajasthan"),
#         ("Sikkim", "Sikkim"),
#         ("Tamil Nadu", "Tamil Nadu"),
#         ("Telangana", "Telangana"),
#         ("Tripura", "Tripura"),
#         ("Uttar Pradesh", "Uttar Pradesh"),
#         ("Uttarakhand", "Uttarakhand"),
#         ("West Bengal", "West Bengal"),
#     ]

#     name = models.CharField(max_length=255, choices=STATE_CHOICES, unique=True)

#     def __str__(self):
#         return self.name


class StateTimeSlot(models.Model):
    state = models.OneToOneField(State, on_delete=models.CASCADE, related_name="time_slot")
    peak_hours = models.JSONField(default=dict)  # Stores peak hours dynamically
    off_peak_hours = models.JSONField(default=dict)  # Stores off-peak hours dynamically

    def __str__(self):
        return f"Time Slots for {self.state.name}"

    def save(self, *args, **kwargs):
        # Ensure at least 1 and at most 3 peak hour slots exist
        if not (1 <= len(self.peak_hours) <= 3):
            raise ValueError("Each state must have at least 1 and at most 3 peak hour slots.")

        super().save(*args, **kwargs)

    
# Generator models
class SolarPortfolio(models.Model):
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        limit_choices_to={'user_category': 'Generator'}
    )  # Restrict to users with user_category='Generator'
    project = models.CharField(max_length=255)
    state = models.CharField(max_length=255)  # State/Location of the energy source
    connectivity = models.CharField(max_length=255, blank=True, null=True)
    site_name = models.CharField(max_length=255, blank=True, null=True)
    total_install_capacity = models.FloatField(blank=True, null=True)
    available_capacity = models.FloatField()  # Maximum energy capacity (in kWh)
    capital_cost = models.FloatField(blank=True, null=True)
    expected_tariff = models.FloatField(blank=True, null=True)  # (INR/kWh)
    cod = models.DateField()  # COD (commercial operation date)
    updated = models.BooleanField(default=False)
    hourly_data = models.FileField(upload_to='hourly_data/', blank=True, null=True)
    annual_generation_potential = models.FloatField(blank=True, null=True)
    banking_available = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.pk:  # If the instance is being created (not updated)
            user_entries_count = SolarPortfolio.objects.filter(user=self.user).count()
            self.project = f"Solar_{user_entries_count + 1}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.project} - {self.site_name}"

class WindPortfolio(models.Model):
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        limit_choices_to={'user_category': 'Generator'}
    )  # Restrict to users with user_category='Generator'
    project = models.CharField(max_length=255)
    state = models.CharField(max_length=255)  # State/Location of the energy source
    connectivity = models.CharField(max_length=255, blank=True, null=True)
    site_name = models.CharField(max_length=255, blank=True, null=True)
    total_install_capacity = models.FloatField(blank=True, null=True)
    available_capacity = models.FloatField()  # Maximum energy capacity (in kWh)
    capital_cost = models.FloatField(blank=True, null=True)
    expected_tariff = models.FloatField(blank=True, null=True)  # (INR/kWh)
    cod = models.DateField()  # COD (commercial operation date)
    updated = models.BooleanField(default=False)
    hourly_data = models.FileField(upload_to='hourly_data/', blank=True, null=True)
    annual_generation_potential = models.FloatField(blank=True, null=True)
    banking_available = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.pk:  # If the instance is being created (not updated)
            user_entries_count = WindPortfolio.objects.filter(user=self.user).count()
            self.project = f"Wind_{user_entries_count + 1}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.project} - {self.site_name}"


class ESSPortfolio(models.Model):
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'user_category': 'Generator'}) # Restrict to users with user_category='Generator'
    project = models.CharField(max_length=255)
    state = models.CharField(max_length=255)  # State/Location of the energy source
    connectivity = models.CharField(max_length=255, blank=True, null=True)
    site_name = models.CharField(max_length=255, blank=True, null=True)
    total_install_capacity = models.FloatField(blank=True, null=True)
    available_capacity = models.FloatField()  # Maximum energy capacity (in kWh)
    capital_cost = models.FloatField(blank=True, null=True)
    expected_tariff = models.FloatField(blank=True, null=True)  # (INR/kWh)
    cod = models.DateField()  # COD (commercial operation date)
    updated = models.BooleanField(default=False)
    efficiency_of_storage = models.FloatField(blank=True, null=True)
    efficiency_of_dispatch = models.FloatField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.pk:  # If the instance is being created (not updated)
            user_entries_count = ESSPortfolio.objects.filter(user=self.user).count()
            self.project = f"ESS_{user_entries_count + 1}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.project} - {self.site_name}"
    








# Consumer models
class ConsumerRequirements(models.Model):
    # Foreign key to the User model
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'user_category': 'Consumer'}) # Restrict to users with user_category='Consumer'
    state = models.CharField(max_length=255)  # State/Location where the company is located
    industry = models.CharField(max_length=255)  # Industry your company is involved in (e.g., IT, Manufacturing)
    sub_industry = models.CharField(max_length=255)
    contracted_demand = models.FloatField()  # Total energy requirement for the consumer
    tariff_category = models.CharField(max_length=255)  # Select the tariff category applicable to your company (e.g., HT Commercial, LT Industrial).
    voltage_level = models.IntegerField()  # Select the voltage level of the electricity being supplied to your company.
    procurement_date = models.DateField()  # Select the date when the procurement of services or goods occurred (expected Date).
    consumption_unit = models.CharField(max_length=255, blank=True, null=True) #sit name
    annual_electricity_consumption = models.FloatField(blank=True, null=True)

    roof_area = models.FloatField(blank=True, null=True)  # in square meters
    solar_rooftop_capacity = models.FloatField(blank=True, null=True)  # in kWp
    location = models.CharField(max_length=255, blank=True, null=True)  # Location in district
    latitude = models.FloatField(blank=True, null=True)  # Latitude for geolocation
    longitude = models.FloatField(blank=True, null=True)  # Longitude for geolocation

    def __str__(self):
        return f"Demand for {self.user} - {self.state} - {self.industry} - {self.sub_industry} - {self.consumption_unit} - {self.contracted_demand} kWh"

class ScadaFile(models.Model):
    requirement = models.OneToOneField(ConsumerRequirements, on_delete=models.CASCADE, related_name="scada_file", unique=True)  # Ensures only one file per requirement
    file = models.FileField(upload_to="scada_files/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"SCADA File for {self.requirement}"
    
class MonthlyConsumptionData(models.Model):
    requirement = models.ForeignKey(ConsumerRequirements, on_delete=models.CASCADE)
    year = models.CharField(max_length=255, null=True, blank=True)
    month = models.CharField(max_length=255, null=True, blank=True)
    monthly_consumption = models.FloatField(null=True, blank=True)
    peak_consumption = models.FloatField(null=True, blank=True)
    off_peak_consumption = models.FloatField(null=True, blank=True)
    monthly_bill_amount = models.FloatField(null=True, blank=True)
    bill = models.FileField(upload_to='bills/', blank=True, null=True)

    def __str__(self):
        return f"Monthly Consumption for {self.requirement} - {self.year} - {self.month}"
    
class HourlyDemand(models.Model):
    requirement = models.ForeignKey(ConsumerRequirements, on_delete=models.CASCADE)
    hourly_demand = models.TextField(blank=True, null=True)  # Stores a single string of values
    csv_file = models.FileField(upload_to="csv_files/", blank=True, null=True)  # CSV File

    def __str__(self):
        return f"{self.requirement}"

    def get_hourly_data_as_list(self):
        """Convert the stored string of values into a list of floats."""
        return list(map(float, self.hourly_demand.split(',')))

    def set_hourly_data_from_list(self, data_list):
        """Convert a list of floats into a comma-separated string and save it."""
        self.hourly_demand = ','.join(map(str, data_list))

class Combination(models.Model):
    requirement = models.ForeignKey(ConsumerRequirements, on_delete=models.CASCADE, related_name='combinations')
    generator = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'user_category': 'Generator'}, related_name='generator_combinations') # Restrict to users with user_category='Generator'
    combination = models.CharField(max_length=200)
    re_replacement = models.IntegerField(blank=True, null=True)
    state = models.CharField(max_length=255, blank=True, null=True)
    optimal_solar_capacity = models.FloatField()
    optimal_wind_capacity = models.FloatField()
    optimal_battery_capacity = models.FloatField()
    per_unit_cost = models.FloatField()
    final_cost = models.FloatField()
    annual_demand_offset = models.FloatField()
    annual_demand_met = models.FloatField(blank=True, null=True)
    annual_curtailment = models.FloatField()
    request_sent = models.BooleanField(default=False)
    terms_sheet_sent = models.BooleanField(default=False)
    connectivity = models.CharField(max_length=255, blank=True, null=True)
    banking_available = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.combination}"

class StandardTermsSheet(models.Model):
    STATUS_CHOICES = [
        ('Offer Sent', 'Offer Sent'),
        ('Offer Received', 'Offer Received'),
        ('Counter Offer Sent', 'Counter Offer Sent'),
        ('Counter Offer Received', 'Counter Offer Received'),
        ('Accepted', 'Accepted'),
        ('Rejected', 'Rejected'),
        ('Withdrawn', 'Withdrawn'),
    ]

    USER_CHOICES = [
        ('Consumer', 'Consumer'),
        ('Generator', 'Generator')
    ]

    consumer = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'user_category': 'Consumer'}, related_name='consumer_terms_sheets')  # Unique related_name for consumer
    combination = models.ForeignKey(Combination, on_delete=models.CASCADE)
    term_of_ppa = models.PositiveIntegerField(help_text="Term of PPA in years")
    lock_in_period = models.PositiveIntegerField(help_text="Lock-in period in years")
    commencement_of_supply = models.DateField(help_text="Commencement date of supply")
    contracted_energy = models.FloatField(help_text="Contracted energy in million units")
    minimum_supply_obligation = models.FloatField(help_text="Minimum supply obligation in million units")
    payment_security_day = models.PositiveIntegerField(help_text="Payment security duration in days")
    payment_security_type = models.CharField(max_length=100, null=True, blank=True, help_text="Type of payment security")
    count = models.IntegerField(help_text="Used for counting iterations, only 4 iterations are valid", default=0)
    consumer_status = models.CharField(max_length=100, choices=STATUS_CHOICES, default='Offer Sent', help_text="Status from the consumer's perspective")
    generator_status = models.CharField(max_length=100, choices=STATUS_CHOICES, default='Offer Sent', help_text="Status from the generator's perspective")
    from_whom = models.CharField(max_length=200, choices=USER_CHOICES, null=True, blank=True)
    consumer_is_read = models.BooleanField(default=False)
    generator_is_read = models.BooleanField(default=False)
    equity_contribution_required_from_consumer = models.FloatField(blank=True, null=True)
    late_payment_surcharge = models.FloatField(default=1.25) # unit is %/month
    termination_compensation = models.IntegerField(default=24) # number of months

    def save(self, *args, **kwargs):
        if not self.pk:  # If the object is new
            self.count = 1  # Initialize count to 1

        previous_consumer_is_read = self.consumer_is_read
        previous_generator_is_read = self.generator_is_read

        # Fetch existing record before saving
        if self.pk:
            previous = StandardTermsSheet.objects.get(pk=self.pk)

            # If status changed and is_read is True, set it to False
            if self.consumer_status != previous.consumer_status and previous.consumer_is_read:
                self.consumer_is_read = False
            
            if self.generator_status != previous.generator_status and previous.generator_is_read:
                self.generator_is_read = False

        super().save(*args, **kwargs)

        # Determine which user should receive the WebSocket update
        if self.from_whom == "Consumer":
            if self.count % 2 == 1:  # Odd counts (1, 3) → Updated by Consumer
                user_id = self.consumer.id
            else:  # Even counts (2, 4) → Updated by Generator
                user_id = self.combination.generator.id
        else:
            if self.count % 2 == 1:  # Odd counts (1, 3) → Updated by Consumer
                user_id = self.consumer.id
            else:  # Even counts (2, 4) → Updated by Generator
                user_id = self.combination.generator.id

        # Send WebSocket update
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        unread_count = self.get_unread_terms_sheet_count(user_id)
        
        async_to_sync(channel_layer.group_send)(
            f"user_{user_id}",
            {"type": "send_terms_sheet", "unread_count": unread_count},
        )

    @staticmethod
    def get_unread_terms_sheet_count(user_id):
        user = User.objects.get(id=user_id)
        if user.user_category == 'Consumer':
            return StandardTermsSheet.objects.filter(consumer=user.id, consumer_is_read=False).count()
        else:
            return StandardTermsSheet.objects.filter(combination__generator=user.id, generator_is_read=False).count()

    def __str__(self):
        return f"{self.consumer} - {self.combination.requirement}"


# Model to store types of subscriptions
class SubscriptionType(models.Model):
    # Choices for user types
    USER_TYPE_CHOICES = [
        ('Consumer', 'Consumer'),
        ('Generator', 'Generator'),
    ]

    SUBSCRIPTION_CHOICES = [
        ('FREE', 'FREE'),
        ('LITE', 'LITE'),
        ('PRO', 'PRO'),
    ]

    user_type = models.CharField(max_length=50, choices=USER_TYPE_CHOICES, default='Consumer',)  # Specifies if the plan is for consumers or generators
    subscription_type = models.CharField(max_length=20, choices=SUBSCRIPTION_CHOICES)
    description = models.TextField(blank=True, null=True)  # Optional description of the plan
    price = models.DecimalField(max_digits=10, decimal_places=2)  # Price of the subscription
    duration_in_days = models.PositiveIntegerField()  # Duration of the plan in days

    def __str__(self):
        return f"{self.subscription_type} ({self.user_type})"

# Model to store user subscriptions
class SubscriptionEnrolled(models.Model):
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)  # User who enrolled
    subscription = models.ForeignKey(SubscriptionType, on_delete=models.CASCADE)  # Subscription type
    start_date = models.DateField()  # Subscription start date
    end_date = models.DateField()  # Subscription end date
    status = models.CharField(
        max_length=50,
        choices=[
            ('active', 'Active'),
            ('expired', 'Expired'),
        ],
        default='active',
    )

    def __str__(self):
        return f"{self.subscription.subscription_type} for {self.user} ({self.subscription.user_type})"
    
class MatchingIPP(models.Model):
    requirement = models.ForeignKey(ConsumerRequirements, on_delete=models.CASCADE)
    generator_ids = models.JSONField(default=list)

    def __str__(self):
        return f"{self.requirement} - {self.generator_ids}"
    
class Notifications(models.Model):
    # Foreign key to User model to link notification to a user
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)  # Assuming User model is in 'accounts' app
    message = models.TextField()  # The message to be sent to the user
    timestamp = models.DateTimeField(auto_now_add=True)  # Timestamp of when the notification was created
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"Notification for {self.user}"
    
class Tariffs(models.Model):
    STATUS_CHOICES=[
        ('Active','Active'),
        ('Closed','Closed'),
        ('Accepted','Accepted'),
        ('Rejected','Rejected'),
    ]

    terms_sheet = models.ForeignKey(StandardTermsSheet, on_delete=models.CASCADE)
    offer_tariff = models.FloatField(blank=True, null=True)
    window_status = models.CharField(max_length=100, choices=STATUS_CHOICES, default='Active')

    def __str__(self):
        return f"Tariff for {self.terms_sheet}"
    
class GeneratorOffer(models.Model):
    generator = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'user_category': 'Generator'})
    tariff = models.ForeignKey(Tariffs, on_delete=models.CASCADE)
    updated_tariff = models.FloatField(default=0)
    updated_at = models.DateTimeField(auto_now_add=True)
    is_accepted = models.BooleanField(default=False)
    accepted_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, limit_choices_to={'user_category': 'Consumer'}, related_name='accepted_offers')

    def __str__(self):
        return f"Offer by {self.generator.username} for Terms Sheet {self.tariff}"

class NegotiationWindow(models.Model):
    name = models.CharField(max_length=255, blank=True)
    terms_sheet = models.ForeignKey(StandardTermsSheet, on_delete=models.CASCADE)
    start_time = models.DateTimeField(default=now)
    end_time = models.DateTimeField()
    created_date = models.DateField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.name:
            # Generate a unique name with a random 3-digit number
            while True:
                random_number = random.randint(100, 999)  # Generate random 3-digit number
                potential_name = f"Transaction {random_number}"
                if not NegotiationWindow.objects.filter(name=potential_name).exists():
                    self.name = potential_name
                    break
        super().save(*args, **kwargs)

    def is_active(self):
        return self.start_time <= now() <= self.end_time

class NegotiationInvitation(models.Model):
    negotiation_window = models.ForeignKey(NegotiationWindow, on_delete=models.CASCADE, related_name='invitations')
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    invited_at = models.DateTimeField(auto_now_add=True)

class MasterTable(models.Model):
    state = models.CharField(max_length=200)
    ISTS_charges = models.FloatField()
    state_charges = models.FloatField()
    banking_charges = models.FloatField(default=8, help_text="Banking charges in percentage (default = 8% now for all states)")
    rooftop_price = models.FloatField(default=1, null=True, blank=True)
    max_capacity = models.FloatField(default=1, null=True, blank=True, help_text="Maximum capacity in MW for the state, minimum is 1 MW")

class RETariffMasterTable(models.Model):
    industry = models.CharField(max_length=255)
    re_tariff = models.FloatField()
    average_savings = models.FloatField()

class GridTariff(models.Model):
    state = models.CharField(max_length=200)    
    tariff_category = models.CharField(max_length=200)    
    cost = models.FloatField()

class PerformaInvoice(models.Model):
    STATUS = [
        ('Pending', 'Pending'),
        ('Paid', 'Paid'),
        ('Collapsed', 'Collapsed'),
        ('Failed', 'Failed'),
    ]
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    invoice_number = models.CharField(max_length=20, unique=True, blank=True, null=True, verbose_name="Invoice Number")
    company_name = models.CharField(max_length=255, verbose_name="Company Name")
    company_address = models.TextField(verbose_name="Company Address")
    gst_number = models.CharField(max_length=50, verbose_name="GST Number", blank=True, null=True)
    gst_state = models.CharField(max_length=50, verbose_name="GST State", blank=True, null=True)
    cgst = models.CharField(max_length=50, blank=True, null=True)
    sgst = models.CharField(max_length=50, blank=True, null=True)
    igst = models.CharField(max_length=50, blank=True, null=True)
    subscription = models.ForeignKey(SubscriptionType, on_delete=models.CASCADE)
    total_amount = models.IntegerField(blank=True, null=True)
    payment_status = models.CharField(max_length=50, choices=STATUS, default='Pending')
    issue_date = models.DateField(auto_now_add=True, verbose_name="Issue Date")
    due_date = models.DateField(verbose_name="Due Date", default=date.today() + timedelta(days=10))

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            today_str = date.today().strftime("%Y%m%d")
            last_invoice = PerformaInvoice.objects.filter(invoice_number__startswith=f"INV{today_str}").order_by('-invoice_number').first()
            
            if last_invoice and last_invoice.invoice_number:
                last_number = int(last_invoice.invoice_number[-3:])
                new_number = f"{last_number + 1:03d}"
            else:
                new_number = "001"

            self.invoice_number = f"INV{today_str}{new_number}"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Proforma Invoice {self.invoice_number} - {self.company_name}"

    class Meta:
        verbose_name = "Proforma Invoice"
        verbose_name_plural = "Proforma Invoices"
        ordering = ['-issue_date']

class PaymentTransaction(models.Model):
    invoice = models.ForeignKey(PerformaInvoice, on_delete=models.CASCADE)
    payment_id = models.CharField(max_length=100, verbose_name="Payment ID")
    order_id = models.CharField(max_length=100, verbose_name="Order ID")
    signature = models.CharField(max_length=100, verbose_name="signature")
    amount = models.IntegerField(verbose_name="Amount")
    datetime = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"({self.invoice.user}) -({self.order_id})" 
    
class GeneratorMonthlyConsumption(models.Model):
    generator = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'user_category': 'Generator'})
    month = models.CharField(max_length=255, null=True, blank=True)
    monthly_consumption = models.FloatField(null=True, blank=True)
    peak_consumption = models.FloatField(null=True, blank=True)
    off_peak_consumption = models.FloatField(null=True, blank=True)
    monthly_bill_amount = models.FloatField(null=True, blank=True)
    bill = models.FileField(upload_to='bills/', blank=True, null=True)

class GeneratorHourlyDemand(models.Model):
    generator = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'user_category': 'Generator'})
    hourly_demand = models.TextField(blank=True, null=True)  # Stores a single string of values

    def __str__(self):
        return f"{self.generator}"

    def get_hourly_data_as_list(self):
        """Convert the stored string of values into a list of floats."""
        return list(map(float, self.hourly_demand.split(',')))

    def set_hourly_data_from_list(self, data_list):
        """Convert a list of floats into a comma-separated string and save it."""
        self.hourly_demand = ','.join(map(str, data_list))

class GeneratorDemand(models.Model):
    generator = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'user_category': 'Generator'})
    annual_consumption = models.FloatField(null=True, blank=True)  # in MWh
    contracted_demand = models.FloatField(null=True, blank=True)  # in MW
    morning_peak_hours_start = models.TimeField(null=True, blank=True)  # in 00:00 hrs
    morning_peak_hours_end = models.TimeField(null=True, blank=True)  # in 00:00 hrs
    annual_morning_peak_hours_consumption = models.FloatField(null=True, blank=True)  # in MWh
    evening_peak_hours_start = models.TimeField(null=True, blank=True)  # in 00:00 hrs
    evening_peak_hours_end = models.TimeField(null=True, blank=True)  # in 00:00 hrs
    annual_evening_peak_hours_consumption = models.FloatField(null=True, blank=True)  # in MWh
    peak_hours_availability_requirement = models.FloatField(null=True, blank=True)  # in %

class PeakHours(models.Model):
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name="peak_hours")
    peak_start_1 = models.TimeField()  # Start time of peak hours 1
    peak_end_1 = models.TimeField()    # End time of peak hours 1
    peak_start_2 = models.TimeField(null=True, blank=True)  # Start time of peak hours 2
    peak_end_2 = models.TimeField(null=True, blank=True)    # End time of peak hours 2
    off_peak_start = models.TimeField(null=True, blank=True)  # Start time of off-peak hours
    off_peak_end = models.TimeField(null=True, blank=True)    # End time of off-peak hours

    def calculate_hours(self, start_time, end_time):
        """Calculate duration between two time fields, handling cases where end time is past midnight"""
        if not start_time or not end_time:  # Handle missing values
            return 0

        start_dt = datetime.combine(datetime.today(), start_time)
        end_dt = datetime.combine(datetime.today(), end_time)

        if end_dt < start_dt:
            end_dt += timedelta(days=1)  # Adjust for midnight crossing

        return (end_dt - start_dt).total_seconds() / 3600  # Convert seconds to hours

    def calculate_peak_hours(self):
        """Returns total peak hours"""
        peak_hours_1 = self.calculate_hours(self.peak_start_1, self.peak_end_1)
        peak_hours_2 = self.calculate_hours(self.peak_start_2, self.peak_end_2) if self.peak_start_2 and self.peak_end_2 else 0
        return peak_hours_1 + peak_hours_2

    def calculate_off_peak_hours(self):
        """Returns total off-peak hours"""
        return self.calculate_hours(self.off_peak_start, self.off_peak_end) if self.off_peak_start and self.off_peak_end else 0

    def __str__(self):
        return f"{self.state} - Peak: {self.calculate_peak_hours()} hrs, Off-Peak: {self.calculate_off_peak_hours()} hrs"

class NationalHoliday(models.Model):
    date = models.DateField(unique=True)
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} - {self.date}"
    
class CapacitySizingCombination(models.Model):
    generator = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'user_category': 'Generator'}, related_name='generator_capacity_combinations') # Restrict to users with user_category='Generator'
    record_name = models.CharField(max_length=255)
    combination = models.CharField(max_length=200)
    optimal_solar_capacity = models.FloatField()
    optimal_wind_capacity = models.FloatField()
    optimal_battery_capacity = models.FloatField()
    per_unit_cost = models.FloatField()
    oa_cost = models.FloatField()
    final_cost = models.FloatField()
    annual_demand_offset = models.FloatField()
    annual_demand_met = models.FloatField(blank=True, null=True)
    annual_curtailment = models.FloatField()
    demand = models.JSONField(blank=True, null=True)

    # new added fields
    total_cost = models.FloatField(blank=True, null=True)
    solar_allocation = models.JSONField(blank=True, null=True)
    wind_allocation = models.JSONField(blank=True, null=True)
    soc = models.JSONField(blank=True, null=True)
    ess_discharge = models.JSONField(blank=True, null=True)
    ess_charge = models.JSONField(blank=True, null=True)
    unmet_demand = models.JSONField(blank=True, null=True)
    generation = models.JSONField(blank=True, null=True)
    curtailment = models.JSONField(blank=True, null=True)
    total_demand_met_by_allocation = models.JSONField(blank=True, null=True)
    demand_met = models.JSONField(blank=True, null=True)
    state = models.JSONField(blank=True, null=True)
    site_name = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"{self.generator} - {self.record_name} - {self.combination}"

class OfflinePayment(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'), 
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected')
    ]

    invoice = models.ForeignKey(PerformaInvoice, on_delete=models.CASCADE)
    transaction_id = models.CharField(max_length=100)
    payment_date = models.DateField()
    payment_mode = models.CharField(max_length=50)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

class BankingOrder(models.Model):
    name = models.CharField(max_length=100, default="Default", unique=True)
    order = models.JSONField(default=list)  # Stores list like ['peak_1', 'peak_2', 'normal', 'off_peak']

    def __str__(self):
        return self.name