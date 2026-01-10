import os.path
import json
import re
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

TOKEN_PATH = '/home/takhan/github/tariqk00/toolbox/google-drive/token_full_drive.json'
SCOPES = ['https://www.googleapis.com/auth/drive']
STACK_ID = '1HERen6HP4uDLMXV8Vj_cLOJ3xpT6QV2dLuBVm6z9i__is2Jmw0px2qPhy-72NrlsOhXyLB-Y'

# Categorization Patterns
PATTERNS = {
    '02 - Personal & ID': [
        r'Identity', r'Passport', r'Driver', r'License', r'Social Security', r'Birth Certificate', 
        r'Marriage', r'Wedding', r'Sofia', r'Thomas', r'Tariq', r'Dawn', r'Transcript', r'School',
        r'Attorney', r'Power', r'Insurance - Auto', r'Volvo', r'Prius', r'Boat', r'House', r'Lease',
        r'DMV', r'Title', r'Registration', r'Lien', r'Abstract', r'Babylon', r'Pool', r'Backyard', 
        r'Fence', r'Fiano', r'LIDF', r'Recital', r'QX60', r'Toyota', r'Tesla', r'Infiniti', r'Recognition',
        r'Traffic', r'Violation', r'Podell', r'Suffolk', r'Merit', r'Naturalization', r'Abstract', r'ID'
    ],
    '03 - Finance': [
        r'Receipt', r'Bill', r'Invoice', r'Payment', r'Statement', r'Taxes', r'IRS', r'Internal Revenue',
        r'Notice', r'Penalty', r'Form \d+', r'1040', r'W2', r'Bank', r'Visa', r'Credit Card', r'UMB',
        r'Costco', r'Giannini', r'Aqua Wizards', r'Firestone', r'Payslip', r'Fidelity', r'Amex',
        r'EZPay', r'Equity', r'Payrazr', r'Lien Release', r'Merrill', r'Estimate', r'Confirmation',
        r'Order', r'InBody', r'HSA'
    ],
    '04 - Health': [
        r'Medical', r'Health', r'Insurance - Health', r'Doctor', r'Prescription', r'Pharmacy', 
        r'Anthem', r'UMB Bank \(HSA\)', r'Gastroenterologist', r'InBody', r'Eyewear',
        r'Dental', r'Hospital', r'Diagnostics', r'Langone', r'Surpris', r'LabCorp', r'Allergy',
        r'Vaccination', r'Vaccine', r'Covid', r'Test', r'Discharge', r'Nausheer', r'Dermatology'
    ],
    '06 - Library': [
        r'Manual', r'Guide', r'Instructions', r'Rules', r'Reference', r'Menu', r'Schedule', 
        r'Itinerary', r'Trip', r'Disney', r'Pickleball', r'Navionics', r'Garmin', r'Reading',
        r'Nest', r'Cam', r'Doorbell', r'Projector', r'Sharpener', r'Germany', r'Planning', 
        r'Activity', r'Hedge', r'Basket', r'Planting', r'Nordictrack', r'Wash', r'Dryer',
        r'Startup', r'Directions', r'Details', r'Warranty', r'Note', r'Note.pdf'
    ],
    '07 - Archive': [
        r'^\d+_.*_n\.jpg$', r'sandbox', r'temp'
    ]
}

def get_service():
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    return build('drive', 'v3', credentials=creds)

def categorize_name(name):
    for bucket, keywords in PATTERNS.items():
        for kw in keywords:
            if re.search(kw, name, re.IGNORECASE):
                return bucket
    return 'Uncategorized'

def audit_stack():
    service = get_service()
    
    results = []
    page_token = None
    
    print(f"Auditing items in Stack...")
    
    while True:
        response = service.files().list(
            q=f"'{STACK_ID}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType, size, createdTime)",
            pageSize=1000,
            pageToken=page_token
        ).execute()
        
        results.extend(response.get('files', []))
        page_token = response.get('nextPageToken')
        if not page_token:
            break

    print(f"Total items found: {len(results)}")
    
    analysis = {cat: [] for cat in PATTERNS.keys()}
    analysis['Uncategorized'] = []
    
    for item in results:
        category = categorize_name(item['name'])
        analysis[category].append(item['name'])
    
    # Save Report
    report_path = '/home/takhan/.gemini/antigravity/brain/96222b02-e59f-4ecf-8297-9128097dd857/stack_audit_report.json'
    with open(report_path, 'w') as f:
        json.dump(analysis, f, indent=2)
    
    print(f"Analysis saved to {report_path}")
    
    # Summary Table
    print("\n--- AUDIT SUMMARY ---")
    for cat, items in analysis.items():
        print(f"{cat}: {len(items)} items")

if __name__ == '__main__':
    audit_stack()
