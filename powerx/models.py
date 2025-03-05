from django.db import models

# Create your models here.
class ConsumerDayAheadDemand(models.Model):
    requirement = models.ForeignKey('energy.ConsumerRequirements', on_delete=models.CASCADE)
    date = models.DateField()
    start_time = models.TimeField() 
    end_time = models.TimeField() 
    demand = models.IntegerField()
    price_details = models.JSONField()  # Stores prices as JSON: {"Solar": 20, "Non-Solar": 10}

class ConsumerMonthAheadDemand(models.Model):
    requirement = models.ForeignKey('energy.ConsumerRequirements', on_delete=models.CASCADE)
    date = models.DateField()
    demand = models.FloatField()  # Single demand value for all energy types
    price_details = models.JSONField()  # Stores prices as JSON: {"Solar": 20, "Non-Solar": 10}

class ConsumerMonthAheadDemandDistribution(models.Model):
    month_ahead_demand = models.ForeignKey(ConsumerMonthAheadDemand, on_delete=models.CASCADE, related_name="distributions")
    start_time = models.TimeField() # 00:00
    end_time = models.TimeField()   # 00:15
    distributed_demand = models.FloatField()  # Demand distributed per 15-minute slot

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

class MonthAheadPrediction(models.Model):
    date = models.DateTimeField()
    hour = models.IntegerField()
    mcv_prediction = models.FloatField(blank=True, null=True)
    mcp_prediction = models.FloatField(blank=True, null=True)

class Notifications(models.Model):
    # Foreign key to User model to link notification to a user
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='powerx_notifications')  # Assuming User model is in 'accounts' app
    message = models.TextField()  # The message to be sent to the user
    timestamp = models.DateTimeField(auto_now_add=True)  # Timestamp of when the notification was created
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"Notification for {self.user}"