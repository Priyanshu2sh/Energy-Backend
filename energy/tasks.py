# tasks.py
import json
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from channels.db import database_sync_to_async
from .models import NegotiationWindow, Tariffs
from datetime import timedelta
from django_celery_beat.models import PeriodicTask, ClockedSchedule

@shared_task
def send_negotiation_reminder(tariff_id, attempt):
    """
    Checks status and sends reminder emails.
    If the window is still pending, it schedules the next attempt for the next day.
    """
    try:
        tariff = Tariffs.objects.get(id=tariff_id)
        window = NegotiationWindow.objects.get(terms_sheet=tariff.terms_sheet)

        # Stop if the window is accepted/rejected
        if tariff.window_status in ["Accepted", "Rejected"]:
            print(f"Window {window.name} is {tariff.window_status}. No more reminders.")
            return "Stopped: Window resolved."

        # Send email notification
        print(f"Sending reminder {attempt} for Negotiation Window {tariff.id}")
        send_mail(
            subject="Negotiation Window Reminder",
            message=f"Your negotiation window (ID: {window.name}) is still pending action. Please accept or reject.",
            from_email="noreply@example.com",
            recipient_list=[tariff.terms_sheet.consumer.email]
        )

        # If attempt < 2, schedule the next reminder for the next day
        if attempt < 2:
            next_run_time = window.end_time + timedelta(days=attempt)  # Next day
            # Create a clocked schedule for the specific execution time
            clocked_schedule, created = ClockedSchedule.objects.get_or_create(
                clocked_time=next_run_time
            )
            

            # Create a unique periodic task that runs one time
            task, created = PeriodicTask.objects.get_or_create(
                name=f'negotiation_reminder_{tariff.id}',  # Unique task name
                task='energy.tasks.send_negotiation_reminder',  # Celery task function
                defaults={
                    'args': json.dumps([tariff.id, 1]),  # Pass window ID + attempt count (1st attempt)
                    'one_off': True,  # Runs only once
                    'enabled': True,
                    'clocked': clocked_schedule  # Assign the clocked schedule
                }
            )
            print(f"Next reminder {attempt + 1} scheduled for {next_run_time}")

        return "Reminder sent."

    except Tariffs.DoesNotExist:
        print(f"Window {tariff_id} not found. Task aborted.")
        return "Task aborted, window not found."
    except NegotiationWindow.DoesNotExist:
        print(f"Window {tariff_id} not found. Task aborted.")
        return "Task aborted, window not found."