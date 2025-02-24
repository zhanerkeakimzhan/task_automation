import yaml
import os


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
            response.append(f"intent: {missing}")
    else:
        response.append("Все интенты прописаны для каждого utter в stories.")
    
    return response