from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os.path

# Определите область доступа к Google Sheets


def get_sheet_values(spreadsheet_id, range_name):
    print("get_sheet_values")
    """
    Функция для получения данных из Google Sheets.
    
    :param spreadsheet_id: ID Google таблицы.
    :param range_name: Диапазон данных, который нужно получить.
    :return: Список значений из таблицы.
    """
    # Получаем учетные данные из token.json
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    else:
        print("Файл token.json не найден.")
        return None
    
    # Подключаемся к Google Sheets API
    service = build('sheets', 'v4', credentials=creds)
    
    # Вызываем API и получаем данные
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
    values = result.get('values', [])
    
    return values

