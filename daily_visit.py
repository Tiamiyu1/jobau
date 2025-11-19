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

def save_to_google_sheet(df, sheet_name="Daily User Data", replace=True):
    try:
        sh = gc.open(sheet_name)
        print(f"📘 Found existing Google Sheet: {sheet_name}")
    except gspread.SpreadsheetNotFound:
        sh = gc.create(sheet_name)
        print(f"🆕 Created new Google Sheet: {sheet_name}")

    try:
        worksheet = sh.get_worksheet(0)
    except IndexError:
        worksheet = sh.add_worksheet(title="Today_Jobs", rows=1000, cols=20)

    if replace:
        worksheet.clear()
        set_with_dataframe(worksheet, df)
        print("✅ Sheet replaced with latest job data.")
    else:
        existing = len(worksheet.get_all_values())
        set_with_dataframe(worksheet, df, row=existing + 1, include_column_header=False)
        print("➕ New job data appended.")

    print(f"🔗 Google Sheet link: https://docs.google.com/spreadsheets/d/{sh.id}")

import pandas as pd
import numpy as np
import json


dat = pd.read_json("https://api.alumunite-staging.com/v1/user-daily-count" )['data']
data = pd.read_json("https://api.alumunite.co/v1/user-daily-count")['data']

dat = pd.DataFrame(dat.tolist())
data = pd.DataFrame(data.tolist())

df = pd.merge(dat, data, on='date', how='inner')
df.columns = ['date', "stagging", "new_signups"]

# Convert the 'date' column to datetime objects
df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
df['cum_stage'], df['cum_new_signups'] = df['stagging'].cumsum(), df['new_signups'].cumsum()
save_to_google_sheet(df)
