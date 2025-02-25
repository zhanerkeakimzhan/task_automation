import yaml
import os
import yaml
import csv
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd


def check_ted_policy(project_path):
    def check_yaml_file(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                # Читаем файл построчно, игнорируя строки с комментариями
                lines = file.readlines()
                content_without_comments = "\n".join([line for line in lines if not line.strip().startswith("#")])
                yaml.safe_load(content_without_comments)  # Пробуем загрузить YAML без комментариев
            print(f"Файл {file_path} корректен.")
        except yaml.YAMLError as e:
            print(f"Ошибка синтаксиса в файле {file_path}: {e}")
            exit(1)  # Завершаем программу с ошибкой


    def extract_intents_from_nlu(file_path):
        check_yaml_file(file_path)  # Проверяем файл на корректность
        with open(file_path, 'r', encoding='utf-8') as file:
            nlu_data = yaml.safe_load(file)
        intents_list = []
        for item in nlu_data.get('nlu', []):
            intent = item.get('intent')
            if intent is False:
                intents_list.append('no')
            elif intent is True:
                intents_list.append('yes')
            else:
                intents_list.append(intent)
        return intents_list

    def extract_utters_from_domain(file_path):
        check_yaml_file(file_path)  # Проверяем файл на корректность
        with open(file_path, 'r', encoding='utf-8') as file:
            domain_data = yaml.safe_load(file)
        utters_list = []
        for utter in domain_data.get('responses', {}).keys():
            if utter.startswith('utter_q') or utter.startswith('utter_getCSIRU') or utter.startswith('utter_getCSIKZ')  or utter.startswith('utter_scoreRU') or utter.startswith('utter_scoreKZ'):
                utters_list.append(utter)
        return utters_list


    def extract_intents_from_steps(steps):
        related_intents = []
        for step in steps:
            if 'intent' in step:
                if step['intent'] is False:
                    related_intents.append('no')
                elif step['intent'] is True:
                    related_intents.append('yes')
                else:
                    related_intents.append(step['intent'])
            elif 'or' in step:
                for sub_step in step['or']:
                    if 'intent' in sub_step:
                        if sub_step['intent'] is False:
                            related_intents.append('no')
                        elif sub_step['intent'] is True:
                            related_intents.append('yes')
                        else:
                            related_intents.append(sub_step['intent'])
        return related_intents


    def check_missing_intents_in_rules(rule_file_path, utters_list, intents_list):
        check_yaml_file(rule_file_path)  # Проверяем файл на корректность
        with open(rule_file_path, 'r', encoding='utf-8') as file:
            rule_data = yaml.safe_load(file)
        rules = rule_data.get('rules', [])
        missing_intents_for_utters = {}
        for utter in utters_list:
            related_intents = []
            for rule in rules:
                if 'steps' in rule:
                    for step in rule['steps']:
                        if 'action' in step and step['action'] == utter:
                            related_intents.extend(extract_intents_from_steps(rule['steps']))
            missing_intents = [intent for intent in intents_list if intent not in related_intents]
            if missing_intents:
                missing_intents_for_utters[utter] = missing_intents
        return missing_intents_for_utters


    def extract_intents_from_stories(stories_data):
        intents_in_stories = []
        for story in stories_data.get('stories', []):
            if 'steps' in story:
                # Используем extract_intents_from_steps для извлечения интентов, в том числе и внутри or
                intents_in_stories.extend(extract_intents_from_steps(story['steps']))
        return intents_in_stories


    def check_missing_intents_in_stories(stories_file_path, intents_list):
        check_yaml_file(stories_file_path)  # Проверяем файл на корректность
        with open(stories_file_path, 'r', encoding='utf-8') as file:
            stories_data = yaml.safe_load(file)
        
        # Извлекаем все интенты, использованные в stories
        intents_in_stories = extract_intents_from_stories(stories_data)
        
        # Ищем отсутствующие интенты
        missing_intents = [intent for intent in intents_list if intent not in intents_in_stories]
        
        return missing_intents

    response = []

    # Путь к файлам проекта
    nlu_file_path = os.path.join(project_path, 'data/nlu.yml')
    domain_file_path = os.path.join(project_path, 'domain.yml')
    rule_file_path = os.path.join(project_path, 'data/rules.yml')
    stories_file_path = os.path.join(project_path, 'data/stories.yml')
    # Извлекаем интенты и уттеры
    intents = extract_intents_from_nlu(nlu_file_path)
    utters = extract_utters_from_domain(domain_file_path)
    utters.extend([
        "utter_interruptingRU",
        "utter_interruptingKZ",
        "utter_repeat_questionRU",
        "utter_repeat_questionKZ"
    ])

    # Проверяем пропущенные интенты
    missing_intents_for_utters = check_missing_intents_in_rules(rule_file_path, utters, intents)
    missing_intents_in_stories =  check_missing_intents_in_stories(stories_file_path,intents)

    if missing_intents_for_utters:
        # print("Пропущенные интенты для следующих utters в rull:")
        response.append('Пропущенные интенты для следующих utters в rull:')
        for utter, missing in missing_intents_for_utters.items():
            # print(f"{utter}: {missing}")
            if missing[0] != None:
                response.append(f"{utter}: {missing}")
    else:
        response.append("Все интенты прописаны для каждого utter в rull.")



    if missing_intents_in_stories:
        response.append("Пропущенные интенты для следующих utters в stories:")
        for missing in missing_intents_in_stories:
            response.append(f"utter_q0: {missing}")
    else:
        response.append("Все интенты прописаны для каждого utter в stories.")
    
    return response


def parse_csv(project_path, sheet_name, file_name):
    print(f'file_path: {project_path}, sheet_name: {sheet_name}, file_name: {file_name}')
    # google connect
    SPREADSHEET_ID = "1cz9TYk75cRrWkrV44zOOpQbr-kmltqmsye4n5xBMwxs"
    SHEET_NAME = sheet_name #название таблицы
    JSON_KEY_FILE = "service_account.json"

    def load_google_sheets_data():
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
        return sheet.get_all_records()

    with open(f'{project_path}/domain.yml', 'r', encoding='utf-8') as file:
        domain_data = yaml.safe_load(file)

    gs_data = load_google_sheets_data()
    responses = domain_data.get('responses', {})
    csv_data = {}
    pattern = re.compile(r'\s*([\d.]+)\s*\|\s*(.*)')  # для извлечения Priority и Text

    for intent_name, intent_responses in domain_data.get('responses', {}).items():
        for response in intent_responses:
            if 'text' in response:
                text_value = response['text']
                match = pattern.match(text_value)
                if match:
                    priority = int(float(match.group(1)))
                    text = match.group(2).strip()

                    # Инициализация временных списков
                    temp_audio_ru_f = []
                    temp_audio_ru_m = []
                    temp_audio_kz_f = []
                    temp_audio_kz_m = []

                    for row in gs_data:
                        # Получаем тексты и аудио из Google Sheets
                        text_ru = row.get("текст на русском языке", "").strip()
                        text_kz = row.get("текст на казахском языке", "").strip()
                        audio_ru_f = row.get("AudioRU_F", "").strip()
                        audio_kz_f = row.get("AudioKZ_F", "").strip()
                        audio_ru_m = row.get("AudioRU_M", "").strip()
                        audio_kz_m = row.get("AudioKZ_M", "").strip()

                        # Обработка русского текста
                        if text == text_ru:
                            # Добавляем оригинальные RU аудио
                            if audio_ru_f and "_F_R" in audio_ru_f and audio_ru_f not in temp_audio_ru_f:
                                temp_audio_ru_f.append(audio_ru_f)
                                # Дублируем в KZ_F с заменой окончания
                                kz_f_audio = audio_ru_f.replace("_F_R", "_F_K")
                                if kz_f_audio not in temp_audio_kz_f:
                                    temp_audio_kz_f.append(kz_f_audio)

                            if audio_ru_m and "_M_R" in audio_ru_m and audio_ru_m not in temp_audio_ru_m:
                                temp_audio_ru_m.append(audio_ru_m)
                                # Дублируем в KZ_M с заменой окончания
                                kz_m_audio = audio_ru_m.replace("_M_R", "_M_K")
                                if kz_m_audio not in temp_audio_kz_m:
                                    temp_audio_kz_m.append(kz_m_audio)

                        # Обработка казахского текста
                        elif text == text_kz:
                            # Добавляем оригинальные KZ аудио
                            if audio_kz_f and "_F_K" in audio_kz_f and audio_kz_f not in temp_audio_kz_f:
                                temp_audio_kz_f.append(audio_kz_f)
                                # Дублируем в RU_F с заменой окончания
                                ru_f_audio = audio_kz_f.replace("_F_K", "_F_R")
                                if ru_f_audio not in temp_audio_ru_f:
                                    temp_audio_ru_f.append(ru_f_audio)

                            if audio_kz_m and "_M_K" in audio_kz_m and audio_kz_m not in temp_audio_kz_m:
                                temp_audio_kz_m.append(audio_kz_m)
                                # Дублируем в RU_M с заменой окончания
                                ru_m_audio = audio_kz_m.replace("_M_K", "_M_R")
                                if ru_m_audio not in temp_audio_ru_m:
                                    temp_audio_ru_m.append(ru_m_audio)

                    # Обновляем или создаем запись в csv_data
                    if intent_name in csv_data:
                        entry = csv_data[intent_name]
                        entry['Text'] += ' / ' + text
                        # Объединяем аудио списки
                        for field, values in [
                            ('AudioRU_F', temp_audio_ru_f),
                            ('AudioRU_M', temp_audio_ru_m),
                            ('AudioKZ_F', temp_audio_kz_f),
                            ('AudioKZ_M', temp_audio_kz_m)
                        ]:
                            existing = entry[field]
                            for item in values:
                                if item not in existing:
                                    existing.append(item)
                    else:
                        csv_data[intent_name] = {
                            'Priority': priority,
                            'NameIntent': intent_name,
                            'Text': text,
                            'AudioRU_F': temp_audio_ru_f.copy(),
                            'AudioRU_M': temp_audio_ru_m.copy(),
                            'AudioKZ_F': temp_audio_kz_f.copy(),
                            'AudioKZ_M': temp_audio_kz_m.copy(),
                            'Intents': '-',
                            'Next_audio': '',
                            'Duration_waiting': '',
                            'Finished': '',
                            'Language': "AudioRU" if intent_name.endswith("RU") else "AudioKZ" if intent_name.endswith("KZ") else "AudioRU",
                            'BadRU_M': '',
                            'BadKZ_M': '',
                            'BadRU_F': '',
                            'BadKZ_F': '',
                            'OtherRU_M': '',
                            'OtherKZ_M': '',
                            'OtherRU_F': '',
                            'OtherKZ_F': '',
                            'Interrupting_strategy': '',
                            'reload_template': 'no',
                            'repeat': '3',
                            'asr': 'default_kz'
                        }

    # Преобразование списков в строки
    csv_rows = list(csv_data.values())
    for entry in csv_rows:
        for field in ['AudioRU_F', 'AudioRU_M', 'AudioKZ_F', 'AudioKZ_M']:
            entry[field] = ', '.join(entry[field]) if entry[field] else '-'

    csv_rows = list(csv_data.values())
    csv_columns = [
        'Priority', 'NameIntent', 'Text', 'AudioRU_M', 'AudioKZ_M', 'AudioRU_F',
        'AudioKZ_F', 'Intents', 'Next_audio', 'Duration_waiting', 'Finished',
        'Language', 'BadRU_M', 'BadKZ_M', 'BadRU_F', 'BadKZ_F', 'OtherRU_M',
        'OtherKZ_M', 'OtherRU_F', 'OtherKZ_F', 'Interrupting_strategy',
        'reload_template', 'repeat', 'asr'
    ]
    # Словарь доп интентов для заполение столбца next_audio
    SPECIAL_NEXT_AUDIO = {"utter_scoreRU", "utter_scoreKZ", "utter_interruptingKZ", "utter_interruptingRU", "utter_justOperatorKZ", "utter_justOperatorRU"}

    # Словарь исключений
    EXCLUDED_INTENTS = {"utter_justOperatorRU", "utter_justOperatorKZ"}

    # Словарь доп интентов для заполнения столбца Finished
    FINISHED_INTENTS = {"utter_goodByeRU", "utter_goodByeKZ", "utter_error_stateRU", "utter_error_stateKZ"}

    # Словарь доп интентов для заполнения столбца Interrupting Strategy
    IS_INTENTS = {"utter_error_stateRU", "utter_error_stateKZ", "utter_repeat_questionRU", "utter_repeat_questionKZ"}

    # для получения последнего приоритета
    max_priority = max(entry['Priority'] for entry in csv_rows)

    for entry in csv_rows:
        # Для заполнения столбца next_audio
        if entry['Priority'] == 0:
            entry['Next_audio'] = max_priority
        elif 'q' in entry['NameIntent']:
            entry['Next_audio'] = max_priority
        elif entry['NameIntent'] in SPECIAL_NEXT_AUDIO:
            entry['Next_audio'] = max_priority
        else:
            entry['Next_audio'] = '-'
        # Для заполнения столбца Duration_waiting
        if entry['Next_audio'] == max_priority:
            entry['Duration_waiting'] = 6
        else:
            entry['Duration_waiting'] = 0
        # Меняем название операторов на !Oper
        if "operator" in entry['NameIntent'].lower() and entry['NameIntent'] not in EXCLUDED_INTENTS:
            entry['NameIntent'] = "!Oper"
        # Для заполнения столбца Finished
        if entry['NameIntent'] in FINISHED_INTENTS:
            entry['Finished'] = 'OK'
        else:
            entry['Finished'] = '-'
        # Для заполнения столбца Interrupting Strategy
        if entry['NameIntent'] == "!Oper":
            entry['Interrupting_strategy'] = "NoOp"
        elif entry['NameIntent'] in IS_INTENTS:
            entry['Interrupting_strategy'] = "NoOp"
        else:
            entry['Interrupting_strategy'] = "ASR"

    # Создание CSV
    with open(f'{project_path}/{file_name}.csv', 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
        writer.writeheader()
        writer.writerows(csv_rows)
        csv_file_path = f'{project_path}/{file_name}.csv'
    
    df = pd.DataFrame(csv_rows)
    df.to_excel(f'{project_path}/{file_name}.xlsx', index=False)
    excel_file_path = f'{project_path}/{file_name}.xlsx'

    return csv_file_path, excel_file_path