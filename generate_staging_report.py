
import csv
import os

CSV_PATH = 'sorter_dry_run.csv'

# Mapping based on folder_manifest.md and recent changes
CATEGORY_PATHS = {
    "PKM/Plaud": "My Drive / 01 - Second Brain / Plaud",
    "PKM/Plaud/Transcripts": "My Drive / 01 - Second Brain / Plaud / Transcripts",
    "PKM": "My Drive / 01 - Second Brain",
    "Work": "My Drive / 01 - Second Brain / Work",
    "Source_Material": "My Drive / 01 - Second Brain / Archive (AI Sources)",
    "Personal": "My Drive / 02 - Personal & ID",
    "Health": "My Drive / 04 - Health",
    "Finance": "My Drive / 03 - Finance",
    "Finance/Receipts": "My Drive / 03 - Finance / Receipts",
    "Finance/Taxes": "My Drive / 03 - Finance / Taxes",
    "Finance/Statements": "My Drive / 03 - Finance / Statements",
    "Finance/Invoices": "My Drive / 03 - Finance / Invoices",
    "Finance/Tracking": "My Drive / 03 - Finance / Tracking",
    "Finance/Paycheck": "My Drive / 03 - Finance / Paycheck",
    "Finance/Insurance": "My Drive / 03 - Finance / Insurance",
    "House": "My Drive / 02 - Personal & ID", # Mapped to same as Personal in config
    "Auto": "My Drive / 02 - Personal & ID",
    "Education": "My Drive / 02 - Personal & ID",
    "Library": "My Drive / 06 - Library",
    "Other": "My Drive / 99 - Other",
    "Staging": "My Drive / 00 - Staging"
}

print("| # | Original Name | Target Name | Category | Full Target Path |")
print("| :--- | :--- | :--- | :--- | :--- |")

if not os.path.exists(CSV_PATH):
    print("CSV not found.")
    exit()

with open(CSV_PATH, 'r') as f:
    reader = csv.DictReader(f)
    rows = list(reader)
    
    # Just show last 52 (current batch) if file is huge, but we cleared it.
    # So show all.
    
    for i, row in enumerate(rows, 1):
        original = row['original']
        # Truncate long names for display
        if len(original) > 30:
            original = original[:27] + "..."
            
        proposed = row['proposed']
        if len(proposed) > 30:
            proposed = proposed[:27] + "..."
            
        cat = row['category']
        path = CATEGORY_PATHS.get(cat, f"Unknown ({cat})")
        
        # If confidence is Low and staying in Staging (usually 'Other' or 'Staging' cat)
        # Note: 'Other' with Low confidence stays in Inbox/Staging in Inbox Mode.
        # But 'Other' with High confidence moves to 99 - Other.
        # The CSV has 'confidence'.
        conf = row['confidence']
        
        if conf != 'High':
            path = "My Drive / 00 - Staging (No Move)"
        elif cat == 'Other' and conf == 'Low': # Redundant check
            path = "My Drive / 00 - Staging (No Move)"
            
        print(f"| {i} | `{original}` | `{proposed}` | {cat} | `{path}` |")
