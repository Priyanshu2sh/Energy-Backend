from accounts.models import User
from celery import shared_task
from powerx.AI_Model.model_scheduling import run_models_sequentially
from django.core.mail import send_mail
from energy_transition import settings

@shared_task(bind=True)
def run_model_task(self):
    run_models_sequentially()
    return "Task executed successfully"
