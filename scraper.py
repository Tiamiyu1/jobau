# -*- coding: utf-8 -*-

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

# --------------------------------------------
# CONFIGURATION
# --------------------------------------------
BASE_URL = "https://www.myjobmag.com"
TODAY_URL = f"{BASE_URL}/jobs-by-date/today"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


# --------------------------------------------
# SCRAPING FUNCTIONS
# --------------------------------------------
def get_today_jobs():
    """Fetch all job listings across all pages for today's postings."""
    all_jobs = []
    page = 1

    while True:
        # Build URL for each page
        if page == 1:
            url = TODAY_URL
        else:
            url = f"{TODAY_URL}/{page}"

        print(f"Scraping page {page}: {url}")
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"❌ Failed to fetch page {page}. Stopping.")
            break

        soup = BeautifulSoup(response.text, "html.parser")
        job_divs = soup.select("li.job-list-li")

        # Stop when no job listings are found (end of pages)
        if not job_divs:
            print(f"✅ No more jobs found after page {page-1}.")
            break

        for job_div in job_divs:
            title_tag = job_div.select_one("h2 a")
            location_tag = job_div.select_one("span a")

            if not title_tag or not title_tag.get("href"):
                continue

            title_text = title_tag.get_text(strip=True)

            # Split "at" if it exists, e.g., "HR Associate at HR Aid"
            if " at " in title_text:
                parts = title_text.split(" at ", 1)
                title = parts[0].strip()
                company = parts[1].strip()
            else:
                title = title_text.strip()
                company = None

            location = location_tag.get_text(strip=True) if location_tag else None
            link = BASE_URL + title_tag["href"]

            all_jobs.append({
                "title": title,
                "company": company,
                "location": location,
                "link": link
            })

        print(f"✅ Page {page} - {len(job_divs)} jobs scraped.")
        page += 1
        time.sleep(1)  # be polite to the server

    print(f"\n🎯 Total jobs found across all pages: {len(all_jobs)}")
    return all_jobs


def get_job_details(job_url):
    """Fetch detailed info for one job posting."""
    response = requests.get(job_url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    # Extract title and company
    title_tag = soup.select_one("h1")
    title_text = title_tag.get_text(strip=True) if title_tag else None

    if title_text and " at " in title_text:
        parts = title_text.split(" at ", 1)
        title = parts[0].strip()
        company = parts[1].strip()
    else:
        title = title_text
        company_tag = soup.select_one("div.company-name a")
        company = company_tag.get_text(strip=True) if company_tag else None

    # Extract job metadata
    details = {}
    for li in soup.select("ul.job-key-info li"):
        key_tag = li.select_one("span.jkey-title")
        val_tag = li.select_one("span.jkey-info")

        if not key_tag or not val_tag:
            continue

        key = key_tag.get_text(strip=True).lower()
        value = val_tag.get_text(" ", strip=True)
        details[key] = value

    # Posted and deadline dates
    posted_tag = soup.find("b", class_="tc-o")
    if posted_tag and posted_tag.parent:
        posted_text = posted_tag.parent.get_text(" ", strip=True)
        posted_text = posted_text.replace("Posted :", "").replace("Posted:", "").strip()
        details["posted_date"] = posted_text

    deadline_tag = soup.find("b", class_="tc-bl3")
    if deadline_tag and deadline_tag.parent:
        deadline_text = deadline_tag.parent.get_text(" ", strip=True)
        deadline_text = deadline_text.replace("Deadline :", "").replace("Deadline:", "").strip()
        details["deadline_date"] = deadline_text

    # Description
    desc_section = soup.select_one("div.job-details-section")
    description = desc_section.get_text(separator="\n", strip=True) if desc_section else None

    # Salary detection
    page_text = soup.get_text(" ", strip=True)
    salary_pattern = re.compile(
        r'(?:salary|remuneration)[:\s]*([₦N]?\s?\d{1,3}(?:[,.\d]*)(?:\s?[KkMm]\b)?)',
        flags=re.IGNORECASE
    )

    salary_match = salary_pattern.search(page_text)
    details['salary'] = salary_match.group(1).strip() if salary_match else None

    # Combine all
    return {
        "Title": title,
        "Company": company,
        "Experience": details.get("experience"),
        "Qualification": details.get("qualification"),
        "Job Type": details.get("job type"),
        "State": details.get("location"),
        "City": details.get("city"),
        "Salary": details.get("salary"),
        "Field": details.get("job field"),
        "Posted on": details.get("posted_date"),
        "Deadline": details.get("deadline_date"),
        "Apply": job_url
    }


# --------------------------------------------
# MAIN SCRAPING WORKFLOW
# --------------------------------------------
def main():
    # Step 1: Get today’s job listings
    summary_jobs = get_today_jobs()
    print(f"Found {len(summary_jobs)} jobs today.")

    # Step 2: Fetch detailed info for each job
    detailed_jobs = []
    for i, job in enumerate(summary_jobs, start=1):
        print(f"Fetching job {i}/{len(summary_jobs)}: {job['title']}")
        try:
            details = get_job_details(job["link"])
            detailed_jobs.append(details)
            time.sleep(1.5)  # polite scraping
        except Exception as e:
            print(f"Error fetching {job['link']}: {e}")
        # break  # Remove this 'break' if you want to scrape all jobs

    # Step 3: Save to DataFrame
    df = pd.DataFrame(detailed_jobs)
    print(df.head())

    # Step 4: Save to Google Sheets
    save_to_google_sheet(df)

# --------------------------------------------
# GOOGLE SHEETS INTEGRATION
# --------------------------------------------
def save_to_google_sheet(df, sheet_name="MyJobMag_Jobs_Latest", replace=True):
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


# --------------------------------------------
# RUN SCRIPT
# --------------------------------------------
if __name__ == "__main__":
    main()
