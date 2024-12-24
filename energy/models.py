from django.db import models

# Create your models here.
# class State(models.Model):
#     name = models.CharField(max_length=255)
#     state_code = models.CharField(max_length=10)

#     def __str__(self):
#         return self.name
    

    
# Generator models
class GenerationPortfolio(models.Model):
    # Foreign key to the User model to link the profile to a user
    ENERGY_CHOICES = [
        ('Solar', 'Solar'),
        ('Wind', 'Wind'),
        ('ESS', 'ESS'),  # Energy Storage System
    ]


    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'user_category': 'Generator'}) # Restrict to users with user_category='Generator'
    energy_type = models.CharField(max_length=255, choices=ENERGY_CHOICES) # Restrict energy types to specific choices
    state = models.CharField(max_length=255)  # State/Location of the energy source
    connectivity = models.CharField(max_length=255, blank=True, null=True)
    capacity = models.IntegerField()  # Maximum energy capacity (in kWh)
    total_install_capacity = models.IntegerField(blank=True, null=True)
    capital_cost = models.IntegerField(blank=True, null=True)
    marginal_cost = models.IntegerField(blank=True, null=True)
    cod = models.DateField()  # COD (commercial operation date)
    updated = models.BooleanField(default=False)

    # for Solar and Wind
    hourly_data = models.IntegerField(blank=True, null=True)
    annual_generation_potential = models.IntegerField(blank=True, null=True)

    
    # for ESS
    efficiency_of_storage = models.IntegerField(blank=True, null=True)
    efficiency_of_dispatch = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return f"{self.energy_type} - {self.user}"
    










# Consumer models
class ConsumerRequirements(models.Model):
    # Foreign key to the User model
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'user_category': 'Consumer'}) # Restrict to users with user_category='Consumer'
    state = models.CharField(max_length=255)  # State/Location where the company is located
    industry = models.CharField(max_length=255)  # Industry your company is involved in (e.g., IT, Manufacturing)
    contracted_demand = models.IntegerField()  # Total energy requirement for the consumer (in kWh)
    tariff_category = models.CharField(max_length=255)  # Select the tariff category applicable to your company (e.g., HT Commercial, LT Industrial).
    voltage_level = models.IntegerField()  # Select the voltage level of the electricity being supplied to your company.
    procurement_date = models.DateField()  # Select the date when the procurement of services or goods occurred (expected Date).

    def __str__(self):
        return f"Demand for {self.user} - {self.contracted_demand} kWh"
    
class MonthlyConsumptionData(models.Model):
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'user_category': 'Consumer'}) # Restrict to users with user_category='Consumer'
    month = models.CharField(max_length=255)
    monthly_consumption = models.IntegerField()
    peak_consumption = models.IntegerField()
    off_peak_consumption = models.IntegerField()
    monthly_bill_amount = models.IntegerField()

    def __str__(self):
        return f"Monthly Consumption for {self.user} - {self.month}"




    
# class Recommendations(models.Model):
#     # Foreign key to EnergyDemands to link the recommendation to a specific demand
#     demand = models.ForeignKey('ConsumerRequirements', on_delete=models.CASCADE)  # Assuming EnergyDemands is in the same app
#     allocation_details = models.TextField()  # Details about how the energy is allocated
#     total_cost = models.FloatField()  # Total cost of the recommendation (e.g., cost for procuring energy)
#     environmental_impact = models.TextField()  # Description of the environmental impact of the recommendation

#     def __str__(self):
#         return f"Recommendation for {self.demand}"

# class Subscriptions(models.Model):
#     # Foreign key to User model to link subscription to a user
#     user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)  # Assuming User model is in 'accounts' app
#     plan_type = models.CharField(max_length=255)  # The type of subscription plan (e.g., Basic, Premium)
#     start_date = models.DateField()  # Start date of the subscription
#     end_date = models.DateField()  # End date of the subscription

#     def __str__(self):
#         return f"{self.plan_type} Subscription for {self.user}"

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