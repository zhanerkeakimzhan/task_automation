import yaml
import os
import yaml
import csv
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from collections import OrderedDict


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


def prerecording_list(file_path, gender, default_text, sheet_name):
    if gender not in ['M', 'F']:
        raise ValueError("Пол должен быть 'M' или 'F'")
    #google connect
    gc = gspread.service_account(filename="service_account.json")
    SPREADSHEET_ID = "1cz9TYk75cRrWkrV44zOOpQbr-kmltqmsye4n5xBMwxs"
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)

    try:
        sheet = spreadsheet.worksheet(sheet_name)
        print("Лист уже существует, дайте другое название")
        return
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=sheet_name, rows="200", cols="5")

    with open(file_path, 'r', encoding='utf-8') as file:
        data = yaml.load(file, Loader=yaml.FullLoader)

    entries = OrderedDict()
    ordered_keys = []
    global_index = 1
    output = []

    # Обработка responses
    for key in data.get('responses', {}):
        if key.endswith('KZ'):
            continue

        base_key = key[:-2] if key.endswith('RU') else key

        cleaned_texts = [
            item['text'].split('|')[-1].strip()
            for item in data['responses'][key]
        ]

        if base_key not in ordered_keys:
            ordered_keys.append(base_key)

        entries[base_key] = cleaned_texts

    # Генерация таблицы
    for base_key in ordered_keys:
        for text in entries.get(base_key, []):
            audio_fields = (
                f"{global_index}_{default_text}_{gender}_R",
                f"{global_index}_{default_text}_{gender}_K"
            )
            output.append([base_key, text, '', *audio_fields])
            global_index += 1

        if re.match(r'^utter_q\d+$', base_key):
            audio_fields = (
                f"{global_index}_{default_text}_{gender}_R",
                f"{global_index}_{default_text}_{gender}_K"
            )
            output.append([f"{base_key}_BAD", '', '', *audio_fields])
            global_index += 1

    headers = [
        'название уттера',
        'текст на русском языке',
        'текст на казахском языке',
        f'AudioRU_{gender}',
        f'AudioKZ_{gender}'
    ]

    values = [headers] + output
    sheet.update(values=values, range_name=f"A1:E{len(values)}")

    return (f"Данные успешно записаны в лист '{sheet_name}'")


def check_test_list_name(sheet_name):
    print('Я ТУТ')
    print(sheet_name)
    gc = gspread.service_account(filename="service_account.json")
    SPREADSHEET_ID = "1fzp8Lpz506QeTG4l0iweo_sq_T2j8DXAGRE9p-rVICo"
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)

    # Получаем список всех листов
    sheets = spreadsheet.worksheets()
    sheet_names = [s.title for s in sheets]
    print(sheet_names)

    if sheet_name in sheet_names:
        print('лист существует')
        return True
    else:
        return False


