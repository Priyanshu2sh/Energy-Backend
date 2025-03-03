from accounts.models import User
from celery import shared_task
from powerx.AI_Model.model_scheduling import run_models_sequentially
from django.core.mail import send_mail
from energy_transition import settings

@shared_task(bind=True)
def run_model_task(self):
    run_models_sequentially()
    return "Task executed successfully"

@shared_task(bind=True)
def send_mail_func(self):
    users = User.objects.all()
    for user in users:
        mail_subject = "Hi! Celery Testing"
        message = "Please accept any offer"
        to_email = user.email
        send_mail(
            subject = mail_subject,
            message = message,
            from_email = settings.EMAIL_HOST_USER,
            recipient_list = [to_email],
            fail_silently = True,
        )
    return "Done"