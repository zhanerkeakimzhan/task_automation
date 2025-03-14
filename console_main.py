import os
import librosa
import zipfile
import shutil
import asyncio
from noise_reduction import reduce_noise_in_audio  # Импортируем функцию для удаления шума
from vad_segmentation import vad_segments_in_memory  # Импортируем функцию для сегментации
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from sheet_fetcher import get_sheet_values
from similarity import compare_texts_cosine
from ASR import transcribe_audio
from googleapiclient.discovery import build


# Директории для сохранения файлов
BASE_DIR = os.getcwd()
SAVE_DIR = 'audio_files'
PROCESSED_DIR = 'processed_audio_files'
SEGMENTS_DIR = 'segments_audio_files'

# Убедитесь, что директории для сохранения файлов существуют
for directory in [SAVE_DIR, PROCESSED_DIR, SEGMENTS_DIR]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# Глобальные переменные для Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Авторизация в Google Sheets
def google_sheets_auth():
    print("google_sheets_auth")
    print("Авторизация в Google Sheets...")
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

# Функция для очистки директории
def clear_directory(directory):
    print("clear_directory")
    if os.path.exists(directory):
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f'Не удалось удалить {file_path}. Причина: {e}')



def get_dynamic_range(creds, spreadsheet_id, sheet_name):
    print("Получаем динамический диапазон данных...")

    service = build('sheets', 'v4', credentials=creds)
    
    # Получаем данные о содержимом листа
    sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id, fields='sheets(data.rowData,properties.title)').execute()
    sheets = sheet_metadata.get('sheets', '')

    for sheet in sheets:
        if sheet['properties']['title'] == sheet_name:
            # Извлекаем строки с данными
            rows = sheet.get('data', [])[0].get('rowData', [])
            if not rows:
                print("Данных на листе нет.")
                return None

            # Определяем первую и последнюю строку и столбец с данными
            first_row, last_row = None, None
            first_column, last_column = None, None

            for i, row in enumerate(rows):
                values = row.get('values', [])
                if any(values):  # Если в строке есть данные
                    if first_row is None:
                        first_row = i + 1  # Устанавливаем первую строку
                    last_row = i + 1  # Обновляем последнюю строку

                    for j, cell in enumerate(values):
                        if cell.get('effectiveValue') is not None:  # Если в ячейке есть данные
                            if first_column is None or j + 1 < first_column:
                                first_column = j + 1  # Устанавливаем первый столбец
                            last_column = max(last_column or 0, j + 1)  # Обновляем последний столбец

            if first_row is None or last_row is None or first_column is None or last_column is None:
                print("Не удалось определить диапазон данных.")
                return None

            # Преобразуем индексы столбцов в буквы (например, 1 -> A, 3 -> C)
            first_column_letter = chr(64 + first_column)
            last_column_letter = chr(64 + last_column)

            range_notation = f"{sheet_name}!{first_column_letter}{first_row}:{last_column_letter}{last_row}"
            print(f"Найденный диапазон данных: {range_notation}")
            return range_notation
    
    print("Лист не найден.")
    return None

# Основная функция обработки аудиофайлов
async def process_audio_files(spreadsheet_id, range_name, original_filename, user_language):
    print("process_audio_files")
    print("Обработка аудиофайлов начата...")

    # Убираем шум из аудиофайла
    processed_filepath = reduce_noise_in_audio(original_filename, PROCESSED_DIR)

    # Сегментируем аудиофайл на основе VAD
    audio_data, sample_rate = librosa.load(processed_filepath, sr=8000)
    vad_segments_in_memory(audio_data, sample_rate, SEGMENTS_DIR)

    print("Файл обработан, шум удален и аудио разделено на части.")

    # Авторизуемся в Google Sheets и получаем данные
    creds = google_sheets_auth()
    try:
        sheet_values = get_sheet_values(spreadsheet_id, range_name)
        if not sheet_values:
            print("Данные не найдены или диапазон пуст.")
            return
        print("Данные успешно получены.")
    except Exception as e:
        print(f"Ошибка при получении данных из таблицы: {str(e)}")
        return

    # Проходим по каждому аудиофайлу в папке
    for audio_filename in os.listdir(SEGMENTS_DIR):
        audio_path = os.path.join(SEGMENTS_DIR, audio_filename)

        if not os.path.isfile(audio_path):
            continue

        # Распознаем текст из аудиофайла
        asr_text = await transcribe_audio(SEGMENTS_DIR, audio_filename)

        max_percentage = 0
        audio_name = ''
        audio_similarity_text = ''

        if user_language == 'RU':
            for row in sheet_values:
                similarity_percentage = compare_texts_cosine(asr_text, row[0])
                if similarity_percentage > max_percentage:
                    max_percentage = similarity_percentage
                    audio_similarity_text = row[0]
                    audio_name = row[2]
        elif user_language == 'KZ':
            for row in sheet_values:
                similarity_percentage = compare_texts_cosine(asr_text, row[1])
                if similarity_percentage > max_percentage:
                    max_percentage = similarity_percentage
                    audio_similarity_text = row[1]
                    audio_name = row[3]

        if audio_name:
            new_audio_name = audio_name if audio_name.endswith(".wav") else f"{audio_name}.wav"
            new_audio_path = os.path.join(SEGMENTS_DIR, new_audio_name)
            os.rename(audio_path, new_audio_path)
            print(f"Файл {audio_filename} переименован в {new_audio_name}")

        for row in sheet_values:
            if row[2] == audio_name:
                sheet_values.remove(row)
                print(f"Удалена строка с audio_name: {audio_name}")
                break  # Выход из цикла после удаления строки

    # Создаем ZIP-файл с архивированием всех файлов из папки
    zip_filename = f"{range_name}.zip"
    
    folder_path = os.path.dirname(original_filename)
    print(folder_path)
    
    zip_filepath = os.path.join(folder_path, zip_filename)

    with zipfile.ZipFile(zip_filepath, 'w') as zipf:
        for root, dirs, files in os.walk(SEGMENTS_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                if file != zip_filename:
                    zipf.write(file_path, os.path.relpath(file_path, SEGMENTS_DIR))

    print(f"ZIP-файл создан: {zip_filepath}")

    # Очищаем директории
    clear_directory(SAVE_DIR)
    clear_directory(PROCESSED_DIR)
    clear_directory(SEGMENTS_DIR)

    return True

# Главная функция, вызывающая обработку
def audio_processing(original_filename, user_language, sheet_name, spreadsheet_id="1cz9TYk75cRrWkrV44zOOpQbr-kmltqmsye4n5xBMwxs"):
    creds = google_sheets_auth()
    range_name = get_dynamic_range(creds, spreadsheet_id, sheet_name)
    
    if not range_name:
        print("Не удалось найти лист с таким именем.")
        return
    
    print(f"Автоматически определён диапазон: {range_name}")
    
    result = asyncio.run(process_audio_files(spreadsheet_id=spreadsheet_id, range_name=range_name, original_filename=original_filename, user_language=user_language))
    print(result)
    return result

# Пример вызова главной функции с передачей параметров
if __name__ == '__main__':
    original_filename = input("Введите путь к аудиофайлу WAV: ")
    user_language = input("Выберите язык (RU или KZ): ").upper()
    sheet_name = input("Теперь укажите имя листа: ")
    audio_processing(original_filename, user_language, sheet_name)
