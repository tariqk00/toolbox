import csv
import os

CSV_FILE = 'sorter_dry_run.csv'
OUTPUT_FILE = 'dry_run_report.md'

def generate_report():
    if not os.path.exists(CSV_FILE):
        print("CSV file not found.")
        return

    with open(CSV_FILE, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    with open(OUTPUT_FILE, 'w') as f:
        f.write("# Dry Run Results\n\n")
        f.write(f"**Total Files Scanned:** {len(rows)}\n\n")
        f.write("| Original Name | Proposed Name | Category | Confidence |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        
        for row in rows:
            # Escape pipes if necessary
            orig = row['original'].replace('|', '\|')
            prop = row['proposed'].replace('|', '\|')
            cat = row['category']
            conf = row['confidence']
            f.write(f"| {orig} | {prop} | {cat} | {conf} |\n")
            
    print(f"Report generated: {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_report()
