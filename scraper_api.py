# -*- coding: utf-8 -*-

import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import json
import os

# --------------------------------------------
# CONFIGURATION
# --------------------------------------------
BASE_URL = "https://www.myjobmag.com"
TODAY_URL = f"{BASE_URL}/jobs-by-date/today"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# API Configuration
API_BASE_URL = os.environ.get('API_BASE_URL', 'https://api.alumunite-staging.com')  # Change to production when ready
API_ENDPOINT = f"{API_BASE_URL}/v1/store-job-api"

# --------------------------------------------
# SCRAPING FUNCTIONS
# --------------------------------------------
def get_today_jobs(max_jobs=None):
    """Fetch job listings from today's postings."""
    all_jobs = []
    page = 1

    while True:
        if page == 1:
            url = TODAY_URL
        else:
            url = f"{TODAY_URL}/{page}"

        print(f"📄 Scraping page {page}: {url}")
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"❌ Failed to fetch page {page}. Stopping.")
            break

        soup = BeautifulSoup(response.text, "html.parser")
        job_divs = soup.select("li.job-list-li")

        if not job_divs:
            print(f"✅ No more jobs found after page {page-1}.")
            break

        for job_div in job_divs:
            title_tag = job_div.select_one("h2 a")
            location_tag = job_div.select_one("span a")

            if not title_tag or not title_tag.get("href"):
                continue

            title_text = title_tag.get_text(strip=True)

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
            
            # Stop if we've reached max_jobs
            if max_jobs and len(all_jobs) >= max_jobs:
                print(f"✋ Reached limit of {max_jobs} jobs")
                return all_jobs

        print(f"   Found {len(job_divs)} jobs on page {page}")
        page += 1
        time.sleep(1)

    print(f"\n🎯 Total jobs found: {len(all_jobs)}")
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

    # Extract APPLICATION METHOD
    application_method = None
    application_instructions = None
    
    app_method_section = soup.find("h2", id="application-method")
    if not app_method_section:
        for heading in soup.find_all(['h2', 'h3']):
            if 'application' in heading.get_text(strip=True).lower():
                app_method_section = heading
                break
    
    if app_method_section:
        app_div = app_method_section.find_next_sibling("div")
        
        if app_div:
            application_instructions = app_div.get_text(separator=" ", strip=True)
            app_link = app_div.find("a", href=True)
            
            if app_link:
                link_href = app_link.get('href', '')
                
                if link_href.startswith('http'):
                    application_method = link_href
                elif link_href.startswith('/apply-now/'):
                    base_url = '/'.join(response.url.split('/')[:3])
                    application_method = base_url + link_href
                else:
                    email_tag = app_div.find("strong")
                    if email_tag:
                        email_text = email_tag.get_text(strip=True)
                        if '@' in email_text:
                            email = email_text
                            subject = title.replace(" ", "%20") if title else "Job%20Application"
                            application_method = f"mailto:{email}?subject={subject}"
                    
                    if not application_method:
                        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
                        email_match = re.search(email_pattern, application_instructions)
                        if email_match:
                            email = email_match.group(0)
                            subject = title.replace(" ", "%20") if title else "Job%20Application"
                            application_method = f"mailto:{email}?subject={subject}"
            else:
                email_tag = app_div.find("strong")
                if email_tag:
                    email_text = email_tag.get_text(strip=True)
                    if '@' in email_text:
                        email = email_text
                        subject = title.replace(" ", "%20") if title else "Job%20Application"
                        application_method = f"mailto:{email}"
                
                if not application_method:
                    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
                    email_match = re.search(email_pattern, application_instructions)
                    if email_match:
                        email = email_match.group(0)
                        subject = title.replace(" ", "%20") if title else "Job%20Application"
                        application_method = f"mailto:{email}"


    # Extract description
    description = None
    description_selectors = [
        "div.job-details-section",
        "div.job-description",
        "div[class*='description']",
    ]
    
    for selector in description_selectors:
        desc_section = soup.select_one(selector)
        if desc_section:
            description = desc_section.get_text(separator="\n", strip=True)
            break

    # Salary detection
    page_text = soup.get_text(" ", strip=True)
    salary_pattern = re.compile(
        r'(?:salary|remuneration)[:\s]*([₦N]?\s?\d{1,3}(?:[,.\d]*)(?:\s?[KkMm]\b)?)',
        flags=re.IGNORECASE
    )

    salary_match = salary_pattern.search(page_text)
    salary = salary_match.group(1).strip() if salary_match else None
    
    if not salary and 'salary' in details:
        salary = details['salary']

    return {
        "Title": title,
        "Company": company,
        "Description": description,
        "Experience": details.get("experience"),
        "Qualification": details.get("qualification"),
        "Job Type": details.get("job type"),
        "State": details.get("location"),
        "City": details.get("city"),
        "Salary": salary,
        "Field": details.get("job field"),
        "Posted on": details.get("posted_date"),
        "Deadline": details.get("deadline_date"),
        "Apply Now": application_method,
    }


