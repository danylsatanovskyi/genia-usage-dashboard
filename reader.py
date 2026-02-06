"""Service for Google Sheets integration"""

import gspread
from google.oauth2.service_account import Credentials
from config import GOOGLE_CREDS_FILE, GOOGLE_SPREADSHEET_NAME, SCOPES
import pandas as pd


def get_company_usage(sheet_name):
    """
    Get a Google Sheet worksheet by name
    
    Args:
        sheet_name: Name of the worksheet to retrieve
    
    Returns:
        gspread.Worksheet object
    """
    creds = Credentials.from_service_account_file(GOOGLE_CREDS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open(GOOGLE_SPREADSHEET_NAME)
    sheet = spreadsheet.worksheet(sheet_name)
    #print(sheet.get('K3:V5'))
    #print(sheet.get('C4:C6'))

    project_column = sheet.col_values(3)[3:]
    projects = []
    for l in project_column:
        if l != "":
            projects.append(l)
            continue
        break
    #print(projects)

    start_row = 4
    end_row = 4+len(projects)-1
    
    #cell_range = 'K4:V6'
    cell_range = 'K'+str(start_row)+':'+'V'+str(end_row)
    #print(range)

    numbers = sheet.get(cell_range)
    for i in range (len(projects)-len(numbers)):
        numbers.append([])
    #print(numbers)

    for ls in numbers:
        if len(ls) != 12:
            ls.extend([""]*(12-len(ls)))
        
    project_df = pd.DataFrame(numbers, columns = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'])
    project_df.insert(0, "Projects", projects)

    print (project_df)


companies = ['HEMA-QUEBEC', 'CELLCOM', 'SERIE CONSEIL', 'TECHO BLOC', 'DIGITAD', 'RETROMTL', 'CHEMTECH']

for company in companies:
    print(company)
    get_company_usage(company)

#get_google_sheet('SERIE CONSEIL')