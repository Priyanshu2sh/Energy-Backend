# Generated by Django 5.1.4 on 2025-01-03 05:04

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('energy', '0019_matchingipp'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SubscriptionType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user_type', models.CharField(choices=[('consumer', 'Consumer'), ('generator', 'Generator')], default='consumer', max_length=50)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, null=True)),
                ('price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('duration_in_days', models.PositiveIntegerField()),
            ],
        ),
        migrations.CreateModel(
            name='SubscriptionEnrolled',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('status', models.CharField(choices=[('active', 'Active'), ('inactive', 'Inactive'), ('expired', 'Expired')], default='active', max_length=50)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('subscription', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='energy.subscriptiontype')),
            ],
        ),
        migrations.DeleteModel(
            name='Subscriptions',
        ),
    ]
