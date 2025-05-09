from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

# Create your models here.
class ConsumerDayAheadDemand(models.Model):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('submitted to trader', 'submitted to trader'),
        ('Trade Executed', 'Trade Executed'),
        ('Trade Failed', 'Trade Failed'),
    ]
    requirement = models.ForeignKey('energy.ConsumerRequirements', on_delete=models.CASCADE)
    date = models.DateField()
    demand = models.IntegerField(blank=True, null=True)
    price_details = models.JSONField(blank=True, null=True)  # Stores prices as JSON: {"Solar": 20, "Non-Solar": 10}
    status = models.CharField(max_length=200, choices=STATUS_CHOICES, default="Draft")

class ConsumerDayAheadDemandDistribution(models.Model):
    day_ahead_demand = models.ForeignKey(ConsumerDayAheadDemand, on_delete=models.CASCADE, related_name="day_ahead_distributions")
    start_time = models.TimeField(null=True, blank=True)  # e.g., 00:00
    end_time = models.TimeField()    # e.g., 00:15
    distributed_demand = models.FloatField()  # Demand value per 15-minute interval

class ConsumerMonthAheadDemand(models.Model):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('submitted to trader', 'submitted to trader'),
        ('Trade Executed', 'Trade Executed'),
        ('Trade Failed', 'Trade Failed'),
    ]
    requirement = models.ForeignKey('energy.ConsumerRequirements', on_delete=models.CASCADE)
    date = models.DateField()
    demand = models.FloatField()  # Single demand value for all energy types
    price_details = models.JSONField()  # Stores prices as JSON: {"Solar": 20, "Non-Solar": 10}
    status = models.CharField(max_length=200, choices=STATUS_CHOICES, default="Draft")

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
    
class DayAheadGeneration(models.Model):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('submitted to trader', 'submitted to trader'),
        ('Trade Executed', 'Trade Executed'),
        ('Trade Failed', 'Trade Failed'),
    ]

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, limit_choices_to={'app_label': 'energy', 'model__in': ['solarportfolio', 'windportfolio']}
    )
    object_id = models.PositiveIntegerField()
    portfolio = GenericForeignKey('content_type', 'object_id')

    date = models.DateField()
    generation = models.IntegerField()
    price = models.IntegerField()
    status = models.CharField(max_length=200, choices=STATUS_CHOICES, default="Draft")

class DayAheadGenerationDistribution(models.Model):
    day_ahead_generation = models.ForeignKey(
        DayAheadGeneration,
        on_delete=models.CASCADE,
        related_name="day_generation_distributions"
    )
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField()
    distributed_generation = models.FloatField()

    def __str__(self):
        return f"{self.day_ahead_generation} | {self.start_time}-{self.end_time} | {self.distributed_generation}"


class MonthAheadGeneration(models.Model):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('submitted to trader', 'submitted to trader'),
        ('Trade Executed', 'Trade Executed'),
        ('Trade Failed', 'Trade Failed'),
    ]
    
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, limit_choices_to={'app_label': 'energy', 'model__in': ['solarportfolio', 'windportfolio']}
    )
    object_id = models.PositiveIntegerField()
    portfolio = GenericForeignKey('content_type', 'object_id')

    date = models.DateField()
    generation = models.FloatField()  # Single generation value for all energy types
    price = models.IntegerField()
    status = models.CharField(max_length=200, choices=STATUS_CHOICES, default="Draft")

class MonthAheadGenerationDistribution(models.Model):
    month_ahead_generation = models.ForeignKey(MonthAheadGeneration, on_delete=models.CASCADE, related_name="generation_distributions")
    start_time = models.TimeField() # 00:00
    end_time = models.TimeField()   # 00:15
    distributed_generation = models.FloatField()  # Generation distributed per 15-minute slot


class UploadedTradeFile(models.Model):
    TRADE_TYPE_CHOICES = [
        ('demand', 'Demand'),
        ('generation', 'Generation'),
    ]

    trade_type = models.CharField(max_length=20, choices=TRADE_TYPE_CHOICES)
    demand = models.ForeignKey(ConsumerDayAheadDemand, on_delete=models.SET_NULL, null=True, blank=True)
    generation = models.ForeignKey(DayAheadGeneration, on_delete=models.SET_NULL, null=True, blank=True)
    file = models.FileField(upload_to='trade_files/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Save file first so path exists
        self.process_file()

    def process_file(self):
        import pandas as pd
        from datetime import datetime

        df = pd.read_excel(self.file.path)
        for _, row in df.iterrows():
            date = pd.to_datetime(row['Date']).date()
            time_interval = row['Time Interval']  # e.g., "00:00 - 00:15"
            start_str, end_str = time_interval.split(' - ')
            start_time = datetime.strptime(start_str.strip(), "%H:%M").time()
            end_time = datetime.strptime(end_str.strip(), "%H:%M").time()

            if self.trade_type == 'demand':
                ExecutedDemandTrade.objects.create(
                    demand=self.demand,
                    date=date,
                    start_time=start_time,
                    end_time=end_time,
                    asked_demand=row['Asked Demand'],
                    executed_demand=row['Executed Demand'],
                    asked_price=row['Asked Price'],
                    executed_price=row['Executed Price'],
                )
            elif self.trade_type == 'generation':
                ExecutedGenerationTrade.objects.create(
                    generation=self.generation,
                    date=date,
                    start_time=start_time,
                    end_time=end_time,
                    asked_generation=row['Asked Generation'],
                    executed_generation=row['Executed Generation'],
                    asked_price=row['Asked Price'],
                    executed_price=row['Executed Price'],
                )

class ExecutedDayDemandTrade(models.Model):
    demand = models.ForeignKey(ConsumerDayAheadDemand, blank=True, null=True, on_delete=models.SET_NULL)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    asked_demand = models.IntegerField()
    executed_demand = models.IntegerField()
    asked_price = models.IntegerField()
    executed_price = models.IntegerField()

class ExecutedDayGenerationTrade(models.Model):
    generation = models.ForeignKey(DayAheadGeneration, blank=True, null=True, on_delete=models.SET_NULL)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    asked_generation = models.IntegerField()
    executed_generation = models.IntegerField()
    asked_price = models.IntegerField()
    executed_price = models.IntegerField()
