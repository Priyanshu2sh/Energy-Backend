# Generated by Django 4.2.10 on 2025-01-27 06:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_user_registration_token_subuserinvite'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(blank=True, choices=[('Admin', 'Admin'), ('Management', 'Management'), ('Edit', 'Edit'), ('View', 'View')], default='Admin', max_length=50, null=True),
        ),
        migrations.DeleteModel(
            name='SubUserInvite',
        ),
    ]