# --------------------------------------------
# API INTEGRATION
# --------------------------------------------
def map_job_to_api_format(job):
    """Convert scraped job data to API format."""
    
    # Extract skills from description/requirements
    skills = []
    text_to_search = f"{job.get('Description', '')} {job.get('Requirements', '')}"
    common_skills = [
        "Python", "JavaScript", "Java", "PHP", "Laravel", "React", "Node.js",
        "SQL", "MySQL", "PostgreSQL", "MongoDB", "AWS", "Azure", "Docker",
        "Git", "TypeScript", "Vue.js", "Angular", "Django", "Flask"
    ]
    for skill in common_skills:
        if skill.lower() in text_to_search.lower():
            skills.append(skill)
            
    
    # Parse deadline to expiration_date
    expiration_date = None
    deadline = job.get("Deadline")
    if deadline:
        try:
            from datetime import datetime
            # Try to parse common date formats
            for fmt in ["%B %d, %Y", "%d %B %Y", "%Y-%m-%d", "%d/%m/%Y"]:
                try:
                    date_obj = datetime.strptime(deadline, fmt)
                    expiration_date = date_obj.strftime("%Y-%m-%d")
                    break
                except:
                    continue
        except:
            pass
    
    # Build location
    location_parts = [job.get("City"), job.get("State")]
    location = ", ".join(filter(None, location_parts)) or "Nigeria"
    
    # Parse salary
    salary_range = None
    currency = "NGN"
    salary_raw = job.get("Salary")
    if salary_raw:
        # Clean salary string
        salary_clean = re.sub(r'[₦N,]', '', str(salary_raw)).strip()
        # Check if it's a range
        if '-' in salary_clean or 'to' in salary_clean.lower():
            salary_range = salary_clean
        else:
            salary_range = salary_clean
    
    return {
        "company": job.get("Company"),
        "title": job.get("Title"),
        "description": job.get("Description"),
        "overview": job.get("Description"),
        "responsibilities": job.get("Description"),
        "url": job.get("Apply Now"),
        "expiration_date": expiration_date,
        "location": location,
        "job_type": job.get("Job Type"),
        "employment_type": job.get("Job Type"),
        "experience_level": job.get("Experience"),
        "qualifications": job.get("Qualification"),
        "skills": skills[:5] if skills else ["General"],  
        "currency": currency,
        "salary_range": salary_range,
        "pay_schedule": "Monthly",
        "benefits": "Not specified"
    }


def push_job_to_api(job_data):
    """Push a single job to the API."""
    try:
        api_payload = map_job_to_api_format(job_data)
        
        response = requests.post(
            API_ENDPOINT,
            json=api_payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code in [200, 201]:
            print(f"   ✅ Successfully posted: {job_data.get('Title')}")
            return True
        else:
            print(f"   ❌ API Error ({response.status_code}): {job_data.get('Title')}")
            print(f"      Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"   ❌ Exception posting {job_data.get('Title')}: {e}")
        return False


# --------------------------------------------
# MAIN SCRAPING WORKFLOW
# --------------------------------------------
def main():
    print(f"🚀 Starting job scraper...")
    print(f"📡 API Endpoint: {API_ENDPOINT}\n")
    
    # Step 1: Get today's job listings
    summary_jobs = get_today_jobs(max_jobs=1)
    
    if not summary_jobs:
        print("❌ No jobs found. Exiting.")
        return

    # Step 2: Fetch detailed info and push to API
    successful = 0
    failed = 0
    
    for i, job in enumerate(summary_jobs, start=1):
        print(f"\n🔍 Processing job {i}/{len(summary_jobs)}: {job['title']}")
        try:
            details = get_job_details(job["link"])
            
            # Push to API
            if push_job_to_api(details):
                successful += 1
            else:
                failed += 1
            
            time.sleep(1.5)  # Be polite
            
        except Exception as e:
            print(f"   ❌ Error processing {job['link']}: {e}")
            failed += 1
    
    # Summary
    print(f"\n{'='*50}")
    print(f"📊 SCRAPING SUMMARY")
    print(f"{'='*50}")
    print(f"✅ Successfully posted: {successful}")
    print(f"❌ Failed: {failed}")
    print(f"📝 Total processed: {successful + failed}")


if __name__ == "__main__":
    main()
