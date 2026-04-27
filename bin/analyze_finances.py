#!/usr/bin/env python3
"""
Automated Spending Analysis
Ingests year-end CSVs from Amex, Chase, and Citi, categorizes spending, and generates
markdown reports for life-docs.
"""

import os
import glob
import pandas as pd
from datetime import datetime
from pathlib import Path

# Setup paths
TOOLBOX_ROOT = Path(__file__).resolve().parent.parent
FINANCE_INCOMING_DIR = TOOLBOX_ROOT / 'data' / 'finance' / 'incoming'
LIFE_DOCS_FINANCE_DIR = Path.home() / 'github' / 'tariqk00' / 'life-docs' / 'docs' / 'finance'

def normalize_dataframe(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Normalize the dataframe columns based on typical bank structures."""
    # Convert all columns to strings to safely apply str operations
    df.columns = df.columns.astype(str).str.strip().str.title()
    
    # Identify Date column
    date_col = None
    for col in ['Date', 'Transaction Date', 'Post Date', 'Posting Date']:
        if col in df.columns:
            date_col = col
            break
            
    # Identify Description column
    desc_col = None
    for col in ['Description', 'Payee', 'Title', 'Name']:
        if col in df.columns:
            desc_col = col
            break
            
    # Identify Amount column
    amt_col = None
    for col in ['Amount', 'Amount (Usd)', 'Debit', 'Credit']:
        if col in df.columns:
            amt_col = col
            break
            
    # Identify Category
    cat_col = None
    for col in ['Category', 'Type', 'Transaction Type']:
        if col in df.columns:
            cat_col = col
            break

    # If we couldn't find key columns, try heuristics or skip
    if not date_col or not desc_col or not amt_col:
        print(f"Warning: Could not normalize columns for {source}. Columns found: {df.columns.tolist()}")
        return pd.DataFrame()

    # Create normalized DataFrame
    norm_df = pd.DataFrame()
    norm_df['Date'] = pd.to_datetime(df[date_col], errors='coerce')
    norm_df['Description'] = df[desc_col]
    
    # Handle amount (some banks use Credit/Debit columns)
    if 'Debit' in df.columns and 'Credit' in df.columns:
        # Fill NaN with 0
        df['Debit'] = pd.to_numeric(df['Debit'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        df['Credit'] = pd.to_numeric(df['Credit'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        norm_df['Amount'] = df['Debit'] - df['Credit']  # Net spend (positive = spend)
    else:
        # Convert to numeric, removing commas
        norm_df['Amount'] = pd.to_numeric(df[amt_col].astype(str).str.replace(r'[$,]', '', regex=True), errors='coerce')
        # Some banks report spends as negative, some as positive. Assume mostly spends.
        # If the sum is negative, invert it.
        if norm_df['Amount'].sum() < 0:
            norm_df['Amount'] = norm_df['Amount'] * -1

    norm_df['Category'] = df[cat_col] if cat_col and cat_col in df.columns else 'Uncategorized'
    norm_df['Source'] = source
    
    # Drop rows with invalid dates or amounts
    norm_df = norm_df.dropna(subset=['Date', 'Amount'])
    
    return norm_df

def generate_markdown_report(df: pd.DataFrame, report_date: str) -> None:
    """Generate a markdown report in life-docs."""
    if df.empty:
        print("No data to generate report.")
        return
        
    LIFE_DOCS_FINANCE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Ensure Amount is float
    df['Amount'] = df['Amount'].astype(float)
    
    # Extract year and month for grouping
    df['YearMonth'] = df['Date'].dt.to_period('M')
    
    total_spend = df['Amount'].sum()
    
    # Group by category
    cat_summary = df.groupby('Category')['Amount'].sum().reset_index()
    cat_summary = cat_summary.sort_values('Amount', ascending=False)
    
    # Group by month
    monthly_summary = df.groupby('YearMonth')['Amount'].sum().reset_index()
    monthly_summary['YearMonth'] = monthly_summary['YearMonth'].astype(str)
    
    lines = [
        f"# Finance Report: {report_date}",
        "",
        f"**Total Spend:** ${total_spend:,.2f}",
        "",
        "## Spending by Category",
        "| Category | Amount |",
        "|----------|--------|"
    ]
    
    for _, row in cat_summary.iterrows():
        lines.append(f"| {row['Category']} | ${row['Amount']:,.2f} |")
        
    lines.extend([
        "",
        "## Monthly Trend",
        "| Month | Amount |",
        "|-------|--------|"
    ])
    
    for _, row in monthly_summary.iterrows():
        lines.append(f"| {row['YearMonth']} | ${row['Amount']:,.2f} |")
        
    lines.extend([
        "",
        "## Top 10 Transactions",
        "| Date | Description | Category | Source | Amount |",
        "|------|-------------|----------|--------|--------|"
    ])
    
    top_10 = df.sort_values('Amount', ascending=False).head(10)
    for _, row in top_10.iterrows():
        date_str = row['Date'].strftime('%Y-%m-%d')
        desc = str(row['Description'])[:40]
        cat = str(row['Category'])[:20]
        lines.append(f"| {date_str} | {desc} | {cat} | {row['Source']} | ${row['Amount']:,.2f} |")
        
    lines.append("")
    lines.append(f"_Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    
    out_path = LIFE_DOCS_FINANCE_DIR / f"{report_date}.md"
    out_path.write_text('\n'.join(lines))
    print(f"Generated report at {out_path}")

def main():
    csv_files = glob.glob(str(FINANCE_INCOMING_DIR / '*.csv'))
    if not csv_files:
        print(f"No CSV files found in {FINANCE_INCOMING_DIR}")
        return

    all_dfs = []
    for file_path in csv_files:
        filename = os.path.basename(file_path)
        print(f"Processing {filename}...")
        try:
            df = pd.read_csv(file_path)
            # Simple heuristic for source
            source = 'Unknown'
            fn_lower = filename.lower()
            if 'amex' in fn_lower:
                source = 'Amex'
            elif 'chase' in fn_lower:
                source = 'Chase'
            elif 'citi' in fn_lower:
                source = 'Citi'
            
            norm_df = normalize_dataframe(df, source)
            if not norm_df.empty:
                all_dfs.append(norm_df)
        except Exception as e:
            print(f"Error processing {filename}: {e}")

    if all_dfs:
        combined_df = pd.concat(all_dfs, ignore_index=True)
        # Use the current year as the report name, or 'Consolidated'
        report_name = datetime.now().strftime('Y%Y_Consolidated')
        generate_markdown_report(combined_df, report_name)
    else:
        print("No valid data extracted from CSVs.")

if __name__ == '__main__':
    main()
