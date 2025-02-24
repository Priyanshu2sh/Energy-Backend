from django.db import models

# Create your models here.
class ConsumerTradingDemand(models.Model):
    ENERGY_CHOICES = [
        ('Solar', 'Solar'),
        ('Wind', 'Wind'),
        ('Hydro', 'Hydro')
    ]

    consumer = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'user_category': 'Consumer'})
    energy_type = models.CharField(max_length=50, choices=ENERGY_CHOICES)
    date = models.DateField()
    start_time = models.TimeField() 
    end_time = models.TimeField() 
    demand = models.IntegerField()

class CleanData(models.Model):
    date = models.DateTimeField()
    hour = models.IntegerField()
    purchase_bid = models.FloatField()
    total_sell_bid = models.FloatField()
    sell_bid_solar = models.FloatField()
    sell_bid_non_solar = models.FloatField()
    sell_bid_hydro = models.FloatField()
    mcv_total = models.FloatField()
    mcv_solar = models.FloatField()
    mcv_non_solar = models.FloatField()
    mcv_hydro = models.FloatField()
    mcp = models.FloatField()
    year = models.IntegerField()
    month = models.IntegerField()
    day = models.IntegerField()

class NextDayPrediction(models.Model):
    date = models.DateTimeField()
    hour = models.IntegerField()
    mcv_prediction = models.FloatField(blank=True, null=True)
    mcp_prediction = models.FloatField(blank=True, null=True)