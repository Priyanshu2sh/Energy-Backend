from django.db import models

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
    capacity = models.FloatField()  # Maximum energy capacity (in kWh)
    total_install_capacity = models.FloatField(blank=True, null=True)
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
    capacity = models.FloatField()  # Maximum energy capacity (in kWh)
    total_install_capacity = models.FloatField(blank=True, null=True)
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
    capacity = models.FloatField()  # Maximum energy capacity (in kWh)
    total_install_capacity = models.FloatField(blank=True, null=True)
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
        return f"Demand for {self.user} - {self.contracted_demand} kWh"
    
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
    generator = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'user_category': 'Generator'}, related_name='generator_terms_sheets')  # Unique related_name for generator
    requirement = models.ForeignKey(ConsumerRequirements, on_delete=models.CASCADE, blank=True, null=True)
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
        return f"{self.consumer} - {self.generator}"

class Subscriptions(models.Model):
    # Foreign key to User model to link subscription to a user
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)  # Assuming User model is in 'accounts' app
    plan_type = models.CharField(max_length=255)  # The type of subscription plan (e.g., Basic, Premium)
    plan_details = models.CharField(max_length=255)
    start_date = models.DateField()  # Start date of the subscription
    end_date = models.DateField()  # End date of the subscription

    def __str__(self):
        return f"{self.plan_type} Subscription for {self.user}"
    
# class Recommendations(models.Model):
#     # Foreign key to EnergyDemands to link the recommendation to a specific demand
#     demand = models.ForeignKey('ConsumerRequirements', on_delete=models.CASCADE)  # Assuming EnergyDemands is in the same app
#     allocation_details = models.TextField()  # Details about how the energy is allocated
#     total_cost = models.FloatField()  # Total cost of the recommendation (e.g., cost for procuring energy)
#     environmental_impact = models.TextField()  # Description of the environmental impact of the recommendation

#     def __str__(self):
#         return f"Recommendation for {self.demand}"


# class Notifications(models.Model):
#     # Foreign key to User model to link notification to a user
#     user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)  # Assuming User model is in 'accounts' app
#     message = models.TextField()  # The message to be sent to the user
#     timestamp = models.DateTimeField(auto_now_add=True)  # Timestamp of when the notification was created
#     status = models.CharField(max_length=20, choices=[('sent', 'Sent'), ('read', 'Read'), ('pending', 'Pending')])  # Status of the notification

#     def __str__(self):
#         return f"Notification for {self.user} - {self.status}"
    
# class Tariffs(models.Model):
#     state = models.CharField(max_length=255)  # State to which the tariff applies
#     open_access_charges = models.FloatField()  # Open access charges
#     monthly_transmission_charges = models.FloatField()  # Monthly transmission charges
#     calculation_details = models.TextField()  # Detailed calculation of the charges

#     def __str__(self):
#         return f"Tariff for {self.state}"

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