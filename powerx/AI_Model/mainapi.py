from fastapi import FastAPI, HTTPException
import pandas as pd
from datetime import datetime

DUMMY_DATA_FILE = "dummy_data.xlsx"
dummy_data = pd.read_excel(DUMMY_DATA_FILE)

dummy_data['Date'] = pd.to_datetime(dummy_data['Date']).dt.date

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Welcome to the Dummy Data API!"}

@app.get("/data/{date}")
def get_data(date: str):
    """Fetch all rows (96 blocks) for a specific date."""
    try:
        query_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    filtered_data = dummy_data[dummy_data['Date'] == query_date]
    print(filtered_data) 

    if filtered_data.empty:
        raise HTTPException(status_code=404, detail="No data found for the given date.")

    return filtered_data.to_dict(orient="records")
