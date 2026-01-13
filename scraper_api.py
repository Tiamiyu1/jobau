import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import json
from datetime import datetime
import random

def clean_text(text):
    """Clean unwanted special characters and Unicode from text."""
    if not text:
        return None
    text = text.replace('\r', ' ').replace('\n', ' ').replace('\u2019', "'")
    text = re.sub(r'\s+', ' ', text)  # collapse multiple spaces
    return text.strip()

# --------------------------------------------
# CONFIGURATION
# --------------------------------------------
BASE_URL = "https://www.myjobmag.com"
TODAY_URL = f"{BASE_URL}/jobs-by-date/today"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# API Configuration - CHANGE THIS WHEN READY
API_BASE_URL = 'https://api.alumunite-staging.com'  # Staging
# API_BASE_URL = 'https://api.alumunite.co'  # Production
API_ENDPOINT = f"{API_BASE_URL}/v1/store-job-api"

# Test mode settings
TEST_MODE = False  # Set to False to actually push to API
MAX_JOBS_TO_SCRAPE = 2  # Limit jobs for testing (set to None for all jobs)

print(f"🔧 Configuration:")
print(f"   API: {API_ENDPOINT}")
print(f"   Test Mode: {TEST_MODE}")

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
        # break
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


    overview_section = soup.select_one(".job-description")
    # overview_text = None

    if overview_section:
        # Extract text directly inside the tag (excluding nested tags)
        text_nodes = [t for t in overview_section.contents if isinstance(t, str) and t.strip()]
        if text_nodes:
            overview_text = text_nodes[0].strip()
        else:
            # Fallback: look for the next <p> if text is inside it
            p = overview_section.find("p")
            if p:
                overview_text = p.get_text(strip=True)
    overview_text = clean_text(overview_text)

    # Find the industry section
    industry_section = soup.find("li", class_="job-industry")
    industry = None

    if industry_section:
        first_link = industry_section.find("a")
        if first_link:
            industry = first_link.get_text(strip=True)
            industry = industry.replace("View Jobs in", "").strip()
    industry = clean_text(industry)


    # Extract description
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
    description = clean_text(description)


    # Salary detection
    salary = None
    if 'salary' in details:
        salary = details['salary']

    return {
        "Title": title,
        "Company": company,
        "Industry": industry,
        "Overview": overview_text,
        "Experience": details.get("experience"),
        "Qualification": details.get("qualification"),
        "Job Type": details.get("job type"),
        "State": details.get("location"),
        "City": details.get("city"),
        "Salary": salary,
        "Field": details.get("job field"),
        "Posted on": details.get("posted_date"),
        "Deadline": details.get("deadline_date"),
        "Description": description,
        "Apply Now": application_method,
        "Original URL": job_url,
    }


# --------------------------------------------
# API INTEGRATION
# --------------------------------------------
def map_job_to_api_format(job):
    """Convert scraped job data to API format."""

    # Extract skills from description/requirements
    skills = []
    text_to_search = f"{job.get('Description', '')}"
    common_skills = ["Python", "JavaScript", "Java", "PHP", "Laravel", "React", "Node.js", "SQL", "MySQL", "PostgreSQL", "MongoDB", "AWS", "Azure", "Docker", "Git", "TypeScript", "Vue.js", "Angular", "Django", "Flask", "Excel", "analytical thinking", "problem-solving", "organizational skills", "Communication", "Collaboration", "Critical Thinking", "Adaptability", "Leadership", "Time Management", "Attention to Detail", "Negotiation", "Creativity", "Teamwork", "Active Listening", "Public Speaking", "Emotional Intelligence", "Go", "Golang", "Ruby on Rails", "C++", "C#", "Swift", "Kotlin", "HTML5", "CSS3", "Sass", "LESS", "jQuery", "Bootstrap", "Data Analysis", "Data Science", "Database Management", "Big Data Technologies", "Spark", "Hadoop", "Data Warehousing", "ETL", "Extract", "Transform", "Load", "Data Visualization", "Tableau", "Power BI", "Matplotlib", "Seaborn", "NoSQL Databases", "Cassandra", "Redis", "Google Cloud Platform", "GCP", "Version Control", "GitHub", "GitLab", "Bitbucket", "Kubernetes", "DevOps Principles", "CI/CD", "Continuous Integration", "Continuous Deployment", "Containerization", "Linux Command Line", "Unix Command Line", "Shell Scripting", "Bash", "Terraform", "Ansible", "Jenkins", "Jira", "Confluence", "Machine Learning", "Artificial Intelligence", "AI", "Natural Language Processing", "NLP", "Deep Learning", "TensorFlow", "PyTorch", "Keras", "Generative AI", "Computer Vision", "Reinforcement Learning", "API Development", "RESTful APIs", "GraphQL", "Cybersecurity", "Cloud Security", "Mobile Development", "iOS Development", "Android Development", "React Native", "Flutter", "UI/UX Design", "Figma", "Sketch", "Adobe XD", "Agile Methodologies", "Scrum", "Kanban", "Software Development Life Cycle", "SDLC", "Microsoft Office Suite", "Word", "PowerPoint", "Outlook", "Project Management", "PMP Certification", "CAPM Certification", "Business Intelligence", "BI", "Cloud Architecture", "Network Management", "Operating Systems", "Windows Server Management", "macOS Management", "Ubuntu Management", "Digital Marketing", "SEO", "Search Engine Optimization", "Content Creation", "Social Media Management", "Financial Literacy", "Budgeting", "Customer Relationship Management", "CRM", "Salesforce", "HubSpot", "Data Privacy", "Regulation", "GDPR", "CCPA", "Problem Framing", "Strategic Planning", "Process Improvement"]

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
        # "industry": job.get("Industry"),
        "overview": job.get("Overview") or job.get("Description"),
        "responsibilities": job.get("Description"),
        "url": job.get("Apply Now"),
        "expiration_date": expiration_date or "9999-01-01",
        "location": location,
        "job_type": job.get("Job Type"),
        "employment_type": "full-time",
        "experience_level": job.get("Experience") or "Not Available",
        "qualifications": job.get("Qualification"),
        "skills": skills[:5] if skills else ["General"],
        "currency": currency,
        "salary_range": salary_range or "Not Stated",
        "pay_schedule": "Monthly",
        "benefits": "Not specified"
    }



