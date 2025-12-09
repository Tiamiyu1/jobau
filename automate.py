import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import gspread
from gspread_dataframe import set_with_dataframe
from google.oauth2.service_account import Credentials
import json
import os

# Authentication for GitHub Actions
def get_gspread_client():
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    if creds_json:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(
            creds_dict,
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
        )
    else:
        creds = Credentials.from_service_account_file(
            'credentials.json',
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
        )
    return gspread.authorize(creds)

try:
    gc = get_gspread_client()
    print("✓ Google Sheets connected successfully")
except Exception as e:
    print(f"✗ Failed to connect to Google Sheets: {e}")
    raise

def save_to_google_sheet(df, sheet_name, worksheet_name, replace=True):
    """Save job data to Google Sheets."""
    auth.authenticate_user()
    creds, _ = default()
    gc = gspread.authorize(creds)

    try:
        sh = gc.open(sheet_name)
        print(f"📘 Found existing Google Sheet: {sheet_name}")
    except gspread.SpreadsheetNotFound:
        sh = gc.create(sheet_name)
        print(f"🆕 Created new Google Sheet: {sheet_name}")

    try:
        worksheet = sh.worksheet(worksheet_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sh.add_worksheet(title=worksheet_name, rows=1000, cols=20)
        print(f"➕ Created new worksheet: {worksheet_name}")

    if replace:
        worksheet.clear()
        set_with_dataframe(worksheet, df)
        print(f"✅ Worksheet '{worksheet_name}' replaced with latest data.")
    else:
        existing = len(worksheet.get_all_values())
        set_with_dataframe(worksheet, df, row=existing + 1, include_column_header=False)
        print("➕ New data appended.")

    print(f"🔗 Google Sheet link: https://docs.google.com/spreadsheets/d/{sh.id}")

import pandas as pd
import numpy as np
import json

# Daily user
user = pd.read_json("https://api.alumunite.co/v1/user-daily-count")['data']
user = pd.DataFrame(user.tolist())
user.columns = ['date', "new_signups"]
user['date'] = pd.to_datetime(user['date']).dt.strftime('%Y-%m-%d')
user['cum_new_signups'] =user['new_signups'].cumsum()

# Scholarship
scholarship = pd.read_json("https://api.alumunite.co/v1/get-scholarship-fund" )['data']
scholarship = pd.DataFrame(scholarship.tolist())


configs = {
    "scholarship": {
        "df": scholarship,
        "sheet_name": "Scholarship Submission",
        "worksheet_name": "scholarship_submission"
    },
    "user": {
        "df": user,
        "sheet_name": "Daily User Data",
        "worksheet_name": "Sheet1"
    }
}

# Loop through and save
for cfg in configs.values():
    save_to_google_sheet(
        cfg["df"],
        sheet_name=cfg["sheet_name"],
        worksheet_name=cfg["worksheet_name"]
    )
