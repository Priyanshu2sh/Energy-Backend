from celery import shared_task
from powerx.AI_Model.model_scheduling import run_models_sequentially

@shared_task
def run_model_task():
    print("Running the AI model sequentially...")
    run_models_sequentially()
    return "Task executed successfully"
