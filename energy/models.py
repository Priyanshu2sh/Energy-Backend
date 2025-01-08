from django.db import models
from django.utils.timezone import now
# Create your models here.

# class State(models.Model):
#     name = models.CharField(max_length=255)
#     state_code = models.CharField(max_length=10)

#     def __str__(self):
#         return self.name
    

    
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
    total_install_capacity = models.FloatField(blank=True, null=True)
    available_capacity = models.FloatField()  # Maximum energy capacity (in kWh)
    capital_cost = models.FloatField(blank=True, null=True)
    marginal_cost = models.FloatField(blank=True, null=True)
    cod = models.DateField()  # COD (commercial operation date)
    updated = models.BooleanField(default=False)
    hourly_data = models.FileField(upload_to='hourly_data/', blank=True, null=True)
    annual_generation_potential = models.FloatField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.pk:  # If the instance is being created (not updated)
            user_entries_count = SolarPortfolio.objects.filter(user=self.user).count()
            self.project = f"Solar_{user_entries_count + 1}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.project}"

class WindPortfolio(models.Model):
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        limit_choices_to={'user_category': 'Generator'}
    )  # Restrict to users with user_category='Generator'
    project = models.CharField(max_length=255)
    state = models.CharField(max_length=255)  # State/Location of the energy source
    connectivity = models.CharField(max_length=255, blank=True, null=True)
    total_install_capacity = models.FloatField(blank=True, null=True)
    available_capacity = models.FloatField()  # Maximum energy capacity (in kWh)
    capital_cost = models.FloatField(blank=True, null=True)
    marginal_cost = models.FloatField(blank=True, null=True)
    cod = models.DateField()  # COD (commercial operation date)
    updated = models.BooleanField(default=False)
    hourly_data = models.FileField(upload_to='hourly_data/', blank=True, null=True)
    annual_generation_potential = models.FloatField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.pk:  # If the instance is being created (not updated)
            user_entries_count = WindPortfolio.objects.filter(user=self.user).count()
            self.project = f"Wind_{user_entries_count + 1}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.project}"


class ESSPortfolio(models.Model):
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'user_category': 'Generator'}) # Restrict to users with user_category='Generator'
    project = models.CharField(max_length=255)
    state = models.CharField(max_length=255)  # State/Location of the energy source
    connectivity = models.CharField(max_length=255, blank=True, null=True)
    total_install_capacity = models.FloatField(blank=True, null=True)
    available_capacity = models.FloatField()  # Maximum energy capacity (in kWh)
    capital_cost = models.FloatField(blank=True, null=True)
    marginal_cost = models.FloatField(blank=True, null=True)
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
        return f"{self.user.username} - {self.project}"
    








# Consumer models
class ConsumerRequirements(models.Model):
    # Foreign key to the User model
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'user_category': 'Consumer'}) # Restrict to users with user_category='Consumer'
    state = models.CharField(max_length=255)  # State/Location where the company is located
    industry = models.CharField(max_length=255)  # Industry your company is involved in (e.g., IT, Manufacturing)
    contracted_demand = models.FloatField()  # Total energy requirement for the consumer (in kWh)
    tariff_category = models.CharField(max_length=255)  # Select the tariff category applicable to your company (e.g., HT Commercial, LT Industrial).
    voltage_level = models.IntegerField()  # Select the voltage level of the electricity being supplied to your company.
    procurement_date = models.DateField()  # Select the date when the procurement of services or goods occurred (expected Date).

    def __str__(self):
        return f"Demand for {self.user} - {self.state} - {self.industry} - {self.contracted_demand} kWh"
    
class MonthlyConsumptionData(models.Model):
    requirement = models.ForeignKey(ConsumerRequirements, on_delete=models.CASCADE)
    month = models.CharField(max_length=255)
    monthly_consumption = models.FloatField()
    peak_consumption = models.FloatField()
    off_peak_consumption = models.FloatField()
    monthly_bill_amount = models.FloatField()
    bill = models.FileField(upload_to='bills/', blank=True, null=True)

    def __str__(self):
        return f"Monthly Consumption for {self.requirement} - {self.month}"
    
class HourlyDemand(models.Model):
    requirement = models.ForeignKey(ConsumerRequirements, on_delete=models.CASCADE)
    hourly_demand = models.TextField(blank=True, null=True)  # Stores a single string of values
    bulk_file = models.FileField(upload_to="bulk_file/", blank=True, null=True)  # File path

    def __str__(self):
        return f"{self.requirement}"

    def get_hourly_data_as_list(self):
        """Convert the stored string of values into a list of floats."""
        return list(map(float, self.hourly_demand.split(',')))

    def set_hourly_data_from_list(self, data_list):
        """Convert a list of floats into a comma-separated string and save it."""
        self.hourly_demand = ','.join(map(str, data_list))