def test_list(file_path, list_name):
    print('дернул test_list')

    def extract_intents_utters(file_path):
        '''
        логика предназначена для обработки Action
        сперва обращается в Actions.py
        начиает искать ActionAfterQN
        Дальше внутри ищет action_qN
        Если находится такое ищет словарь intents_utters
        Начинает парсить словарь, избавляется от f и начинает заменять lang на RU
        '''
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        class_pattern = re.compile(
            r"class\s+(ActionAfterQ\d+)\(Action\):\s*"
            r"(?:.|\n)*?def\s+name\(self\)\s*->\s*\w+:\s*"
            r"(?:.|\n)*?return\s+['\"](action_q\d+)['\"]",
            re.S
        )

        actions_intents_utters = {}

        # Функция для замены f-строк вида f'...{lang}'
        def replace_f_strings(match):
            return re.sub(
                r"f'([^']*)\{lang\}'",
                lambda m: f"'{m.group(1).replace('q', 'q')}RU'",  # Просто добавляем RU вместо {lang}
                match.group(1)
            )

        for class_match in class_pattern.finditer(content):
            class_name = class_match.group(1)
            action_name = class_match.group(2)

            class_body = content[
                        class_match.end():
                        content.find("class ", class_match.end())
                        ].strip()

            intents_pattern = re.compile(
                r"intents_utters\s*=\s*(\{(?:[^{}]*|\{(?:[^{}]*|\{[^{}]*\})*\})*\})",
                re.S
            )

            intents_match = intents_pattern.search(class_body)
            if not intents_match:
                continue

            try:
                # Заменяем f-строки перед парсингом
                dict_str = re.sub(
                    r"f'([^']*)\{lang\}'",
                    lambda m: f"'{m.group(1)}RU'",
                    intents_match.group(1)
                )

                dict_str = dict_str.replace("\n", "")
                intents_dict = ast.literal_eval(dict_str)
                actions_intents_utters[action_name] = intents_dict

            except Exception as e:
                print(f"Ошибка при обработке {class_name}: {e}")
                print(f"Проблемная строка: {dict_str}")

        return actions_intents_utters

    intents_utters = extract_intents_utters(f"{file_path}/actions/actions.py")

    # Обратный словарь для поиска интентов по utter'ам
    utter_to_intents = {}
    '''
    Логика для определения какой интент относиться к какому utter
    '''
    for intent, utters in intents_utters.items():
        for utter in utters:
            if utter not in utter_to_intents:
                utter_to_intents[utter] = []
            utter_to_intents[utter].append(intent)


    # Загрузка YAML-файлов
    with open(f"{file_path}/domain.yml", "r") as f:
        domain = yaml.safe_load(f)

    with open(f"{file_path}/data/rules.yml", "r") as f:
        rules = yaml.safe_load(f)

    with open(f"{file_path}/data/nlu.yml", "r") as f:
        nlu_data = yaml.safe_load(f)

    with open(f"{file_path}/data/stories.yml", "r") as f:
        stories = yaml.safe_load(f)

    # Создаем словарь responses
    responses = {}
    questions = {}
    missing_texts = {}
    for key, value in domain["responses"].items():
        texts = [t["text"].split("|")[-1].strip() for t in value]
        responses[key] = " / ".join(texts)
    
    # Словарь для заполнения дефолтных интентов
    ACTION_MAPPING = {
        "action_robot": "на робота",
        "action_operator": "на оператора",
        "action_repeat": "повтор",
        "utter_interruptingRU": "на посл. вопр",
        "nlu_fallback": "на выход",
        "utter_goodByeRU": "выход/CSI",
        "utter_getCSIRU": "выход/CSI",
        "action_another_operator": "на оператора"
    }

    missing_texts = {}
    missing_duplicate_key = []
    missing_items = {}  # Словарь для фронта

    # Обработка сторисов
    def process_stories(stories_data):
        """
        логика для обработки сторисов
        """
        stories_rows = []
        for story in stories_data.get("stories", []):
            steps = story.get("steps", [])

            root_action = "utter_hello_start"  # заменить на 0 вопрос

            main_question_text = responses.get(root_action)

            stories_rows.append({
                "intent": main_question_text,
                "question": "",
                "text": ""
            })

            items = process_steps(steps, root_action)

            for item in items:
                if item["question"] == "переспрос":
                    item["text"] = responses.get("utter_q1RU")

                stories_rows.append(item)

        return stories_rows

    def process_steps(steps, root_action):
        """
        Логика для обработки отдельных шагов рулов
        отдельная логика для обработки переспросов
        обработка рулов с OR
        замена True/False на Yes/No
        замена utter_qN на "на N вопрос"
        обработка и поиск след вопроса
        """
        seen_intents = set()
        items = []
        is_perespros = False
        special_actions = []
        intent_examples = {}
        intent_positions = []
        for step_idx, step in enumerate(steps):
            if "action" in step:
                action = step["action"]
                if action == "action_counterRU":
                    is_perespros = True
                elif action in ACTION_MAPPING:
                    special_actions.append(ACTION_MAPPING[action])
                elif action.startswith("action_q"):
                    if action in intents_utters:
                        for intent, utters in intents_utters[action].items():
                            intent_positions.append((intent, step_idx))
            if "or" in step:
                for item in step["or"]:
                    if isinstance(item, dict) and "intent" in item:
                        intent = str(item["intent"])
                        intent_positions.append((intent, step_idx))
            elif "intent" in step:
                intent = str(step["intent"])
                intent_positions.append((intent, step_idx))

        for intent, pos in intent_positions:
            if intent is True or intent == "True":
                intent = "yes"
            elif intent is False or intent == "False":
                intent = "no"

            if intent in seen_intents:
                continue
            seen_intents.add(intent)

            example = intent_examples.get(intent, intent)
            display_intent = f"{example} ({intent})" if example != intent else intent

            action_texts = []
            actions_list = []
            next_question = ""
            linked_actions = []
            for step in steps[pos + 1:]:
                if "action" in step:
                    action = step["action"]
                    linked_actions.append(action)
                    if action.startswith("utter_q"):
                        q_num = re.findall(r"q(\d+)", action)[0]
                        next_question = f"на {q_num} вопрос"
                        if action in responses:
                            action_texts.append(responses[action])
                        break

                    elif action in responses:
                        action_texts.append(responses[action])

                    elif action in ACTION_MAPPING:
                        next_question = ACTION_MAPPING[action]
                        break

                    elif action.startswith("action_"):
                        try:
                            action_dic = intents_utters[action]
                            utters = action_dic[intent]
                            for i in utters:
                                action_texts.append(responses[i])
                            q_num = re.findall(r"q(\d+)", utters[-1])[0]
                            next_question = f"на {q_num} вопрос"
                        except:
                            actions_list.append(action)

            question_type = ""
            if is_perespros:
                question_type = "переспрос"
                action_texts = [responses[root_action]]
            elif special_actions:
                question_type = ", ".join(special_actions)
            elif next_question:
                question_type = next_question
            elif actions_list:
                question_type = ", ".join(actions_list)

            text = ". ".join(filter(None, action_texts))

            # логика для ввода с консоли
            """
            начало логики для ввода с консооли
            если не находятся данные в action, идет ввод с консоли
            """
            if not text and actions_list:
                duplicate_key = f"{root_action}:{intent}:{','.join(actions_list)}"
                if duplicate_key in missing_texts:
                    saved_data = missing_texts[duplicate_key]
                    text = saved_data['text']
                    question_type = saved_data['question_type']
                else:
                    missing_duplicate_key.append(duplicate_key)
                    missing_items[duplicate_key] = {"intent": intent, "question": "", "text": ""}  # Пустые значения
                    
                    # для поля question
                    # print(f"\nВопрос: {root_action} | Интент: {display_intent}")
                    # print("1 - Переспрос")
                    # print("2 - Указать номер вопроса")
                    # print("3 - Ввести текст для поля question вручную")
                    # choice = input("Выберите вариант для поля question (1-3): ").strip()

                    # if choice == "1":
                    #     question_type = "переспрос"
                    #     if root_action in responses:
                    #         text = responses[root_action]
                    #     else:
                    #         text = ""
                    # elif choice == "2":
                    #     q_num = input("Введите номер вопроса (например, 2): ").strip()
                    #     question_type = f"на {q_num} вопрос"
                    # elif choice == "3":
                    #     question_type = input("Введите текст для поля question вручную: ").strip()
                    # else:
                    #     question_type = ""

                    # # для поля text
                    # if choice != "1" or not text:
                    #     print("\nТеперь заполним поле text.")
                    #     print("1 - Ввести utter")
                    #     print("2 - Ввести текст вручную")
                    #     text_choice = input("Выберите вариант для поля text (1-2): ").strip()

                    #     if text_choice == "1":
                    #         while True:
                    #             utter_names = input(
                    #                 "Введите utter через запятую (например, utter_q5RU, utter_q6RU): ").strip()
                    #             utter_list = [name.strip() for name in utter_names.split(", ")]
                    #             texts = []
                    #             for utter_name in utter_list:
                    #                 if utter_name in responses:
                    #                     texts.append(responses[utter_name])
                    #                 else:
                    #                     print(f"Utter '{utter_name}' не найден в domain")
                    #             if texts:
                    #                 text = ", ".join(texts)
                    #                 break
                    #             else:
                    #                 print("Ни один из введенных utter не найден. Попробуйте еще раз.")
                    #     elif text_choice == "2":
                    #         text = input("Введите текст для поля text вручную: ").strip()
                    #     else:
                    #         text = ""

                    # missing_texts[duplicate_key] = {
                    #     'text': text,
                    #     'question_type': question_type
                    # }
            items.append({
                "intent": display_intent,
                "question": question_type,
                "text": text
            })

        return items

    # Обработка intents_utters
    excel_rows = []

    # Обработка stories
    stories_rows = process_stories(stories)
    excel_rows.extend(stories_rows)

    # тут кажется то что вытащили из экшнов добавляем в excel_rows
    for intent, utters in intents_utters.items():
        for utter in utters:
            if utter in responses:
                # Извлекаем номер вопроса из utter (например, utter_q4RU → 4)
                question_number = re.findall(r"q(\d+)", utter)
                if question_number:
                    question_number = question_number[0]
                else:
                    question_number = "?"

                # Формируем строку для таблицы
                excel_rows.append({
                    "intent": intent,
                    "question": f"на {question_number} вопрос",
                    "text": responses[utter]
                })

    # Обработка rules
    for rule in rules["rules"]:
        steps = rule.get("steps", [])
        root_action = None

        for step in steps:
            if "action" in step:
                action = step["action"]
                if action.startswith("utter_q") and action.endswith("RU"):
                    root_action = action
                    break

        if root_action and root_action in responses:
            if root_action not in questions:
                questions[root_action] = {
                    "text": f'{root_action[7:-2]}. {responses[root_action]}',
                    "items": []
                }

            new_items = process_steps(steps, root_action)

            existing_intents = {item["intent"] for item in questions[root_action]["items"]}
            for item in new_items:
                if item["intent"] not in existing_intents:
                    questions[root_action]["items"].append(item)
                    existing_intents.add(item["intent"])

        elif root_action and root_action not in questions:
            questions[root_action] = {
                "text": f'{root_action[7:-2]}. {responses[root_action]}',
                "items": []
            }

            new_items = process_steps(steps, root_action)

    # Добавляем данные из questions в excel_rows
    for q_name, q_data in questions.items():
        excel_rows.append({"intent": q_data["text"], "question": "", "text": ""})
        for item in q_data["items"]:
            excel_rows.append({
                "intent": item["intent"],
                "question": item["question"],
                "text": item["text"]
            })
    
    
    #запись в таблицу
    gc = gspread.service_account(filename="service_account.json")
    SPREADSHEET_ID = "1fzp8Lpz506QeTG4l0iweo_sq_T2j8DXAGRE9p-rVICo"
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)

    sheet_name = list_name #name

    # Проверяем, существует ли лист
    try:
        existing_sheet = spreadsheet.worksheet(sheet_name)
        spreadsheet.del_worksheet(existing_sheet)  # Удаляем лист, если найден
        print(f"Лист {sheet_name} существовал и был удален.")
    except gspread.exceptions.WorksheetNotFound:
        print(f"Лист {sheet_name} не найден. Создаём новый.")

    sheet = spreadsheet.add_worksheet(title=sheet_name, rows="1000", cols="26")
    excel_rows = []

    main_question = None
    for q_name in questions:
        if "utter_hello_start" in q_name.lower():  # Ищем по ключевым словам
            main_question = q_name
            break

    sorted_questions = sorted(
        questions.items(),
        key=lambda x: (
        x[0] != main_question, int(re.findall(r"q(\d+)", x[0])[0]) if "q" in x[0] else (x[0] != main_question, 0))
    )

    for q_name, q_data in sorted_questions:
        excel_rows.append([q_data["text"], "", ""])  # Вопрос
        for item in q_data["items"]:
            excel_rows.append([item["intent"], item["question"], item["text"]])  # Данные

    # Добавляем данные из stories в excel_rows
    story_data = [
        [story_row["intent"], story_row["question"], story_row["text"]]
        for story_row in stories_rows
    ]
    excel_rows = story_data + excel_rows
    sheet.append_rows(excel_rows)

    # Окрашивание вопросов в цвет
    requests = []
    for i, row in enumerate(excel_rows, start=1):
        if row[1] == "" and row[2] == "":
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet.id,
                        "startRowIndex": i - 1, "endRowIndex": i,
                        "startColumnIndex": 0, "endColumnIndex": 3  # Красим первые 3 колонки
                    },
                    "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.917, "green": 0.69, "blue": 0.737}}},
                    "fields": "userEnteredFormat.backgroundColor"
                }
            })

    # Задаем ширину столбцов
    requests.append({
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet.id,
                "dimension": "COLUMNS",
                "startIndex": 0, "endIndex": 3  # Первые 3 колонки
            },
            "properties": {"pixelSize": 200},  # Ширина 200px
            "fields": "pixelSize"
        }
    })

    # запрос
    spreadsheet.batch_update({"requests": requests})
    print(f"Лист {sheet_name} создан, данные записаны и отформатированы.")

    return (f"Лист {sheet_name} создан, данные записаны и отформатированы.")

    # return 'FUCKING TEST LIST, I HATE YOU!!!'