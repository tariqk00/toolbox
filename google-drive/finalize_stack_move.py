import os.path
import re
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, 'token_full_drive.json')
SCOPES = ['https://www.googleapis.com/auth/drive']
STACK_ID = '1HERen6HP4uDLMXV8Vj_cLOJ3xpT6QV2dLuBVm6z9i__is2Jmw0px2qPhy-72NrlsOhXyLB-Y'

BUCKETS = {
    '02 - Personal & ID': '1Ob6M7x7-D1jmTNAVu0zd7fE3h5dgFsBX',
    '03 - Finance': '1tKdysRukqbkzDuI1fomvSrYDhA3cr2mx',
    '04 - Health': '1yruR1fC4TAR4U-Irb48p7tIERCDgg_PI',
    '06 - Library': '1SHzgwpYJ8K1d9wGNHQPGP68zVIz13ymI',
    '07 - Archive': '1noldMPM1SfoOvj2qqcUFfjJiB3tI8wso'
}

# Refined Mapping from AI Audit Results
AI_MAPPING = {
    # 02 - Personal & ID
    r'Area code 631 - Aug 30, 2021': '02 - Personal & ID',
    r'DiTomasso AP World II': '02 - Personal & ID',
    r'Gallery Family Search!': '02 - Personal & ID',
    r'Dinner Houston': '02 - Personal & ID',
    r'Edenton Wifi': '02 - Personal & ID',
    r'Authorization Letter': '02 - Personal & ID',
    r'Summer Work': '02 - Personal & ID',
    r'Khan Academy': '02 - Personal & ID',
    
    # 03 - Finance
    r'Area code 631': '03 - Finance', # Tax statements
    r'Vehicle Maintenance': '03 - Finance',
    r'Property Tax': '03 - Finance',
    r'Gianini Landscaping': '03 - Finance',
    r'Gift Letter': '03 - Finance',
    r'Hatch - Hatch': '03 - Finance',
    r'SWPN - Jun 1, 2021': '03 - Finance',
    r'Agilent Technologies': '03 - Finance', # Stock certificate
    
    # 06 - Library
    r'Book Cover': '06 - Library',
    r'GL-iNet mini router': '06 - Library',
    r'Hayward Industries': '06 - Library',
    r'NETGEAR Nighthawk': '06 - Library',
    r'LG Appliances': '06 - Library',
    r'Ms. Carolyn\'s': '06 - Library',
    r'Hermanas Kitchen': '06 - Library',
    r'LG Microwave': '06 - Library',
    r'LI Firewood': '06 - Library', # Flyer
    r'TSIA Your Mess for More': '06 - Library', # Whitepaper
    r'Marriott VACATION CLUB': '06 - Library', # Offer/Reference
    
    # 07 - Archive
    r'ad546e3c-7581-4ed4-9a01-88a11bc4e92e.pdf': '07 - Archive',
    r'TSIAyourmessformore': '07 - Archive'
}

# Original Patterns from analyze_stack_patterns.py
PATTERN_DEFS = {
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

def categorize(name):
    # 1. Check AI mapping first (most specific)
    for pattern, cat in AI_MAPPING.items():
        if re.search(pattern, name, re.I):
            return cat
    
    # 2. Check original patterns
    for cat, patterns in PATTERN_DEFS.items():
        for p in patterns:
            if re.search(p, name, re.I):
                return cat
                
    return '07 - Archive' # Default to archive if totally unknown

def move_files(dry_run=True):
    service = get_service()
    results = service.files().list(
        q=f"'{STACK_ID}' in parents and trashed = false",
        fields="files(id, name)"
    ).execute()
    items = results.get('files', [])
    
    print(f"Found {len(items)} items to move.")
    
    for item in items:
        name = item['name']
        file_id = item['id']
        cat = categorize(name)
        target_id = BUCKETS.get(cat)
        
        if not target_id:
            print(f"ERROR: No target ID for category {cat}")
            continue
            
        if dry_run:
            print(f"[DRY RUN] Would move '{name}' to '{cat}' ({target_id})")
        else:
            print(f"Moving '{name}' to '{cat}'...")
            # Get current parents to remove
            file = service.files().get(fileId=file_id, fields='parents').execute()
            previous_parents = ",".join(file.get('parents', []))
            
            service.files().update(
                fileId=file_id,
                addParents=target_id,
                removeParents=previous_parents,
                fields='id, parents'
            ).execute()

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    
    if args.execute:
        print("\n--- EXECUTING ---")
        move_files(dry_run=False)
        print("\nDone.")
    else:
        print("--- DRY RUN ---")
        move_files(dry_run=True)
        print("\nRun with --execute to perform moves.")