class Combination(models.Model):
    requirement = models.ForeignKey(ConsumerRequirements, on_delete=models.CASCADE)
    generator = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'user_category': 'Generator'}, related_name='generator_combinations') # Restrict to users with user_category='Generator'
    combination = models.CharField(max_length=200)
    state = models.CharField(max_length=100, blank=True, null=True)
    optimal_solar_capacity = models.FloatField()
    optimal_wind_capacity = models.FloatField()
    optimal_battery_capacity = models.FloatField()
    per_unit_cost = models.FloatField()
    final_cost = models.FloatField()
    annual_demand_offset = models.FloatField()
    annual_curtailment = models.FloatField()
    request_sent = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.combination}"

class StandardTermsSheet(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Accepted', 'Accepted'),
        ('Rejected', 'Rejected'),
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
    status = models.CharField(max_length=100, choices=STATUS_CHOICES, default='Pending',help_text="Status of the terms sheet (Pending, Accepted, or Rejected)")

    def save(self, *args, **kwargs):
        if not self.pk:  # If the object is new
            self.count = 1  # Initialize count to 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.consumer} - {self.combination.requirement}"


# Model to store types of subscriptions
class SubscriptionType(models.Model):
    # Choices for user types
    USER_TYPE_CHOICES = [
        ('Consumer', 'Consumer'),
        ('Generator', 'Generator'),
    ]
    user_type = models.CharField(max_length=50, choices=USER_TYPE_CHOICES, default='Consumer',)  # Specifies if the plan is for consumers or generators
    name = models.CharField(max_length=255)  # Subscription plan name (e.g., Basic, Premium)
    description = models.TextField(blank=True, null=True)  # Optional description of the plan
    price = models.DecimalField(max_digits=10, decimal_places=2)  # Price of the subscription
    duration_in_days = models.PositiveIntegerField()  # Duration of the plan in days

    def __str__(self):
        return f"{self.name} ({self.user_type})"

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
        return f"{self.subscription.name} for {self.user} ({self.subscription.user_type})"
    
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

    def __str__(self):
        return f"Notification for {self.user}"
    
class Tariffs(models.Model):
    terms_sheet = models.ForeignKey(StandardTermsSheet, on_delete=models.CASCADE)
    offer_tariff = models.FloatField()

    def __str__(self):
        return f"Tariff for {self.terms_sheet}"
    
class GeneratorOffer(models.Model):
    generator = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'user_category': 'Generator'})
    tariff = models.ForeignKey(Tariffs, on_delete=models.CASCADE)
    updated_tariff = models.FloatField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Offer by {self.generator.username} for Terms Sheet {self.tariff}"

class NegotiationWindow(models.Model):
    terms_sheet = models.ForeignKey(StandardTermsSheet, on_delete=models.CASCADE)
    start_time = models.DateTimeField(default=now)
    end_time = models.DateTimeField()

    def is_active(self):
        return self.start_time <= now() <= self.end_time


class MatserTable(models.Model):
    state = models.CharField(max_length=200)
    ISTS_charges = models.FloatField()
    state_charges = models.FloatField()

class GridTariff(models.Model):
    state = models.CharField(max_length=200)    
    tariff_category = models.CharField(max_length=200)    
    cost = models.FloatField()

# class Recommendations(models.Model):
#     # Foreign key to EnergyDemands to link the recommendation to a specific demand
#     demand = models.ForeignKey('ConsumerRequirements', on_delete=models.CASCADE)  # Assuming EnergyDemands is in the same app
#     allocation_details = models.TextField()  # Details about how the energy is allocated
#     total_cost = models.FloatField()  # Total cost of the recommendation (e.g., cost for procuring energy)
#     environmental_impact = models.TextField()  # Description of the environmental impact of the recommendation

#     def __str__(self):
#         return f"Recommendation for {self.demand}"


    

# class Contracts(models.Model):
#     # Foreign key to link ConsumerID and GeneratorID to users or other entities
#     consumer = models.ForeignKey('accounts.User', related_name='consumer_contracts', on_delete=models.CASCADE)  # Assuming Consumer is a User
#     generator = models.ForeignKey('accounts.User', related_name='generator_contracts', on_delete=models.CASCADE)  # Assuming Generator is a User
#     allocation_details = models.TextField()  # Allocation details for the contract
#     pricing = models.FloatField()  # Pricing for the contract
#     duration = models.CharField(max_length=255)  # Duration of the contract (e.g., 1 year, 5 years)
#     status = models.CharField(max_length=255, choices=[('active', 'Active'), ('inactive', 'Inactive')])  # Status of the contract

#     def __str__(self):
#         return f"Contract between {self.consumer} and {self.generator}"

# class Analytics(models.Model):
#     # Foreign key to link the analytics data to a specific user
#     user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)  # Assuming User model is in the 'accounts' app
#     data = models.TextField()  # Analytics data in text format (could be JSON or other data)
#     generated_date = models.DateField()  # Date when the analytics data was generated

#     def __str__(self):
#         return f"Analytics for {self.user} - {self.generated_date}"