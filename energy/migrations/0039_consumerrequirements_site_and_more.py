# Generated by Django 4.2.10 on 2025-01-15 10:16

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('energy', '0038_generatoroffer_accepted_by_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='consumerrequirements',
            name='site',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='combination',
            name='requirement',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='combinations', to='energy.consumerrequirements'),
        ),
        migrations.AlterField(
            model_name='generatoroffer',
            name='accepted_by',
            field=models.ForeignKey(blank=True, limit_choices_to={'user_category': 'Consumer'}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='accepted_offers', to=settings.AUTH_USER_MODEL),
        ),
    ]
