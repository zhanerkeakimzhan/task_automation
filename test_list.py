import yaml
import os
import yaml
import csv
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from collections import OrderedDict

def collect_data_test_list(file_path, list_name):
    print('дернул collect_data_test_list')

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

            print('\n\n\n\n\n\n\n')
            print(items)  # Посмотрим, что там вообще
            print(type(items), items)  
            if items:
                print(type(items[0]), items[0])  # Посмотрим тип первого элемента
            print('\n\n\n\n\n\n\n')


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

        return items, missing_items

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
    
    print(excel_rows)
    return 'DEFUCK'


def write_data_test_list(file_path, list_name):
    print('дернул write_data_test_list')

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
