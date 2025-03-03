# tasks.py
import json
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from channels.db import database_sync_to_async
from .models import NegotiationWindow, Tariffs
from datetime import timedelta
from django_celery_beat.models import PeriodicTask

@shared_task
def send_negotiation_reminder(negotiation_window_id, attempt):
    """
    Checks status and sends reminder emails.
    If the window is still pending, it schedules the next attempt for the next day.
    """
    try:
        window = NegotiationWindow.objects.get(id=negotiation_window_id)

        # Stop if the window is accepted/rejected
        if window.status in ["Accepted", "Rejected"]:
            print(f"Window {window.id} is {window.status}. No more reminders.")
            return "Stopped: Window resolved."

        # Send email notification
        print(f"Sending reminder {attempt} for Negotiation Window {window.id}")
        send_mail(
            subject="Negotiation Window Reminder",
            message=f"Your negotiation window (ID: {window.id}) is still pending action. Please accept or reject.",
            from_email="noreply@example.com",
            recipient_list=[window.terms_sheet.user.email]
        )

        # If attempt < 2, schedule the next reminder for the next day
        if attempt < 2:
            next_run_time = window.end_time + timedelta(days=attempt)  # Next day
            PeriodicTask.objects.create(
                name=f'negotiation_reminder_{window.id}_attempt_{attempt + 1}',
                task='powerx.tasks.send_negotiation_reminder',
                args=json.dumps([window.id, attempt + 1]),
                one_off=True,  # Runs only once
                start_time=next_run_time
            )
            print(f"Next reminder {attempt + 1} scheduled for {next_run_time}")

        return "Reminder sent."

    except NegotiationWindow.DoesNotExist:
        print(f"Window {negotiation_window_id} not found. Task aborted.")
        return "Task aborted, window not found."