def push_job_to_api(job_data, test_mode=True):
    """Push a single job to the API."""
    try:
        api_payload = map_job_to_api_format(job_data)

        if test_mode:
            print(f"   🧪 TEST MODE - Would send:")
            print(f"      Title: {api_payload['title']}")
            print(f"      Company: {api_payload['company']}")
            print(f"      Location: {api_payload['location']}")
            print(f"      Job Type: {api_payload['job_type']}")
            return True, api_payload

        response = requests.post(
            API_ENDPOINT,
            json=api_payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        if response.status_code in [200, 201]:
            print(f"   ✅ Successfully posted: {job_data.get('Title')}")
            return True, api_payload
        else:
            print(f"   ❌ API Error ({response.status_code}): {job_data.get('Title')}")
            print(f"      Response: {response.text[:200]}")
            return False, api_payload

    except Exception as e:
        print(f"   ❌ Exception: {e}")
        return False, None


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
# FILTERING FUNCTIONS
# --------------------------------------------
def should_send_job(job_data, filters):
    """
    Determine if a job should be sent to the API based on filters.

    Args:
        job_data: Dictionary containing job details
        filters: Dictionary with filter criteria

    Returns:
        Tuple (should_send: bool, reason: str)
    """
    # Check required fields
    required_fields = filters.get('required_fields', [])
    for field in required_fields:
        value = job_data.get(field)
        if not value or (isinstance(value, str) and value.strip() == ""):
            return False, f"Missing required field: {field}"

    # Exclude email-based applications
    apply_url = (job_data.get('Apply Now') or "").lower()
    if apply_url.startswith("mailto:") or "@" in apply_url:
        return False, "Email-based application excluded"
        
    # Check industries/fields
    allowed_industries = filters.get('industries', [])

    if allowed_industries:
        # Normalize Field and Industry into a list of lowercase strings
        field_values = job_data.get('Field') or []
        industry_values = job_data.get('Industry') or []

        # Convert both to lowercase lists (handles string or list)
        def to_list(v):
            if isinstance(v, list):
                return [str(item).lower() for item in v]
            return [str(v).lower()] if v else []

        job_fields = to_list(field_values) + to_list(industry_values)

        # Check if any allowed industry appears in any job field
        if not any(ind.lower() in job_fields for ind in allowed_industries):
            return False, f"Industry not in allowed list: {job_fields}"


    # Check blocked industries
    blocked_industries = filters.get('blocked_industries', [])
    if blocked_industries:
        job_field = (job_data.get('Field') or "").lower()
        if any(blocked.lower() in job_field for blocked in blocked_industries):
            return False, f"Industry is blocked: {job_field}"

    # Check job types
    allowed_job_types = filters.get('job_types', [])
    if allowed_job_types:
        job_type = (job_data.get('Job Type') or "").lower()
        if not any(jt.lower() in job_type for jt in allowed_job_types):
            return False, f"Job type not allowed: {job_type}"

    # Check locations
    allowed_locations = filters.get('locations', [])
    if allowed_locations:
        city = (job_data.get('City') or "").lower()
        state = (job_data.get('State') or "").lower()
        location_text = f"{city} {state}"
        if not any(loc.lower() in location_text for loc in allowed_locations):
            return False, f"Location not in allowed list"

    # Check experience level
    min_experience = filters.get('min_experience')
    if min_experience:
        exp = (job_data.get('Experience') or "").lower()
        # Simple check for experience years
        if 'entry' in exp or 'junior' in exp:
            exp_years = 0
        elif 'senior' in exp:
            exp_years = 5
        elif 'mid' in exp:
            exp_years = 2
        else:
            exp_years = 0

        if exp_years < min_experience:
            return False, f"Experience level too low: {exp}"

    # Check if salary is specified (if required)
    if filters.get('require_salary', False):
        salary = job_data.get('Salary')
        if not salary or salary == "Not specified":
            return False, "Salary not specified"

    # All checks passed
    return True, "Passed all filters"


# --------------------------------------------
# MAIN SCRAPING WORKFLOW
# --------------------------------------------
def main():
    print(f"🚀 Starting job scraper...")
    print(f"📡 API Endpoint: {API_ENDPOINT}\n")

    # --------------------------------------------
    # FILTER CONFIGURATION
    # --------------------------------------------
    filters = {
        # Only send jobs with these required fields filled
        'required_fields': ['Company', 'Description', 'Apply Now'],

        # Only send jobs in these industries (leave empty [] to allow all)
        'industries': [
            'Telecommunication',
            'Technical',
            'Security / Intelligence',
            'ict / computer', 
            'ict / telecommunication',
            'Data, Business Analysis and AI',
            'Product Management',
            'Project Management'
            # Add more industries as needed
        ],

        # Block these industries (leave empty [] to block none)
        'blocked_industries': [
            # 'Sales',
            # 'Marketing',
        ],

        # Only send these job types (leave empty [] to allow all)
        'job_types': [
            # 'Remote',
            # 'Hybrid',
            # 'Full-time',
        ],

        # Only send jobs in these locations (leave empty [] to allow all)
        'locations': [
            # 'Lagos',
            # 'Abuja',
            # 'Port Harcourt',
        ],

        # Minimum experience required (0 = entry level, set to None to disable)
        'min_experience': None,

        # Only send jobs with salary specified
        'require_salary': False,
    }

    print("🔍 Active Filters:")
    if filters['required_fields']:
        print(f"   ✓ Required fields: {', '.join(filters['required_fields'])}")
    if filters['industries']:
        print(f"   ✓ Industries: {', '.join(filters['industries'])}")
    if filters['blocked_industries']:
        print(f"   ✗ Blocked industries: {', '.join(filters['blocked_industries'])}")
    if filters['job_types']:
        print(f"   ✓ Job types: {', '.join(filters['job_types'])}")
    if filters['locations']:
        print(f"   ✓ Locations: {', '.join(filters['locations'])}")
    if filters.get('require_salary'):
        print(f"   ✓ Salary required: Yes")
    print()

    # Step 1: Get today's job listings
    summary_jobs = get_today_jobs()

    if not summary_jobs:
        print("❌ No jobs found. Exiting.")
        return

    # Step 2: Fetch detailed info for ALL jobs first (without sending yet)
    qualified_jobs = []

    for i, job in enumerate(summary_jobs, start=1):
        print(f"\n🔍 Processing job {i}/{len(summary_jobs)}: {job['title']}")
        try:
            details = get_job_details(job["link"])

            # Run filters
            should_send, reason = should_send_job(details, filters)

            if should_send:
                qualified_jobs.append(details)
            else:
                print(f"   ⏭️  Skipped: {reason}")

            time.sleep(1.5)

        except Exception as e:
            print(f"   ❌ Error: {e}")

    # -------------------------------------------
    # ⚡ Randomly select ONLY 7 to send to API
    # -------------------------------------------
    print(f"\n🎉 {len(qualified_jobs)} jobs qualified after filter.")

    if len(qualified_jobs) > 7:
        selected_jobs = random.sample(qualified_jobs, 7)
    else:
        selected_jobs = qualified_jobs

    print(f"🚀 Sending {len(selected_jobs)} randomly selected jobs...\n")

    # Step 3: Push selected jobs to API
    successful = 0
    failed = 0

    for job_data in selected_jobs:
        if push_job_to_api(job_data):
            successful += 1
        else:
            failed += 1
        time.sleep(1)

    # Summary
    print(f"\n{'='*50}")
    print(f"📊 SCRAPING SUMMARY")
    print(f"{'='*50}")
    print(f"✅ Successfully posted: {successful}")
    print(f"❌ Failed: {failed}")
    print(f"📝 Total processed: {successful + failed}")

if __name__ == "__main__":
    main()
