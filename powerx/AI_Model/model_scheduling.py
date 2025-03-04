# import time
# import schedule
# from mcp_mcv_final import run_predictions
# from mcp_week_ahead import run_predictions_mcp

# def run_models_sequentially():
#     print("Running the Next Day model predictions...")
#     run_predictions()

#     print("Running the Week Ahead model predictions...")
#     run_week_predictions() 

#     print("Running the Month Ahead model predictions...")
#     run_month_predictions() 
    
# schedule.every().day.at("00:00").do(run_models_sequentially) 
# while True:
#     schedule.run_pending()  
#     time.sleep(60)


import time
import schedule
from powerx.AI_Model.mcp_mcv_final import run_predictions
from powerx.AI_Model.month_ahead_model import run_mcv_predictions
# from mcp_week_ahead import run_predictions_mcp

def run_models_sequentially():
    print("Running the Next Day model predictions...")
    run_predictions()

def run_month_ahead_model():
    print("Running the Month Ahead model predictions...")
    run_mcv_predictions()

