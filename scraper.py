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
    """Fetch detailed info for one job posting with robust extraction."""
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

    # Extract APPLICATION METHOD - FIXED to get actual href URL
    application_method = None
    application_instructions = None
    
    # Find the "application-method" or "Method of Application" section
    app_method_section = soup.find("h2", id="application-method")
    if not app_method_section:
        # Try alternative selectors
        for heading in soup.find_all(['h2', 'h3']):
            if 'application' in heading.get_text(strip=True).lower():
                app_method_section = heading
                break
    
    if app_method_section:
        # Get the div that follows the h2
        app_div = app_method_section.find_next_sibling("div")
        
        if app_div:
            # Get the full application instructions first
            application_instructions = app_div.get_text(separator=" ", strip=True)
            
            # Look for ANY link with href in the application div
            app_link = app_div.find("a", href=True)
            
            if app_link:
                link_href = app_link.get('href', '')
                
                # Extract the actual URL from href attribute
                if link_href.startswith('http'):
                    # It's already a full URL - use it directly
                    application_method = link_href
                elif link_href.startswith('/apply-now/'):
                    # Internal apply link - construct full URL
                    base_url = '/'.join(response.url.split('/')[:3])  # Get https://domain.com
                    application_method = base_url + link_href
                else:
                    # Might be email-based application
                    # Extract email from strong tag or text
                    email_tag = app_div.find("strong")
                    if email_tag:
                        email_text = email_tag.get_text(strip=True)
                        # Check if it's actually an email
                        if '@' in email_text:
                            email = email_text
                            subject = title.replace(" ", "%20") if title else "Job%20Application"
                            application_method = f"mailto:{email}?subject={subject}"
                    
                    if not application_method:
                        # Try to find email using regex in the instructions
                        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
                        email_match = re.search(email_pattern, application_instructions)
                        if email_match:
                            email = email_match.group(0)
                            subject = title.replace(" ", "%20") if title else "Job%20Application"
                            application_method = f"mailto:{email}?subject={subject}"
            else:
                # No link found, must be email-based
                email_tag = app_div.find("strong")
                if email_tag:
                    email_text = email_tag.get_text(strip=True)
                    if '@' in email_text:
                        email = email_text
                        subject = title.replace(" ", "%20") if title else "Job%20Application"
                        application_method = f"mailto:{email}"
                
                if not application_method:
                    # Last resort: regex search for email
                    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
                    email_match = re.search(email_pattern, application_instructions)
                    if email_match:
                        email = email_match.group(0)
                        subject = title.replace(" ", "%20") if title else "Job%20Application"
                        application_method = f"mailto:{email}"
                        #f"mailto:{email}?subject={subject}"

    # Extract job overview/summary - try multiple selectors
    overview = None
    overview_selectors = [
        "div.job-overview",
        "div.job-summary",
        "div[class*='overview']",
        "div[class*='summary']",
        "section.overview",
        "div.description-summary"
    ]
    
    for selector in overview_selectors:
        overview_section = soup.select_one(selector)
        if overview_section:
            overview = overview_section.get_text(separator="\n", strip=True)
            break
    
    # If no dedicated overview found, try to extract from the first paragraph
    if not overview:
        first_para = soup.select_one("div.job-details-section p:first-of-type")
        if first_para:
            overview = first_para.get_text(strip=True)

    # Extract full job description - try multiple approaches
    description = None
    description_selectors = [
        "div.job-details-section",
        "div.job-description",
        "div[class*='description']",
        "div.job-details",
        "section.job-content",
        "div#job-description"
    ]
    
    for selector in description_selectors:
        desc_section = soup.select_one(selector)
        if desc_section:
            description = desc_section.get_text(separator="\n", strip=True)
            break

    # Extract responsibilities section
    responsibilities = None
    resp_patterns = ["responsibilities", "duties", "key responsibilities", "what you'll do"]
    
    for heading in soup.find_all(['h2', 'h3', 'h4', 'strong', 'b']):
        heading_text = heading.get_text(strip=True).lower()
        if any(pattern in heading_text for pattern in resp_patterns):
            # Get the next sibling elements until another heading
            resp_content = []
            for sibling in heading.find_next_siblings():
                if sibling.name in ['h2', 'h3', 'h4'] or (sibling.name in ['strong', 'b'] and len(sibling.get_text(strip=True)) > 20):
                    break
                text = sibling.get_text(separator="\n", strip=True)
                if text:
                    resp_content.append(text)
            
            if resp_content:
                responsibilities = "\n".join(resp_content)
                break

    # Extract requirements/qualifications section
    requirements = None
    req_patterns = ["requirements", "qualifications", "what we're looking for", "you should have"]
    
    for heading in soup.find_all(['h2', 'h3', 'h4', 'strong', 'b']):
        heading_text = heading.get_text(strip=True).lower()
        if any(pattern in heading_text for pattern in req_patterns):
            req_content = []
            for sibling in heading.find_next_siblings():
                if sibling.name in ['h2', 'h3', 'h4'] or (sibling.name in ['strong', 'b'] and len(sibling.get_text(strip=True)) > 20):
                    break
                text = sibling.get_text(separator="\n", strip=True)
                if text:
                    req_content.append(text)
            
            if req_content:
                requirements = "\n".join(req_content)
                break

    # Salary detection
    page_text = soup.get_text(" ", strip=True)
    salary_pattern = re.compile(
        r'(?:salary|remuneration)[:\s]*([₦N]?\s?\d{1,3}(?:[,.\d]*)(?:\s?[KkMm]\b)?)',
        flags=re.IGNORECASE
    )

    salary_match = salary_pattern.search(page_text)
    salary = salary_match.group(1).strip() if salary_match else None
    
    # Also check in the details dict
    if not salary and 'salary' in details:
        salary = details['salary']

    # Combine all
    return {
        "Title": title,
        "Company": company,
        "Experience": details.get("experience"),
        "Qualification": details.get("qualification"),
        "Job Type": details.get("job type"),
        "State": details.get("location"),
        "City": details.get("city"),
        "Salary": salary,
        "Field": details.get("job field"),
        "Posted on": details.get("posted_date"),
        "Deadline": details.get("deadline_date"),
        # "Overview": overview,
        "Description": description,
        # "Responsibilities": responsibilities,
        # "Requirements": requirements,
        "Apply Now": application_method,        
        # "Apply": job_url,
        # "Application Instructions": application_instructions,
        # "Raw_Details": details
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
def save_to_google_sheet(df, sheet_name="AlumUnite Job Board", replace=True):
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
