import pandas as pd
from toolbox.bin.analyze_finances import normalize_dataframe

def test_normalize_chase():
    data = {
        'Transaction Date': ['12/31/2023'],
        'Post Date': ['01/01/2024'],
        'Description': ['TEST VENDOR'],
        'Category': ['Shopping'],
        'Type': ['Sale'],
        'Amount': ['-15.50'],
        'Memo': ['']
    }
    df = pd.DataFrame(data)
    norm = normalize_dataframe(df, 'Chase')
    
    assert not norm.empty
    assert 'Date' in norm.columns
    assert 'Amount' in norm.columns
    assert 'Category' in norm.columns
    assert norm.iloc[0]['Amount'] == 15.50  # Converted to positive spend
    assert norm.iloc[0]['Category'] == 'Shopping'

def test_normalize_amex():
    data = {
        'Date': ['12/31/2023'],
        'Description': ['AMEX VENDOR'],
        'Amount': ['25.00'],
        'Category': ['Dining']
    }
    df = pd.DataFrame(data)
    norm = normalize_dataframe(df, 'Amex')
    
    assert not norm.empty
    assert norm.iloc[0]['Amount'] == 25.00

def test_normalize_citi():
    data = {
        'Date': ['12/31/2023'],
        'Description': ['CITI VENDOR'],
        'Debit': ['35.00'],
        'Credit': ['']
    }
    df = pd.DataFrame(data)
    norm = normalize_dataframe(df, 'Citi')
    
    assert not norm.empty
    assert norm.iloc[0]['Amount'] == 35.00
