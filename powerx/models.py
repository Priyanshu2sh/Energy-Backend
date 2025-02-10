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