# Generated by Django 5.1.4 on 2024-12-23 10:43

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('energy', '0004_generationportfolio_year_of_commissioning'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='generationportfolio',
            name='year_of_commissioning',
        ),
    ]
