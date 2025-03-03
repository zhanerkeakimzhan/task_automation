import random
from typing import Any, Text, Dict, List
import pandas as pd
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
import requests
from rasa_sdk.events import ActionExecuted, SlotSet, ActiveLoop, FollowupAction, Restarted, ConversationPaused, ConversationResumed
from actions.test_api_identification import get_dossier_info, get_antifraud, get_digital_code, get_keyword, update_activity, post_verint
from datetime import datetime
import redis
import json
import yaml
import os
import time
import pytz
import logging
import re


ENVIORENMENT = os.environ.get('ENVIORENMENT', 'dev')

if ENVIORENMENT == 'PROD':
    config_file = 'endpoints_prod.yml'
    with open(f'/rasa/{config_file}') as file:
         config_file = yaml.full_load(file)
    redis_ip = config_file['engine_redis']['url']
    redis_port = config_file['engine_redis']['port']
    redis_db_number = config_file['engine_redis']['db']
    redis_password = config_file['engine_redis']['pass']
else:
    redis_ip = '172.16.55.15'
    redis_password = 'eg_redis_pass'
    redis_port = 6379
    redis_db_number = 0

engine_redis = redis.Redis(host=redis_ip, port=redis_port, db=redis_db_number, password=redis_password)
default_path_csv = '/mnt/nfs_share/nlu_models'


def create_logger(tracker):
    uuid = tracker.current_state()['sender_id']
    dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))
    record_created = dict_to_redis['record_created']

    astana_tz = pytz.timezone('Asia/Qyzylorda')

    date_log = datetime.fromtimestamp(record_created, tz=pytz.utc).astimezone(astana_tz)
    conversation_parent_log_directory = '/mnt/nfs_share/rasa_logs/halyk_bank_identification/'

    logger = logging.getLogger(uuid)
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    # Устанавливаем часовой пояс для asctime
    logging.Formatter.converter = lambda *args: datetime.now(tz=astana_tz).timetuple()

    # log_folder = f'{conversation_parent_log_directory}{name_script}/{date_log.year}/{date_log.month}/{date_log.day}/{date_log.hour}'
    log_folder = f'{conversation_parent_log_directory}{date_log.year}/{date_log.month}/{date_log.day}/{date_log.hour}'
    log_path = f'{log_folder}/{uuid}.log'

    if not os.path.exists(log_folder):
        os.makedirs(log_folder, exist_ok=True)

    if os.path.exists(log_path):
        with open(log_path, 'a', encoding='utf-8') as log_file:
            log_file.write('\n')
            
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setFormatter(formatter)

    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler) and handler.baseFilename == log_path:
            return logger, file_handler

    logger.addHandler(file_handler)
    return logger, file_handler

def changeCSV(priority, lang, code1, code2, code3, tracker):
    print('Заходим в changeCSV')

    uuid = tracker.current_state()['sender_id']
    
    external_audio_key = f'{uuid}_external_audio_source_{priority}'

    # тут нужно будет менять путь к своему папке аудио
    if lang == 'RU':
        audio_list = [f'/mnt/nfs_share/audio_storage/response_sound/halyk_bank_identification/14_halyk_identification_M_R', 
                    f'/mnt/nfs_share/audio_storage/card_numbers/{code1}_halyk_M_R', 
                    f'/mnt/nfs_share/audio_storage/card_numbers/{code2}_halyk_M_R',
                    f'/mnt/nfs_share/audio_storage/card_numbers/{code3}_halyk_M_R',
                    f'/mnt/nfs_share/audio_storage/response_sound/halyk_bank_identification/15_halyk_identification_M_R']
    elif lang == 'KZ':
        audio_list = [f'/mnt/nfs_share/audio_storage/response_sound/halyk_bank_identification/14_halyk_identification_M_K', 
                    f'/mnt/nfs_share/audio_storage/card_numbers/{code1}_halyk_M_K', 
                    f'/mnt/nfs_share/audio_storage/card_numbers/{code2}_halyk_M_K', 
                    f'/mnt/nfs_share/audio_storage/card_numbers/{code3}_halyk_M_K', 
                    f'/mnt/nfs_share/audio_storage/response_sound/halyk_bank_identification/15_halyk_identification_M_K']
    else:
        print('Язык не задан')
    
    call_content = {'external_audio_list': audio_list}

    engine_redis.set(external_audio_key, json.dumps(call_content))
    
    print('Выходим из changeCSV')
    return []

def prepare_dialog(language, default_path_csv, audiopath):
    for_random = -1
    data = pd.read_csv(default_path_csv, sep=';')
    for l in ['RU', 'KZ']:
        for g in ['M', 'F']:
            domen = 'Audio{}_{}'.format(l, g)
            baddomen = 'Bad{}_{}'.format(l, g)
            otherdomen = 'Other{}_{}'.format(l, g)
            # agi.verbose(len(data[domen]))
            for i in range(len(data[domen])):
                if '{' in data.loc[i, 'NameIntent']:
                    if data.loc[i, 'NameIntent'][1:-1] == 'name_robot':
                        all_utters = data.loc[i, domen]
                        if all_utters != '-':
                            utters = all_utters.split(', ')
                            if for_random == -1:
                                for_random = random.randint(0, len(utters) - 1)
                                data.loc[i, domen] = audiopath + '/' + utters[for_random]
                            else:
                                data.loc[i, domen] = audiopath + '/' + utters[for_random]
                else:
                    fullpath = ''
                    if data[domen][i] != '-':
                        for audioname in data[domen][i].split(', '):
                            fullpath += f'{audiopath}/{audioname}, '
                        data.loc[i, domen] = fullpath[:-2]
                        # data[domen][i] = fullpath[:-2]
            try:
                for bdi in range(len(data[baddomen])):
                    if '$' not in data[baddomen][bdi] and data[baddomen][bdi] != '-':
                        fullpath = ''
                        for k in data[baddomen][bdi].split(', '):
                            fullpath += f'{audiopath}/{k}, '
                        data.loc[bdi, baddomen] = fullpath[:-2]
                        # data[baddomen][bdi] = fullpath[:-2]
                for odi in range(len(data[otherdomen])):
                    if '$' not in data[otherdomen][odi] and data[otherdomen][odi] != '-':
                        fullpath = ''
                        for k in data[otherdomen][odi].split(', '):
                            fullpath += f'{audiopath}/{k}, '
                        data.loc[odi, otherdomen] = fullpath[:-2]
                        # data[otherdomen][odi] = fullpath[:-2]
            except Exception as err:
                print('Exception')
                # agi.verbose(str(err))
    data.loc[0, 'Language'] = f'Audio{language}'
    return data

def check_csv_for_empty_values(file_path):
    try:
        data = pd.read_csv(file_path, delimiter=';', keep_default_na=False)  # keep_default_na=False для обработки пустых ячеек как строк
    except Exception as e:
        print(f'Ошибка при загрузке файла: {e}')
        return

    empty_columns = {}

    for column in data.columns:
        empty_priorities = data[data[column] == '']['Priority'].tolist()
        if empty_priorities:
            empty_columns[column] = empty_priorities
    
    return empty_columns

def get_all_utters(events: List[Dict[Text, Any]]) -> List[Text]:
    all_utters = []
    for event in events:
        if event['event'] == 'action' and event['name'].startswith('utter_'):
            all_utters.append(event['name'])
    return all_utters

def get_counter_intent(intent, events: List[Dict[Text, Any]]) -> List[Text]:
    counter = 0
    for event in events:
        if event['event'] == 'user':
            event['parse_data']['intent']['name'] = intent
            counter += 1
    return counter

def get_all_intents(events: List[Dict[Text, Any]]) -> List[Text]:
    all_intents = []
    for event in events:
        if event['event'] == 'user':
            all_intents.append(event['parse_data']['intent']['name'])
    return all_intents

def get_utters_between_two_intents(events: List[Dict[Text, Any]]) -> List[Text]:
    responses = []
    user_event_encountered = False
    for event in reversed(events):
        if event['event'] == 'user' and user_event_encountered:
            break
        elif event['event'] == 'user':
            user_event_encountered = True
        elif user_event_encountered and event['event'] == 'action' and event['name'].startswith('utter'):
            responses.append(event['name'])
    return responses

def get_audio_path_ammount(lang, ammount):
    text = str(int(ammount))
    int_amount = int(ammount)
    low_lang = lang.lower()
    g = 'M'
    name_audio = f'male_{low_lang}_{text}'
    
    print('Сумма:', int_amount)

    if int_amount >= 1_000_000:
        million = int_amount // 1_000_000 * 1_000_000
        tys = int_amount % 1_000_000
        folder_tys = tys // 100_000 + 1
        name_audio_tys = f'male_{low_lang}_{tys}'
        full_path_ammount = [f'/mnt/nfs_share/audio_storage/numbers/yerbolat/millions/male_{low_lang}/{million}',
                            f'/mnt/nfs_share/audio_storage/numbers/yerbolat/{lang}_{g}/audio_gen{folder_tys}/{name_audio_tys}']
    else:
        folder = 1+int(ammount)//100000
        full_path_ammount = [f'/mnt/nfs_share/audio_storage/numbers/yerbolat/{lang}_{g}/audio_gen{folder}/{name_audio}']

    print('output_audio_path:', full_path_ammount)

    return full_path_ammount

def send_external_audio_summa_q14(priority, lang, summa, currency, tracker):
    print('Заходим в send_external_audio_summa_q14')
    uuid = tracker.current_state()['sender_id']

    external_audio_key = f'{uuid}_external_audio_source_{priority}'

    language = lang[0]
    full_path_ammount = get_audio_path_ammount(lang, summa)
    audio_list = [f'/mnt/nfs_share/audio_storage/response_sound/halyk_bank_identification/68_halyk_identification_M_{language}', 
                *full_path_ammount, 
                f'/mnt/nfs_share/audio_storage/response_sound/halyk_bank_identification/{currency}_M_{language}',
                f'/mnt/nfs_share/audio_storage/response_sound/halyk_bank_identification/69_halyk_identification_M_{language}',]

    print('audio_list', audio_list)
    
    call_content = {'external_audio_list': audio_list}

    engine_redis.set(external_audio_key, json.dumps(call_content))

    print('Выходим из send_external_audio_summa_q14')
    return []

def send_external_audio_summa_q15(priority, lang, summa, currency, address, tracker):
    print('Заходим в send_external_audio_summa_q15')
    uuid = tracker.current_state()['sender_id']

    external_audio_key = f'{uuid}_external_audio_source_{priority}'

    if lang == 'RU' and currency == 'USD':
        last_number_currency = int(str(int(summa))[-1])
        if summa in [11,12,13,14] or last_number_currency in [5,6,7,8,9,0]:
            currency = 'USD_dollarov'
        elif last_number_currency in [2,3,4]:
            currency = 'USD_dollara'
        else:
            currency = 'USD'

    language = lang[0]
    full_path_ammount = get_audio_path_ammount(lang, summa)
    audio_list = [f'/mnt/nfs_share/audio_storage/response_sound/halyk_bank_identification/64_halyk_identification_M_{language}', 
                *full_path_ammount, 
                f'/mnt/nfs_share/audio_storage/response_sound/halyk_bank_identification/{currency}_M_{language}',
                f'/mnt/nfs_share/audio_storage/cities/{address}_M_{language}',
                f'/mnt/nfs_share/audio_storage/response_sound/halyk_bank_identification/65_halyk_identification_M_{language}',]

    print('audio_list', audio_list)
    
    call_content = {'external_audio_list': audio_list}

    engine_redis.set(external_audio_key, json.dumps(call_content))

    print('Выходим из send_external_audio_summa_q15')
    return []

def get_last_utter_and_lang(tracker) -> str:
    events = tracker.events
    all_utters = get_all_utters(events)

    uuid = tracker.current_state()['sender_id']
    dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

    f_lang = dict_to_redis['f_language']

    if f_lang and f_lang[-1] != '': 
        lang = f_lang[-1].upper()
    elif all_utters:
        last_utter = all_utters[-1] 
        lang = last_utter[-2:] 
    else: 
        lang = dict_to_redis['language'].upper()
    
    if all_utters:
        last_utter = all_utters[-1] 
    else:
        last_utter = f"utter_q1{lang}"

    return lang, last_utter

def check_intent(last_intent, tracker):
    logger, log_handler = create_logger(tracker)
    user_text = tracker.latest_message.get("text")
    nlu_url = f"http://halyk_bank_{last_intent}:5012/model/parse"
    print(f"Отправляю в NLU: {user_text}")

    try:
        response = requests.post(nlu_url, json={"text": user_text}, timeout=3)
        response.raise_for_status()
        
        internal_intent = response.json().get("intent", {}).get("name", "unknown_intent")
        print(f"Определён интент: {internal_intent}")
        need_ident_or_not = {
            'overdue_debt':  ['noReceipt', 'checkingTheAmount', 'monthlyPayment', 'debt', 'earlyRepayment', 'remainingDebt'],
            'super_app': ['publicServices'],
            'credit_card': ['smsWithOverdue', 'amountTotalDebt', 'howMuchNeedPay'],
            'forgot_card': ['whenBackCard', 'longCollectionATM', 'howGetMoneyWithoutCard', 'cardNotDelivery15Day'],
            'card_delivery' : ['card_not_displayed_in_app', 'card_issue_rejection_reason'],
            'reset_pin' : ['setPinCard', 'epinNotReceived'],
            'sysn' : ['cardDetails'],
            'card_operation': ['card_balance'],
        }

        need_ident = False

        for k, v in need_ident_or_not.items():
            if last_intent == k:
                if internal_intent in v:
                    need_ident = True
        
    except Exception as e:
        response = None
        internal_intent = e
        need_ident = True #если не получиться вытащить интент, пройдет идентификацию
    
    log_message = f'Отправил запрос на: {last_intent} \n\t\t\t текст:{user_text} \n\t\t\t интент: {internal_intent} \n\t\t\t ответ: {need_ident}'
    logger.info(log_message)
    log_handler.close()
    logger.removeHandler(log_handler)

    return need_ident


class ActionInfoAboutClient(Action):
    def name(self) -> Text:
        return 'action_info'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_info')

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        logger, log_handler = create_logger(tracker)
        log_message = f'RUN Action: action_info'
        logger.info(log_message)

        events = tracker.events
        all_utters = get_all_utters(events)

        last_utter = all_utters[-1] if all_utters else 'utter_q1RU'
        last_intent = tracker.latest_message['intent']['name']
        last_message = tracker.latest_message['text']
        print(last_message)

        lang, last_utter = get_last_utter_and_lang(tracker)

        if last_intent == 'langDetectKZ' or last_intent == 'changeLangKZ':
            lang == 'KZ'
        elif last_intent == 'langDetectRU' or last_intent == 'changeLangRU':
            lang == 'RU'
            
        engine_metadata_key = uuid + '-engine_metadata'
        engine_metadata_record = json.loads(engine_redis.get(engine_metadata_key).decode('utf-8'))
        engine_metadata_record['last_message'] = last_message
        engine_redis.set(engine_metadata_key, json.dumps(engine_metadata_record))

        if last_intent == 'blockTheCard' or last_intent == 'unlockIt':
            last_intent = 'block_card'

        dont_need_ident = ['kino_kz', 'registration', 'payments_and_transfers', 'halyk_travel', 'addresses_branches', 'brokerage', 'remove_the_limit', 
                           'current_loan', 'loans_mortgage', 'new_loan']

        # info about client
        trusted_phone = tracker.get_slot('trusted_phone')
        identified = tracker.get_slot('identified')
        antifraud = tracker.get_slot('antifraud')
        client_iin = tracker.get_slot('client_iin')
        verint_id = dict_to_redis['verint_id']

        log_message = f'INITIAL INFORMATION'\
        f'\n\t\t\t lang_from_redis: {lang}'\
        f'\n\t\t\t last_utter: {last_utter}'\
        f'\n\t\t\t last_intent: {last_intent}'\
        f'\n\t\t\t last_message: {last_message}'
        logger.info(log_message)

        if trusted_phone is True and antifraud is True:
            log_message_first = 'Номер доверенный / Мошенничество подтверждено / Нужен идентификация'
            response = post_verint(client_iin, verint_id, uuid)
            log_message_second = f'\n\t\t\t response:{response} {response.text}'
            logger.info(log_message_first + log_message_second)

            log_handler.close()
            logger.removeHandler(log_handler)

            if response.status_code == 200:
                dispatcher.utter_message(response = f'utter_qVerint{lang}')
                return [SlotSet('intent_to_other_script', last_intent),
                        ActionExecuted(f'utter_qVerint{lang}')]
            else:
                dispatcher.utter_message(response = f'utter_requestEgovCode{lang}')
                dispatcher.utter_message(response = f'utter_q8{lang}')
                return [ActionExecuted(f'utter_requestEgovCode{lang}'), 
                        ActionExecuted(f'utter_q8{lang}'),
                        SlotSet('intent_to_other_script', last_intent)]

        # elif trusted_phone is True and antifraud is False:
        elif trusted_phone is True and (antifraud is False or antifraud is None):
            log_message_first = 'Номер доверенный / Мошенничество не подтверждено'
            if last_intent not in dont_need_ident:
                print ('Переход на скрипт, который нужен идентификация')
                # identified = None # тут нужно проверять 'идентификации по Голосовой биометрии'
                always_need_ident = ['limits', 'block_card']
                need_ident = check_intent(last_intent, tracker)
                
                if need_ident or last_intent in always_need_ident:
                    response = post_verint(client_iin, verint_id, uuid)
                    log_message_second = f'\n\t\t\t вопрос требует идентификацию'
                    log_message_third = f'\n\t\t\t response:{response} {response.text}'
                    logger.info(log_message_first + log_message_second + log_message_third)

                    log_handler.close()
                    logger.removeHandler(log_handler)

                    if response.status_code == 200:
                        dispatcher.utter_message(response = f'utter_qVerint{lang}')
                        return [SlotSet('intent_to_other_script', last_intent),
                                ActionExecuted(f'utter_qVerint{lang}')]
                    else:
                        dispatcher.utter_message(response = f'utter_requestEgovCode{lang}')
                        dispatcher.utter_message(response = f'utter_q8{lang}')
                        return [ActionExecuted(f'utter_requestEgovCode{lang}'), 
                                ActionExecuted(f'utter_q8{lang}'),
                                SlotSet('intent_to_other_script', last_intent)]
                else:
                    log_message_second = f'\n\t\t\t вопрос не требует идентификацию'
                    logger.info(log_message_first + log_message_second)

                    log_handler.close()
                    logger.removeHandler(log_handler)

                    return [SlotSet('intent_to_other_script', last_intent),
                            FollowupAction('action_switchToAnotherScript'),]
            else:
                log_message_second = f'\n\t\t\t Переход на скрипт, не требуется идентификация'
                logger.info(log_message_first + log_message_second)

                log_handler.close()
                logger.removeHandler(log_handler)

                return [SlotSet('intent_to_other_script', last_intent),
                        FollowupAction('action_switchToAnotherScript'),]
        else:
            log_message_first = f'Для не доверенных/Не подтвержденный'
            logger.info(log_message_first)

            log_handler.close()
            logger.removeHandler(log_handler)

            return [
                SlotSet('trusted_phone', False),
                SlotSet('intent_to_other_script', last_intent),
                FollowupAction('action_switchToAnotherScript'),
            ]

class ActionInfoAfterVerint(Action):
    def name(self) -> Text:
        return 'action_infoAfterVerint'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_infoAfterVerint')

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        logger, log_handler = create_logger(tracker)
        log_message = f'RUN Action: action_infoAfterVerint'
        logger.info(log_message)

        last_intent = tracker.latest_message['intent']['name']
        last_message = tracker.latest_message['text']
        print(last_message)

        if last_intent == 'langDetectKZ' or last_intent == 'changeLangKZ':
            lang == 'KZ'
        elif last_intent == 'langDetectRU' or last_intent == 'changeLangRU':
            lang == 'RU'
        else:
            lang, last_utter = get_last_utter_and_lang(tracker)

        # info about client
        antifraud = tracker.get_slot('antifraud')
        intent_to_other_script = tracker.get_slot('intent_to_other_script')

        if 'verint_result' in dict_to_redis and dict_to_redis['verint_result'] == 'Match':
            verint_score = dict_to_redis['verint_score']
            log_message_first = f'verint_result: Match, verint_score: {verint_score}'
            if verint_score > 10:
                if antifraud is True:
                    log_message_second = f'\n\t\t\t проверка через голосовую биометрию: identified is True'
                    # обозначаем как идентификацию прошел, и попытаемся разблокировать карту (был заблокирован, потому что был признак мошеничество)

                    redirect_key = str(uuid).replace('-', '_')
                    dict_asterisk = json.loads(engine_redis.get(redirect_key).decode('utf-8'))

                    if lang == 'KZ':
                        operator_number = '79543'
                    else:
                        operator_number = '79540'

                    dict_asterisk['operator_number'] = operator_number
                    engine_redis.set(redirect_key, json.dumps(dict_asterisk))

                    max_retries = 3
                    attempts = 0

                    try:
                        id_home_bank = dict_to_redis['id_home_bank']
                    except Exception as e:
                        id_home_bank = None
                        log_message = f'Error type: {type(e).__name__}\n\t\t\t Message: {str(e)}\n\t\t\t Arguments: {e.args}'
                        logger.error(log_message)

                    print('вытаскиваем данные из апи')
                    while attempts < max_retries:
                        start_time = time.time()
                        response = get_antifraud(id_home_bank)
                        end_time = time.time()
                        print(response, flush=True)

                        log_message = f'response: {response.text}'\
                                    f'\n\t\t\t request completion time: {end_time - start_time:.2f} sec'
                        logger.info(log_message)
                        
                        if response is not None and response.status_code == 200:
                            data_response = response.json()
                            rule_id = data_response['rule_id']
                            transaction_id = data_response['Клиентский идентификатор транзакции']

                            if rule_id in ['9BEC283D720548FEB38B85D0F667CBA0', 'B3CF65F2CF8D4C7FBFB43EB7DD0DC9DF']:
                                print('заблокирован по правилам E-9* или E-9**')

                                log_message_third = f'заблокирован по правилам E-9* или E-9**'
                                logger.info(log_message_first + log_message_second + log_message_third)

                                log_handler.close()
                                logger.removeHandler(log_handler)

                                dispatcher.utter_message(response=f'utter_notifySuspiciousActivity{lang}')
                                dispatcher.utter_message(response=f'utter_q13{lang}')
                                
                                return [SlotSet('identified', True),
                                        SlotSet('identification_method', 'voice'),
                                        SlotSet('transaction_id', transaction_id),
                                        SlotSet('antifraud_rule_id', 'E-9'),
                                        ActionExecuted(f'utter_notifySuspiciousActivity{lang}'), 
                                        ActionExecuted(f'utter_q13{lang}')]
                            
                            elif rule_id in ['6A58C7D7A68F48F1A5E6B7F6D9E0E15C', 'C572DF74331D4129B54FCD051BD97E47', '4ea67607598444f4b938ff888f17422a']:
                                print('заблокирован по правилам E-15* или E-15**')

                                log_message_third = f'заблокирован по правилам E-15* или E-15**'
                                logger.info(log_message_first + log_message_second + log_message_third)

                                log_handler.close()
                                logger.removeHandler(log_handler)

                                dispatcher.utter_message(response=f'utter_notifySuspiciousActivity{lang}')
                                dispatcher.utter_message(response=f'utter_q25{lang}')
                                
                                log_message = f'заблокирован по правилам E-15* или E-15**'
                                logger.info(log_message)

                                log_handler.close()
                                logger.removeHandler(log_handler)

                                return [SlotSet('identified', True),
                                        SlotSet('identification_method', 'voice'),
                                        SlotSet('transaction_id', transaction_id),
                                        SlotSet('antifraud_rule_id', 'E-15'),
                                        ActionExecuted(f'utter_notifySuspiciousActivity{lang}'), 
                                        ActionExecuted(f'utter_q25{lang}')]
                            else:
                                log_message_third = f'заблокирован по другим правилам:{rule_id}'
                                logger.info(log_message_first + log_message_second + log_message_third)

                                log_handler.close()
                                logger.removeHandler(log_handler)

                                dispatcher.utter_message(response=f'utter_toOperatorICant{lang}')
                                return [ActionExecuted(f'utter_toOperatorICant{lang}'), ConversationPaused()]
                        attempts += 1

                    log_handler.close()
                    logger.removeHandler(log_handler)

                    dispatcher.utter_message(response=f'utter_toOperator{lang}')
                    return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
                else:
                    log_message = f'\n\t\t\t проверка через голосовую биометрию: identified is True'
                    logger.info(log_message_first + log_message)

                    log_handler.close()
                    logger.removeHandler(log_handler)

                    return [SlotSet('identified', True),
                            SlotSet('identification_method', 'voice'),
                            FollowupAction('action_switchToAnotherScript'),]
            else:
                log_message_second = f'\n\t\t\t проверка через голосовую биометрию: verint_score < 10, переход на идентификацию по ЦД'
                logger.info(log_message_first + log_message_second)

                log_handler.close()
                logger.removeHandler(log_handler)

                dispatcher.utter_message(response = f'utter_requestEgovCode{lang}')
                dispatcher.utter_message(response = f'utter_q8{lang}')
                return [ActionExecuted(f'utter_requestEgovCode{lang}'), 
                        ActionExecuted(f'utter_q8{lang}')]
        else:
            log_message = f'голосовая биометрия NULL, переход на идентификацию по ЦД'
            logger.info(log_message)

            log_handler.close()
            logger.removeHandler(log_handler)

            dispatcher.utter_message(response = f'utter_requestEgovCode{lang}')
            dispatcher.utter_message(response = f'utter_q8{lang}')
            return [ActionExecuted(f'utter_requestEgovCode{lang}'), 
                    ActionExecuted(f'utter_q8{lang}')]



class ActionSlotSetIdentCode(Action):
    def name(self) -> Text:
        return 'action_slotSetIdentCode'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_slotsetIdentCode')

        # переход на скрипт как 'доверенный номер, но не прошел идентификацию'
        return [
            SlotSet('identified', False),
            SlotSet('identification_method', 'keyword'),
            FollowupAction('action_switchToAnotherScript')
        ]


class ActionSlotSetSintez(Action):
    def name(self) -> Text:
        return 'action_slotSetSintez'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_slotSetSintez')

        # переход на скрипт как 'доверенный номер, но не прошел идентификацию'
        return [
            SlotSet('for_ques_with_sintez', 'without_sintez')
        ]


class ActionRepeat(Action):
    def name(self) -> Text:
        return 'action_repeat'

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        logger, log_handler = create_logger(tracker)
        log_message = f'RUN Action: action_repeat'
        logger.info(log_message)

        events = tracker.events
        responses = get_utters_between_two_intents(events)

        exception = ['utter_checkInfo', 'utter_soundLesslyRU', 'utter_soundLesslyKZ']

        if not responses:
            responses.append('utter_q1RU')

        for i in responses:
            if i == 'utter_waitingInLineRU':
                index = responses.index('utter_waitingInLineRU')
                responses[index] = 'utter_howToProvideCodeRU'
            elif i == 'utter_waitingInLineKZ':
                index = responses.index('utter_waitingInLineKZ')
                responses[index] = 'utter_howToProvideCodeKZ'
            else:
                continue

        # Удаляем элементы из responses, если они есть в списке exception
        filtered_responses = []
        for i in responses:
            skip = False
            for exc in exception:
                if exc in i:
                    skip = True
                    break
            if not skip:
                filtered_responses.append(i)

        for utter in reversed(filtered_responses):
            response = utter
            # print(response)
            dispatcher.utter_message(response=response)
            ActionExecuted(response)

        log_message = f'return_responses: {filtered_responses}'
        logger.info(log_message)

        log_handler.close()
        logger.removeHandler(log_handler)

        return [ActionExecuted(i) for i in reversed(filtered_responses)]


class ActionCounter(Action):
    def name(self) -> Text:
        return 'action_counter'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_counter')

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        events = tracker.events
        all_utters = get_all_utters(events)

        lang, last_utter = get_last_utter_and_lang(tracker)

        last_3 = all_utters[-3:]

        if not last_utter:
            last_utter = f'utter_q1{lang}'
        elif last_utter == 'utter_repeat_questionRU' or last_utter == 'utter_repeat_questionKZ':
            last_utter = f'utter_q1{lang}'

        a = 0
        for i in last_3:
            if str(i) == last_utter:
                a += 1
            else:
                continue

        if a == 3:
            response = f'utter_q6{lang}'
        else:
            response = last_utter
        dispatcher.utter_message(response=response)
        return [ActionExecuted(response)]


class ActionAwaitingCounter(Action):
    def name(self) -> Text:
        return 'action_awaiting'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_awaiting')

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        logger, log_handler = create_logger(tracker)
        log_message = f'RUN Action: action_awaiting'
        logger.info(log_message)

        events = tracker.events
        all_utters = get_all_utters(events)

        last_3_times = all_utters[-6:]
        lang, last_utter = get_last_utter_and_lang(tracker)

        a = 0

        for i in last_3_times:
            if i == 'utter_waitingInLineRU' or i == 'utter_waitingInLineKZ':
                a += 1
            else:
                continue
        print(a)

        log_message = f'last_3_times: {last_3_times}'\
        f'\n\t\t\t counter_for_waiting: {a}'
        logger.info(log_message)

        log_handler.close()
        logger.removeHandler(log_handler)

        if a >= 3:
            # dispatcher.utter_message(response = f'utter_toOperatorICant{lang}')

            # log_message = f'-- a == 3 -- logic has worked, call was forwarded to the operator'
            # logger.info(log_message)

            # log_handler.close()
            # logger.removeHandler(log_handler)

            # return [ActionExecuted(f'utter_toOperatorICant{lang}'), ConversationPaused()]
            # переход на скрипт как 'доверенный номер, но не прошел идентификацию'
            return [
                SlotSet('identified', False),
                SlotSet('identification_method', 'digital_code'),
                FollowupAction('action_switchToAnotherScript')
            ]
        else:
            dispatcher.utter_message(response = f'utter_waitingInLine{lang}')
            dispatcher.utter_message(response = f'utter_q9{lang}')
        
            return [ActionExecuted(f'utter_waitingInLine{lang}'), ActionExecuted(f'utter_q9{lang}')]


class ActionDigitalCodeCounter(Action):
    def name(self) -> Text:
        return 'action_dc_counter'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_dc_counter')

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        logger, log_handler = create_logger(tracker)
        log_message = f'RUN Action: action_dc_counter'
        logger.info(log_message)

        events = tracker.events
        all_utters = get_all_utters(events)

        lang, last_utter = get_last_utter_and_lang(tracker)

        last_3 = all_utters[-3:]
        print(last_3)
        
        if not last_utter:
            last_utter = f'utter_q1{lang}'

        a = 0
        for i in last_3:
            if str(i) == last_utter:
                a += 1
            else:
                continue

        log_message = f'counter_for_last_utter: {a}'
        logger.info(log_message)

        log_handler.close()
        logger.removeHandler(log_handler)

        if a >= 3:
            # переход на скрипт как 'доверенный номер, но не прошел идентификацию'
            return [
                SlotSet('identified', False),
                SlotSet('identification_method', 'digital_code'),
                FollowupAction('action_switchToAnotherScript')
            ]
        else:
            response = last_utter
            dispatcher.utter_message(response=response)
            return [ActionExecuted(response)]


class ActionOperator(Action):
    def name(self) -> Text:
        return 'action_operator'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_operator')

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        logger, log_handler = create_logger(tracker)
        log_message = f'RUN Action: action_operator'
        logger.info(log_message)

        events = tracker.events
        all_utters = get_all_utters(events)

        lang, last_utter = get_last_utter_and_lang(tracker)

        for_q5 = ['utter_q1RU', 'utter_q3RU', 'utter_q4RU', 'utter_q7RU', 'utter_q1KZ', 'utter_q3KZ', 'utter_q4KZ', 'utter_q7KZ', 'utter_interruptingRU', 'utter_interruptingKZ']
        for_q6 = ['utter_q1RU', 'utter_q3RU', 'utter_q4RU', 'utter_q5RU', 'utter_q7RU', 'utter_q8RU', 'utter_q9RU', 'utter_q10RU', 'utter_q11RU', 'utter_q12RU', 'utter_q21RU', 'utter_q22RU', 'utter_q23RU',
                  'utter_q1KZ', 'utter_q3KZ', 'utter_q4KZ', 'utter_q5KZ', 'utter_q7KZ', 'utter_q8KZ', 'utter_q9KZ', 'utter_q10KZ', 'utter_q11KZ', 'utter_q12KZ', 'utter_q21KZ', 'utter_q22RU', 'utter_q23RU']

        operator = tracker.get_slot('operator_counter')
        if operator is None:
            operator = 0

        log_message = f'operator_counter_before_append: {operator}'
        logger.info(log_message)

        if operator > 0:
            if last_utter in for_q6:
                log_handler.close()
                logger.removeHandler(log_handler)

                dispatcher.utter_message(response = f'utter_q6{lang}')
                return [ActionExecuted(f'utter_q6{lang}')]
            else:
                dispatcher.utter_message(response = f'utter_toOperator{lang}')

                log_message = f'-- operator > 0 -- logic has worked, call was forwarded to the operator'
                logger.info(log_message)

                log_handler.close()
                logger.removeHandler(log_handler)

                return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
        else:
            if last_utter in for_q5:
                dispatcher.utter_message(response= f'utter_q5{lang}')

                operator += 1

                log_message = f'operator_counter_after_append: {operator}'
                logger.info(log_message)
                
                log_handler.close()
                logger.removeHandler(log_handler)

                return [SlotSet('operator_counter', operator), ActionExecuted(f'utter_q5{lang}')]
            else:
                dispatcher.utter_message(response = f'utter_justOperator{lang}')
                dispatcher.utter_message(response = last_utter)

                operator += 1

                log_message = f'operator_counter_after_append: {operator}'
                logger.info(log_message)

                log_handler.close()
                logger.removeHandler(log_handler)

                return [SlotSet('operator_counter', operator), ActionExecuted(f'utter_justOperator{lang}'), ActionExecuted(last_utter)]


class ActionRobot(Action):
    def name(self) -> Text:
        return 'action_robot'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_robot')

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        logger, log_handler = create_logger(tracker)
        log_message = f'RUN Action: action_robot'
        logger.info(log_message)

        events = tracker.events
        all_utters = get_all_utters(events)

        lang, last_utter = get_last_utter_and_lang(tracker)

        last_intent = tracker.latest_message['intent']['name']

        exceptions = ['utter_q4RU', 'utter_q3RU', 'utter_q5RU', 'utter_q7RU','utter_q4KZ', 'utter_q3KZ', 'utter_q5KZ', 'utter_q7KZ', 'utter_interruptingRU', 'utter_interruptingKZ']

        if last_utter in exceptions:
            last_utter = f'utter_q1{lang}'

        robot = tracker.get_slot('robot_counter')
        if robot is None:
            robot = 0

        log_message = f'robot_counter_before_append: {robot}'
        logger.info(log_message)

        if robot > 1:
            dispatcher.utter_message(response=f'utter_robotThird{lang}')
            dispatcher.utter_message(response=f'utter_toOperator{lang}')

            log_message = f'-- robot > 1 -- logic has worked, call was forwarded to the operator'
            logger.info(log_message)

            log_handler.close()
            logger.removeHandler(log_handler)

            return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
        elif robot == 1:
            dispatcher.utter_message(response=f'utter_robotSecond{lang}')
            dispatcher.utter_message(response= last_utter)

            robot += 1

            log_message = f'robot_counter_after_append: {robot}'
            logger.info(log_message)

            log_handler.close()
            logger.removeHandler(log_handler)

            return [SlotSet('robot_counter', robot), ActionExecuted(f'utter_robotSecond{lang}'), ActionExecuted(last_utter)]
        else:
            dispatcher.utter_message(response=f'utter_robotFirst{lang}')
            dispatcher.utter_message(response= last_utter)

            robot += 1

            log_message = f'robot_counter_after_append: {robot}'
            logger.info(log_message)

            log_handler.close()
            logger.removeHandler(log_handler)
            
            return [SlotSet('robot_counter', robot), ActionExecuted(f'utter_robotFirst{lang}'), ActionExecuted(last_utter)]


class ActionChangeLang(Action):
    def name(self) -> Text:
        return 'action_changelang'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_changelang')

        events = tracker.events
        all_utters = get_utters_between_two_intents(events)
        last_intent = tracker.latest_message['intent']['name']
        lang, last_utter = get_last_utter_and_lang(tracker)

        exceptions = ['utter_checkInfo', 'utter_soundLesslyRU', 'utter_soundLesslyKZ']

        if not all_utters:
            all_utters.append('utter_q1RU')

        for i in all_utters:
            if i in exceptions: 
                all_utters.remove(i)
            else:
                continue

        returns = []
        
        for response in reversed(all_utters):
            response = response[:-2] + lang
            dispatcher.utter_message(response=response)
            returns.append(ActionExecuted(response))
        
        return returns


class ActionAfterQ0(Action):

    def name(self) -> Text:
        return 'action_q0'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_q0')

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))
        phone_number = dict_to_redis['phone_number']

        logger, log_handler = create_logger(tracker)
        log_message = f'STARTING A CONVERSATION Action: action_q0, uuid: {uuid}, Client: {str(phone_number)}.'
        logger.info(log_message)

        events = tracker.events
        all_utters = get_all_utters(events)

        lang, last_utter = get_last_utter_and_lang(tracker)
        
        last_intent = tracker.latest_message['intent']['name']

        try:
            trusted_phone = dict_to_redis['trusted_phone']
            antifraud = dict_to_redis['antifraud']
            identified = dict_to_redis['identified']
            client_iin = dict_to_redis['client_iin']
        except:
            trusted_phone = False
            antifraud = False
            identified = None
            client_iin = None

        log_message = f'INITIAL INFORMATION'\
        f'\n\t\t\t lang_from_redis: {lang}'\
        f'\n\t\t\t last_utter: {last_utter}'\
        f'\n\t\t\t last_intent: {last_intent}'\
        f'\n\t\t\t phone_number: {phone_number}'\
        f'\n\t\t\t trusted_phone: {trusted_phone}'\
        f'\n\t\t\t antifraud: {antifraud}'\
        f'\n\t\t\t identified: {identified}'\
        f'\n\t\t\t client_iin: {client_iin}'
        logger.info(log_message)

        if antifraud is True:
            redirect_key = str(uuid).replace('-', '_')
            dict_asterisk = json.loads(engine_redis.get(redirect_key).decode('utf-8'))

            if lang == 'KZ':
                operator_number = '79543'
            else:
                operator_number = '79540'

            dict_asterisk['operator_number'] = operator_number
            engine_redis.set(redirect_key, json.dumps(dict_asterisk))

            log_message = f'-- antifraud is True -- logic has worked, follow-up to action_info'
            logger.info(log_message)

            log_handler.close()
            logger.removeHandler(log_handler)

            # dispatcher.utter_message(response = f'utter_toOperator{lang}')
            # return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
            return [SlotSet('trusted_phone', trusted_phone), SlotSet('antifraud', antifraud), SlotSet('identified', identified), SlotSet('phone_number', phone_number), SlotSet('client_iin', client_iin), FollowupAction('action_info')]
        else:
            antifraud = False
    
        intents_utters = {
            'langDetectRU': ['utter_q4RU'],
            'langDetectKZ': ['utter_q4KZ'],
            'changeLangKZ': ['utter_q1KZ'],
            'changeLangRU': ['utter_q1RU'],
            'whoIsIt': [f'utter_langDetect{lang}', f'utter_q1{lang}'],
            'soundlessly': [f'utter_q3{lang}'],
            'haveQuestion': [f'utter_q7{lang}'],
            'aboutCard': [f'utter_q22{lang}'],
            'aboutLoans': [f'utter_q23{lang}'],
            'interrupting': [f'utter_interrupting{lang}'],
            'another': [f'utter_q6{lang}'],
            'fraud': [f'utter_q6{lang}'],
            'noApplication': [f'utter_q6{lang}'],
        }

        to_other_script = ['loans_mortgage', 'remove_the_limit', 'limits', 'forgot_card', 'reset_pin', 'card_operation', 'current_loan', 'card_delivery', 'credit_card', 
                           'new_loan', 'block_card', 'overdue_debt', 'sysn', 'super_app', 'kino_kz', 'registration', 'payments_and_transfers', 'halyk_travel', 
                           'addresses_branches', 'brokerage', 'blockTheCard', 'unlockIt']

        if last_intent in intents_utters:
            messages = intents_utters[last_intent]
            actions = []

            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))

            log_handler.close()
            logger.removeHandler(log_handler)
            
            return [SlotSet('trusted_phone', trusted_phone), SlotSet('antifraud', antifraud), SlotSet('identified', identified), SlotSet('phone_number', phone_number), SlotSet('client_iin', client_iin), *actions]
        elif last_intent in to_other_script:
            try:
                robot_list = dict_to_redis['robot_list']
            except Exception as e:
                robot_list = 'halyk_bank_identification'
                log_message = f'Error type: {type(e).__name__}\n\t\t\t Message: {str(e)}\n\t\t\t Arguments: {e.args}'
                logger.error(log_message)
            dont_need_ident = ["kino_kz", "registration", "payments_and_transfers", "halyk_travel", "addresses_branches", "brokerage", "remove_the_limit", "current_loan", "loans_mortgage", "new_loan"]
            if len(robot_list) > 1 and last_intent in dont_need_ident: #что-бы не сработал двойной переход
                dispatcher.utter_message(response = f'utter_q1{lang}')

                log_message = f'-- last_intent in to_other_script -- logic has worked, double switching so we will RETURN utter_q1{lang}'
                logger.info(log_message)

                log_handler.close()
                logger.removeHandler(log_handler)
            
                return [SlotSet('trusted_phone', trusted_phone), SlotSet('antifraud', antifraud), SlotSet('identified', identified), SlotSet('phone_number', phone_number), SlotSet('client_iin', client_iin), ActionExecuted(f'utter_q1{lang}')]
            else:
                log_message = f'-- last_intent in to_other_script -- logic has worked, follow up to action: action_info'
                logger.info(log_message)

                log_handler.close()
                logger.removeHandler(log_handler)
            
                return [SlotSet('trusted_phone', trusted_phone), SlotSet('antifraud', antifraud), SlotSet('identified', identified), SlotSet('phone_number', phone_number), SlotSet('client_iin', client_iin), FollowupAction('action_info')]
        elif last_intent == 'robot':
            log_handler.close()
            logger.removeHandler(log_handler)
            
            return [SlotSet('trusted_phone', trusted_phone), SlotSet('antifraud', antifraud), SlotSet('identified', identified), SlotSet('phone_number', phone_number), SlotSet('client_iin', client_iin), FollowupAction(f'action_robot')]
        elif last_intent == 'operator':
            log_handler.close()
            logger.removeHandler(log_handler)
            
            return [SlotSet('trusted_phone', trusted_phone), SlotSet('antifraud', antifraud), SlotSet('identified', identified), SlotSet('phone_number', phone_number), SlotSet('client_iin', client_iin), FollowupAction(f'action_operator')]
        else:
            log_handler.close()
            logger.removeHandler(log_handler)
            
            return [SlotSet('trusted_phone', trusted_phone), SlotSet('antifraud', antifraud), SlotSet('identified', identified), SlotSet('phone_number', phone_number), SlotSet('client_iin', client_iin), FollowupAction(f'action_counter')]


class ActionAfterQ1(Action):

    def name(self) -> Text:
        return 'action_q1'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_q1')

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        events = tracker.events
        all_utters = get_all_utters(events)

        lang, last_utter = get_last_utter_and_lang(tracker)
        
        last_intent = tracker.latest_message['intent']['name']

        intents_utters = {
            'langDetectRU': ['utter_q4RU'],
            'langDetectKZ': ['utter_q4KZ'],
            'changeLangKZ': ['utter_q1KZ'],
            'changeLangRU': ['utter_q1RU'],
            'whoIsIt': [f'utter_langDetect{lang}', f'utter_q1{lang}'],
            'soundlessly': [f'utter_q3{lang}'],
            'haveQuestion': [f'utter_q7{lang}'],
            'aboutCard': [f'utter_q22{lang}'],
            'aboutLoans': [f'utter_q23{lang}'],
            'interrupting': [f'utter_interrupting{lang}'],
            'another': [f'utter_q6{lang}'],
            'fraud': [f'utter_q6{lang}'],
            'noApplication': [f'utter_q6{lang}'],
        }

        to_other_script = ['loans_mortgage', 'remove_the_limit', 'limits', 'forgot_card', 'reset_pin', 'card_operation', 'current_loan', 'card_delivery', 'credit_card', 
                           'new_loan', 'block_card', 'overdue_debt', 'sysn', 'super_app', 'kino_kz', 'registration', 'payments_and_transfers', 'halyk_travel', 
                           'addresses_branches', 'brokerage', 'blockTheCard', 'unlockIt']

        if last_intent in intents_utters:
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))

            return actions
        elif last_intent in to_other_script:
            return [FollowupAction('action_info')]
        elif last_intent == 'robot':
            return [FollowupAction(f'action_robot')]
        elif last_intent == 'operator':
            return [FollowupAction(f'action_operator')]
        else:
            return [FollowupAction(f'action_counter')]


class ActionAfterQ3(Action):

    def name(self) -> Text:
        return 'action_q3'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_q3')

        events = tracker.events
        all_utters = get_all_utters(events)

        last_utter = all_utters[-1] if all_utters else 'utter_q1RU'
        last_intent = tracker.latest_message['intent']['name']
        lang, last_utter = get_last_utter_and_lang(tracker)

        intents_utters = {
            'langDetectRU': ['utter_q4RU'],
            'langDetectKZ': ['utter_q4KZ'],
            'changeLangKZ': ['utter_q1KZ'],
            'changeLangRU': ['utter_q1RU'],
            'whoIsIt': [f'utter_langDetect{lang}', f'utter_q1{lang}'],
            'haveQuestion': [f'utter_q7{lang}'],
            'aboutCard': [f'utter_q22{lang}'],
            'aboutLoans': [f'utter_q23{lang}'],
            'interrupting': [f'utter_interrupting{lang}'],
            'another': [f'utter_q6{lang}'],
            'fraud': [f'utter_q6{lang}'],
            'noApplication': [f'utter_q6{lang}'],
        }

        intents_to_q1 = ['yes', 'no', 'repeat', 'dontKnow', 'callBack', 'busy', 'internet']

        to_other_script = ['loans_mortgage', 'remove_the_limit', 'limits', 'forgot_card', 'reset_pin', 'card_operation', 'current_loan', 'card_delivery', 'credit_card', 
                           'new_loan', 'block_card', 'overdue_debt', 'sysn', 'super_app', 'kino_kz', 'registration', 'payments_and_transfers', 'halyk_travel', 
                           'addresses_branches', 'brokerage', 'blockTheCard', 'unlockIt']

        if last_intent in intents_to_q1:
            dispatcher.utter_message(response= f'utter_q1{lang}')
            return [ActionExecuted(f'utter_q1{lang}')]
        elif last_intent in intents_utters:
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))

            return actions
        elif last_intent in to_other_script:
            return [FollowupAction('action_info')]
        elif last_intent == 'robot':
            return [FollowupAction('action_robot')]
        elif last_intent == 'operator':
            return [FollowupAction('action_operator')]
        else:
            return [FollowupAction('action_counter')]

#q4, q5, q7
class ActionQuestions(Action):

    def name(self) -> Text:
        return 'action_questions'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_questions')

        last_intent = tracker.latest_message['intent']['name']
        lang, last_utter = get_last_utter_and_lang(tracker)

        intents_utters = {
            'langDetectRU': ['utter_q4RU'],
            'langDetectKZ': ['utter_q4KZ'],
            'changeLangKZ': ['utter_q1KZ'],
            'changeLangRU': ['utter_q1RU'],
            'repeat': [f'utter_q1{lang}'],
            'whoIsIt': [f'utter_langDetect{lang}', f'utter_q1{lang}'],
            'soundlessly': [f'utter_q3{lang}'],
            'haveQuestion': [f'utter_q7{lang}'],
            'aboutCard': [f'utter_q22{lang}'],
            'aboutLoans': [f'utter_q23{lang}'],
            'interrupting': [f'utter_interrupting{lang}'],
            'another': [f'utter_q6{lang}'],
            'fraud': [f'utter_q6{lang}'],
            'noApplication': [f'utter_q6{lang}'],
        }

        to_other_script = ['loans_mortgage', 'remove_the_limit', 'limits', 'forgot_card', 'reset_pin', 'card_operation', 'current_loan', 'card_delivery', 'credit_card', 
                           'new_loan', 'block_card', 'overdue_debt', 'sysn', 'super_app', 'kino_kz', 'registration', 'payments_and_transfers', 'halyk_travel', 
                           'addresses_branches', 'brokerage', 'blockTheCard', 'unlockIt']

        if last_intent in intents_utters:
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))

            return actions
        elif last_intent in to_other_script:
            return [FollowupAction('action_info')]
        elif last_intent == 'robot':
            return [FollowupAction('action_robot')]
        elif last_intent == 'operator':
            return [FollowupAction('action_operator')]
        else:
            return[FollowupAction('action_counter')]


class ActionAfterQ6(Action):

    def name(self) -> Text:
        return 'action_q6'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_q6')

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))
        all_operator_config = dict_to_redis['all_operator_config']

        redirect_key = str(uuid).replace('-', '_')
        dict_asterisk = json.loads(engine_redis.get(redirect_key).decode('utf-8'))

        logger, log_handler = create_logger(tracker)
        log_message = f'RUN Action: action_q6'
        logger.info(log_message)

        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']
        last_message = tracker.latest_message['text']
        print('last_message:', last_message)
        
        events = tracker.events
        all_utters = get_all_utters(events)
        last_2 = all_utters[-2:]
        a = 0
        for i in last_2:
            if i == 'utter_q6RU' or i == 'utter_q6KZ':
                a += 1
            else:
                continue

        log_message = f'last_message: {last_message}'\
                    f'last_intent: {last_intent}'
        logger.info(log_message)
        
        to_other_script = ['loans_mortgage', 'remove_the_limit', 'limits', 'forgot_card', 'reset_pin', 'card_operation', 'current_loan', 'card_delivery', 'credit_card', 
                           'new_loan', 'block_card', 'overdue_debt', 'sysn', 'super_app', 'kino_kz', 'registration', 'payments_and_transfers', 'halyk_travel', 
                           'addresses_branches', 'brokerage', 'blockTheCard', 'unlockIt']

        if last_intent in ['unlockIt', 'blockTheCard']:
            last_intent == 'block_card'
        elif last_intent == 'noApplication':
            last_intent == 'super_app'

        keywords = {
            'about_app': ['приложение', 'қосымша', 'мобильдік', 'мобильное', 'мобильном', 'приложению', 'приложении', 'мобильді', 'қосымшасында', 'қосымшада', 'қолданбада', 'қосымшаны', 'қолданбамды'],
            'about_deposit': ['депозит', 'депозитный', 'депозитте', 'депозиттен', 'депози', 'депосит', 'депоситов', 'депозитам', 'депозитов', 'депозиту', 'депозита', 'депозиттер', 'депозиттердің'],
            'about_block': ['заблокирован', "заблокируйте", "разблокируйте", "разблокировка", "блокта"],
            'about_travel': ['билеты', "билеты", "травел", "трэвел", "кино"],
            'about_limits': ['лимиты', "лимит"],
            'about_pin': ['пин', "пинкод"],
            'about_overdue': ['просрочка', "просрочен"],
            'about_ipoteka': ['ипотека', "автокредит", "ипотеку"],
            'about_susn': ['пенсия', "пенсию", "пособие", "пособия"],
            'about_transfer': ['платежи', "перевод", "переводы", "платеж"],
            'about_brokerage': ['брокерский', "брокер", "акция", "акции"],
            'about_credit': ['кредит', 'кредитам', 'кредиты', 'несие', "рассрочка", "рассрочку", "кредита", "несием"],
            'about_card': ['карта', 'картам', 'карты']
        }

        vdn = {
            'about_app': {'RU': '79288', 'KZ': '79287'},
            'about_deposit': {'RU': '79284', 'KZ': '79283'},
            'about_block': {'RU': '79266', 'KZ': '79265'},
            'about_travel': {'RU': '79102', 'KZ': '79101'},
            'about_limits': {'RU': '79264', 'KZ': '79263'},
            'about_pin': {'RU': '79274', 'KZ': '79273'},
            'about_overdue': {'RU': '79871', 'KZ': '79872'},
            'about_ipoteka': {'RU': '79166', 'KZ': '79165'},
            'about_susn': {'RU': '79226', 'KZ': '79227'},
            'about_transfer': {'RU': '79280', 'KZ': '79279'},
            'about_brokerage': {'RU': '79896', 'KZ': '79285'},
            'about_credit': {'RU': '79241', 'KZ': '79240'},
            'about_card': {'RU': '79261', 'KZ': '79262'},
        }
        
        if last_intent in to_other_script:
            operator_number_ru = all_operator_config[last_intent]['operator_number_ru']
            operator_number_kz = all_operator_config[last_intent]['operator_number_kz']

            redirect_key = str(uuid).replace('-', '_')
            dict_asterisk = json.loads(engine_redis.get(redirect_key).decode('utf-8'))

            if lang == 'KZ':
                operator_number = operator_number_kz[-1]
            else:
                operator_number = operator_number_ru[-1]

            dict_asterisk['operator_number'] = operator_number
            engine_redis.set(redirect_key, json.dumps(dict_asterisk))

            log_message = f'-- last_intent in to_other_script -- logic has worked, call was forwarded to the operator: {operator_number}'
            logger.info(log_message)

            log_handler.close()
            logger.removeHandler(log_handler)

            dispatcher.utter_message(response = f'utter_toOperator{lang}')
            return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
        elif last_intent == 'robot':
            return [FollowupAction(f'action_robot')]
        elif last_intent == 'changeLangKZ' or last_intent == 'changeLangRU':
            return [FollowupAction('action_changelang')]
        elif a >= 2:
            about_what = ''

            for k, v in keywords.items():
                for j in v:
                    if j in last_message:
                        about_what = k
                        break
                    else:
                        continue

            if last_intent == 'aboutCard':
                if lang == 'KZ':
                    operator_number = '79262'
                else:
                    operator_number = '79261'
                
                log_message = f'-- a >= 2, last_intent == aboutCard -- logic has worked, call was forwarded to the operator: {operator_number}'

            elif last_intent == 'aboutLoans':
                if lang == 'KZ':
                    operator_number = '79240'
                else:
                    operator_number = '79241'
                
                log_message = f'-- a >= 2, last_intent == aboutLoans -- logic has worked, call was forwarded to the operator: {operator_number}'

            elif about_what != '':
                operator_number = vdn[about_what][lang]
                
                log_message = f'-- a >= 2, about_what not NULL, key == {about_what} -- logic has worked, call was forwarded to the operator: {operator_number}'

            else:
                if lang == 'KZ':
                    operator_number = '79271'
                else:
                    operator_number = '79272'
                
                log_message = f'-- a >= 2 and else -- logic has worked, call was forwarded to the operator: {operator_number}'
            
            dict_asterisk['operator_number'] = operator_number
            engine_redis.set(redirect_key, json.dumps(dict_asterisk))
    
            logger.info(log_message)
            log_handler.close()
            logger.removeHandler(log_handler)

            dispatcher.utter_message(response = f'utter_toOperator{lang}')
            return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
        else:
            about_what = ''

            for k, v in keywords.items():
                for j in v:
                    if j in last_message:
                        about_what = k
                        break
                    else:
                        continue

            if last_intent not in ['aboutCard', 'aboutLoans'] and about_what != '':
                operator_number = vdn[about_what][lang]
                
                dict_asterisk['operator_number'] = operator_number
                engine_redis.set(redirect_key, json.dumps(dict_asterisk))
        
                log_message = f'-- else, about_what not NULL, key == {about_what} -- logic has worked, call was forwarded to the operator: {operator_number}'
                logger.info(log_message)

                log_handler.close()
                logger.removeHandler(log_handler)

                dispatcher.utter_message(response = f'utter_toOperator{lang}')
                return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
            else:
                log_message = f'-- else -- logic has worked, second time repeat q6'
                logger.info(log_message)

                log_handler.close()
                logger.removeHandler(log_handler)

                dispatcher.utter_message(response = f'utter_q6{lang}')
                return [ActionExecuted(f'utter_q6{lang}')]


class ActionSlotSetQ10(Action):

    def name(self) -> Text:
        return 'action_slotset_q10'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_slotset_q10')

        lang, last_utter = get_last_utter_and_lang(tracker)

        dispatcher.utter_message(response=f'utter_q10{lang}')
        return[SlotSet('for_q10', 'again_q10'), ActionExecuted(f'utter_q10{lang}')]


class ActionAfterQ10(Action):

    def name(self) -> Text:
        return 'action_q10'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_q10')

        events = tracker.events
        all_utters = get_all_utters(events)
        all_intents = get_all_intents(events)

        last_intent = tracker.latest_message['intent']['name']

        last_3 = all_utters[-3:]
        last_3_intents = all_intents[-3:]
        lang, last_utter = get_last_utter_and_lang(tracker)

        intents_utters = {
            'changeLangKZ': ['utter_q10KZ'],
            'changeLangRU': ['utter_q10RU'],
            'repeat': [f'utter_silence{lang}', f'utter_q10{lang}'],
            'whereIsCode': [f'utter_howToProvideCode{lang}', f'utter_q10{lang}'],
            'whoIsIt': [f'utter_langDetect{lang}', f'utter_q10{lang}'],
            'soundlessly': [f'utter_soundLessly{lang}', f'utter_q10{lang}'],
            'wait': [f'utter_waitingInLine{lang}', f'utter_q10{lang}'],
            'internet': [f'utter_requestCardKeyword{lang}', f'utter_q11{lang}'],
            'noApplication': [f'utter_requestCardKeyword{lang}', f'utter_q11{lang}'],
        }

        if last_intent in intents_utters:
            messages = intents_utters[last_intent]
            actions = []

            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))

            return actions
        elif last_intent == 'codeNumber':
            counter_codeNumber = get_counter_intent('codeNumber', events)
            print(counter_codeNumber)

            code_user = tracker.get_slot('code')
            print('card_number который клиент сказал:', code_user)

            if code_user is not None and len(code_user) == 6:
                print('состоит из 6 цифры')
                code_1 = code_user[:2]
                code_2 = code_user[2:4]
                code_3 = code_user[4:]

                if lang == 'RU':
                    priority = 55
                elif lang ==  'KZ':
                    priority = 56

                changeCSV(priority, lang, code_1, code_2, code_3, tracker)

                dispatcher.utter_message(response=f'utter_before21{lang}')
                dispatcher.utter_message(response=f'utter_code1{lang}', code_1=code_1)
                dispatcher.utter_message(response=f'utter_code2{lang}', code_2=code_2)
                dispatcher.utter_message(response=f'utter_code3{lang}', code_3=code_3)
                dispatcher.utter_message(response=f'utter_q21{lang}')

                logger, log_handler = create_logger(tracker)
                log_message = f'RUN Action: action_q10'
                logger.info(log_message)

                log_message = f'-- code_user is not None and len(code_user) == 6 -- card_number_which_client_said: {code_user}'
                logger.info(log_message)

                log_handler.close()
                logger.removeHandler(log_handler)

                return [ActionExecuted(f'utter_before21{lang}'), ActionExecuted(f'utter_code1{lang}'), ActionExecuted(f'utter_code2{lang}'), ActionExecuted(f'utter_code3{lang}'), ActionExecuted(f'utter_q21{lang}'), ]
            else:
                a = 0
                for i in last_3_intents:
                    if i == 'codeNumber':
                    # if i == 'utter_q10RU' or i == 'utter_q10KZ':
                        a += 1
                    else:
                        continue

                logger, log_handler = create_logger(tracker)
                log_message = f'RUN Action: action_q10'
                logger.info(log_message)
                
                log_message = f'-- code_user is less/more then 6 number, count: {a}, card_number_which_client_said: {code_user}'
                logger.info(log_message)

                log_handler.close()
                logger.removeHandler(log_handler)

                if a == 2:
                    # переход на скрипт как 'доверенный номер, но не прошел идентификацию'
                    return [SlotSet('identified', False),
                            SlotSet('identification_method', 'digital_code'),
                            FollowupAction('action_switchToAnotherScript')]
                else:
                    dispatcher.utter_message(response=f'utter_q10{lang}')
                    return [ActionExecuted(f'utter_q10{lang}')]
        elif last_intent == 'robot':
            return [FollowupAction('action_robot')]
        elif last_intent == 'operator':
            return [FollowupAction('action_operator')]
        else:
            return[SlotSet('for_q10', 'again_q10'), FollowupAction('action_counter')]


class ActionReturnQ21(Action):

    def name(self) -> Text:
        return 'action_returnq21'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_returnq21')

        last_intent = tracker.latest_message['intent']['name']
        lang, last_utter = get_last_utter_and_lang(tracker)

        code_user = tracker.get_slot('code')
        print('card_number который клиент сказал:', code_user)

        if not code_user or len(code_user) != 6:
            dispatcher.utter_message(response = f'utter_q10{lang}')
            return [SlotSet('code', None), ActionExecuted(f'utter_q10{lang}')]
        elif len(code_user) == 6:
            code_1 = code_user[:2]
            code_2 = code_user[2:4]
            code_3 = code_user[4:]

        if lang == 'RU':
            priority = 55
        elif lang ==  'KZ':
            priority = 56

        changeCSV(priority, lang, code_1, code_2, code_3, tracker)

        dispatcher.utter_message(response=f'utter_before21{lang}')
        dispatcher.utter_message(response=f'utter_code1{lang}', code_1=code_1)
        dispatcher.utter_message(response=f'utter_code2{lang}', code_2=code_2)
        dispatcher.utter_message(response=f'utter_code3{lang}', code_3=code_3)
        dispatcher.utter_message(response=f'utter_q21{lang}')

        return [ActionExecuted(f'utter_before21{lang}'), ActionExecuted(f'utter_code1{lang}'), ActionExecuted(f'utter_code2{lang}'), ActionExecuted(f'utter_code3{lang}'), ActionExecuted(f'utter_q21{lang}')]  


class ActionAfterQ22(Action):

    def name(self) -> Text:
        return 'action_q22'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_q22')

        last_intent = tracker.latest_message['intent']['name']
        lang, last_utter = get_last_utter_and_lang(tracker)

        intents_utters = {
            'changeLangKZ': ['utter_q22KZ'],
            'changeLangRU': ['utter_q22RU'],
            'repeat': [f'utter_silence{lang}', f'utter_q22{lang}'],
            'whoIsIt': [f'utter_langDetect{lang}', f'utter_q22{lang}'],
            'soundlessly': [f'utter_q3{lang}'],
            'haveQuestion': [f'utter_q7{lang}'],
            'interrupting': [f'utter_interrupting{lang}'],
            'another': [f'utter_q6{lang}'],
            'fraud': [f'utter_q6{lang}'],
            'noApplication': [f'utter_q6{lang}'],
        }

        to_other_script = ['loans_mortgage', 'remove_the_limit', 'limits', 'forgot_card', 'reset_pin', 'card_operation', 'current_loan', 'card_delivery', 'credit_card', 
                           'new_loan', 'block_card', 'overdue_debt', 'sysn', 'super_app', 'kino_kz', 'registration', 'payments_and_transfers', 'halyk_travel', 
                           'addresses_branches', 'brokerage', 'blockTheCard', 'unlockIt']

        if last_intent in intents_utters:
            messages = intents_utters[last_intent]
            actions = []

            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))

            return actions
        elif last_intent in to_other_script:
            return [FollowupAction('action_info')]
        elif last_intent == 'robot':
            return [FollowupAction('action_robot')]
        elif last_intent == 'operator':
            return [FollowupAction('action_operator')]
        else:
            return[FollowupAction('action_counter')]


class ActionAfterQ23(Action):

    def name(self) -> Text:
        return 'action_q23'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_q23')

        last_intent = tracker.latest_message['intent']['name']
        lang, last_utter = get_last_utter_and_lang(tracker)

        intents_utters = {
            'changeLangKZ': ['utter_q23KZ'],
            'changeLangRU': ['utter_q23RU'],
            'repeat': [f'utter_silence{lang}', f'utter_q23{lang}'],
            'whoIsIt': [f'utter_langDetect{lang}', f'utter_q23{lang}'],
            'soundlessly': [f'utter_q3{lang}'],
            'haveQuestion': [f'utter_q7{lang}'],
            'interrupting': [f'utter_interrupting{lang}'],
            'another': [f'utter_q6{lang}'],
            'fraud': [f'utter_q6{lang}'],
            'noApplication': [f'utter_q6{lang}'],
        }

        to_other_script = ['loans_mortgage', 'remove_the_limit', 'limits', 'forgot_card', 'reset_pin', 'card_operation', 'current_loan', 'card_delivery', 'credit_card', 
                           'new_loan', 'block_card', 'overdue_debt', 'sysn', 'super_app', 'kino_kz', 'registration', 'payments_and_transfers', 'halyk_travel', 
                           'addresses_branches', 'brokerage', 'blockTheCard', 'unlockIt']

        if last_intent in intents_utters:
            messages = intents_utters[last_intent]
            actions = []

            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))

            return actions
        elif last_intent in to_other_script:
            return [FollowupAction('action_info')]
        elif last_intent == 'robot':
            return [FollowupAction('action_robot')]
        elif last_intent == 'operator':
            return [FollowupAction('action_operator')]
        else:
            return[FollowupAction('action_counter')]


class ActionCheckDigitalCode(Action):

    def name(self) -> Text:
        return 'action_checkDigitalCode'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_checkDigitalCode')

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        logger, log_handler = create_logger(tracker)
        log_message = f'RUN Action: action_checkDigitalCode'
        logger.info(log_message)

        events = tracker.events
        all_utters = get_all_utters(events)
        all_intents = get_all_intents(events)

        last_intent = tracker.latest_message['intent']['name']
        lang, last_utter = get_last_utter_and_lang(tracker)

        last_3_intents = all_intents[-3:]
        a = 0
        for i in all_utters:
            if i == 'utter_q21RU' or i == 'utter_q21KZ':
                a += 1
            else:
                continue
        print(a)

        log_message = f'last_utter: {last_utter}'\
                      f'\n\t\t\t last_intent: {last_intent}'\
                      f'\n\t\t\t counter_for_q21: {a}'
        logger.info(log_message)

        if a < 2:
            if last_intent == 'yes':

                code_user = tracker.get_slot('code')
                client_iin = tracker.get_slot('client_iin')

                max_retries = 3
                attempts = 0
                identified = False

                log_message = f'code_user_said: {code_user}'\
                            f'\n\t\t\t client_iin: {client_iin}'
                logger.info(log_message)

                print('Робот сверяет код через Сервис ЦД')
                while attempts < max_retries:
                    start_time = time.time()
                    response = get_digital_code(code_user, client_iin) # чекам мэчиться или нет с переменным code_user(это код который сказал клиент)
                    end_time = time.time()

                    log_message = f'response: {response}'\
                                f'\n\t\t\t request completion time: {end_time - start_time:.2f} sec'
                    logger.info(log_message)

                    if response is not None:
                        if response == 'SUCCESS':
                            identified = True
                        else:
                            identified = False

                        antifraud = tracker.get_slot('antifraud')

                        if identified is True and antifraud is True:
                            # обозначаем как идентификацию прошел, и попытаемся разблокировать карту (был заблокирован, потому что был признак мошшеничество)

                            redirect_key = str(uuid).replace('-', '_')
                            dict_asterisk = json.loads(engine_redis.get(redirect_key).decode('utf-8'))

                            if lang == 'KZ':
                                operator_number = '79543'
                            else:
                                operator_number = '79540'

                            dict_asterisk['operator_number'] = operator_number
                            engine_redis.set(redirect_key, json.dumps(dict_asterisk))

                            max_retries = 3
                            attempts = 0

                            try:
                                id_home_bank = dict_to_redis['id_home_bank']
                            except Exception as e:
                                id_home_bank = None
                                log_message = f'Error type: {type(e).__name__}\n\t\t\t Message: {str(e)}\n\t\t\t Arguments: {e.args}'
                                logger.error(log_message)

                            phone_number = tracker.get_slot('phone_number')

                            print('вытаскиваем данные из апи')
                            while attempts < max_retries:
                                # response_for_id = get_dossier_info(phone_number)
                                # data_response_for_id = response_for_id.json()
                                # id_home_bank = data_response_for_id["idHomeBank"]
                                
                                # log_message = f'data_response_for_id: {data_response_for_id}'\
                                #             f'\n\t\t\t id_home_bank: {id_home_bank} sec'
                                # logger.info(log_message)

                                start_time = time.time()
                                response = get_antifraud(id_home_bank)
                                end_time = time.time()

                                log_message = f'response: {response.text}'\
                                            f'\n\t\t\t request completion time: {end_time - start_time:.2f} sec'
                                logger.info(log_message)

                                # data_response = response.json()
                                # hasDeny = data_response['hasDeny']
                                
                                if response is not None and response.status_code == 200:
                                    data_response = response.json()
                                    rule_id = data_response['rule_id']
                                    transaction_id = data_response['Клиентский идентификатор транзакции']

                                    if rule_id in ['9BEC283D720548FEB38B85D0F667CBA0', 'B3CF65F2CF8D4C7FBFB43EB7DD0DC9DF']:
                                        print('заблокирован по правилам E-9* или E-9**')

                                        dispatcher.utter_message(response=f'utter_notifySuspiciousActivity{lang}')
                                        dispatcher.utter_message(response=f'utter_q13{lang}')

                                        log_message = f'заблокирован по правилам E-9* или E-9**'
                                        logger.info(log_message)

                                        log_handler.close()
                                        logger.removeHandler(log_handler)

                                        return [SlotSet('identified', identified),
                                                SlotSet('identification_method', 'digital_code'),
                                                SlotSet('transaction_id', transaction_id),
                                                SlotSet('antifraud_rule_id', 'E-9'),
                                                ActionExecuted(f'utter_notifySuspiciousActivity{lang}'), 
                                                ActionExecuted(f'utter_q13{lang}')]
                                    
                                    elif rule_id in ['6A58C7D7A68F48F1A5E6B7F6D9E0E15C', 'C572DF74331D4129B54FCD051BD97E47', '4ea67607598444f4b938ff888f17422a']:
                                        print('заблокирован по правилам E-15* или E-15**')

                                        dispatcher.utter_message(response=f'utter_notifySuspiciousActivity{lang}')
                                        dispatcher.utter_message(response=f'utter_q25{lang}')
                                        
                                        log_message = f'заблокирован по правилам E-15* или E-15**'
                                        logger.info(log_message)

                                        log_handler.close()
                                        logger.removeHandler(log_handler)

                                        return [SlotSet('identified', identified),
                                                SlotSet('identification_method', 'digital_code'),
                                                SlotSet('transaction_id', transaction_id),
                                                SlotSet('antifraud_rule_id', 'E-15'),
                                                ActionExecuted(f'utter_notifySuspiciousActivity{lang}'), 
                                                ActionExecuted(f'utter_q25{lang}')]
                                    else:
                                        log_message = f'заблокирован по другим правилам:{rule_id}'
                                        logger.info(log_message)

                                        log_handler.close()
                                        logger.removeHandler(log_handler)

                                        dispatcher.utter_message(response=f'utter_toOperatorICant{lang}')
                                        return [ActionExecuted(f'utter_toOperatorICant{lang}'), ConversationPaused()]
                                attempts += 1

                            log_handler.close()
                            logger.removeHandler(log_handler)

                            dispatcher.utter_message(response=f'utter_toOperator{lang}')
                            return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
                        else:
                            log_handler.close()
                            logger.removeHandler(log_handler)

                            # переход на скрипт
                            return [
                                    SlotSet('identified', identified),
                                    SlotSet('identification_method', 'digital_code'),
                                    FollowupAction('action_switchToAnotherScript')
                                ]
                    attempts += 1

                log_handler.close()
                logger.removeHandler(log_handler)

                dispatcher.utter_message(response=f'utter_toOperator{lang}')
                return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
            elif last_intent == 'no':
                dispatcher.utter_message(response=f'utter_q10{lang}')
                return [ActionExecuted(f'utter_q10{lang}')]
            elif last_intent == 'codeNumber':
                counter_codeNumber = get_counter_intent('codeNumber', events)
                print(counter_codeNumber)

                code_user = tracker.get_slot('code')
                print('card_number который клиент сказал:', code_user)

                if code_user is not None and len(code_user) == 6:
                    print('состоит из 6 цифры')
                    code_1 = code_user[:2]
                    code_2 = code_user[2:4]
                    code_3 = code_user[4:]

                    if lang == 'RU':
                        priority = 55
                    elif lang ==  'KZ':
                        priority = 56

                    changeCSV(priority, lang, code_1, code_2, code_3, tracker)

                    dispatcher.utter_message(response=f'utter_before21{lang}')
                    dispatcher.utter_message(response=f'utter_code1{lang}', code_1=code_1)
                    dispatcher.utter_message(response=f'utter_code2{lang}', code_2=code_2)
                    dispatcher.utter_message(response=f'utter_code3{lang}', code_3=code_3)
                    dispatcher.utter_message(response=f'utter_q21{lang}')

                    logger, log_handler = create_logger(tracker)
                    log_message = f'RUN Action: action_q10'
                    logger.info(log_message)

                    log_message = f'-- code_user is not None and len(code_user) == 6 -- card_number_which_client_said: {code_user}'
                    logger.info(log_message)

                    log_handler.close()
                    logger.removeHandler(log_handler)

                    return [ActionExecuted(f'utter_before21{lang}'), ActionExecuted(f'utter_code1{lang}'), ActionExecuted(f'utter_code2{lang}'), ActionExecuted(f'utter_code3{lang}'), ActionExecuted(f'utter_q21{lang}'), ]
                else:
                    a = 0
                    for i in last_3_intents:
                        if i == 'codeNumber':
                        # if i == 'utter_q10RU' or i == 'utter_q10KZ':
                            a += 1
                        else:
                            continue

                    logger, log_handler = create_logger(tracker)
                    log_message = f'RUN Action: action_q10'
                    logger.info(log_message)
                    
                    log_message = f'-- code_user is less/more then 6 number, count: {a}, card_number_which_client_said: {code_user}'
                    logger.info(log_message)

                    log_handler.close()
                    logger.removeHandler(log_handler)

                    if a == 2:
                        # переход на скрипт как 'доверенный номер, но не прошел идентификацию'
                        return [SlotSet('identified', False),
                                SlotSet('identification_method', 'digital_code'),
                                FollowupAction('action_switchToAnotherScript')]
                    else:
                        dispatcher.utter_message(response=f'utter_q10{lang}')
                        return [ActionExecuted(f'utter_q10{lang}')]
            else:
                code_user = tracker.get_slot('code')

                if code_user and len(code_user) == 6:
                    code_1 = code_user[:2]
                    code_2 = code_user[2:4]
                    code_3 = code_user[4:]
                else:
                    # переход на скрипт как 'доверенный номер, но не прошел идентификацию'
                    return[ SlotSet('identified', False),
                            SlotSet('identification_method', 'digital_code'),
                            FollowupAction('action_switchToAnotherScript')]

                if lang == 'RU':
                    priority = 55
                elif lang ==  'KZ':
                    priority = 56

                changeCSV(priority, lang, code_1, code_2, code_3, tracker)

                dispatcher.utter_message(response=f'utter_before21{lang}')
                dispatcher.utter_message(response=f'utter_code1{lang}', code_1=code_1)
                dispatcher.utter_message(response=f'utter_code2{lang}', code_2=code_2)
                dispatcher.utter_message(response=f'utter_code3{lang}', code_3=code_3)
                dispatcher.utter_message(response=f'utter_q21{lang}')
                
                return [ActionExecuted(f'utter_before21{lang}'), ActionExecuted(f'utter_code1{lang}'), ActionExecuted(f'utter_code2{lang}'), ActionExecuted(f'utter_code3{lang}'), ActionExecuted(f'utter_q21{lang}'), ]  
        else:
            if last_intent == 'yes':

                code_user = tracker.get_slot('code')
                client_iin = tracker.get_slot('client_iin')

                max_retries = 3
                attempts = 0
                identified = False

                log_message = f'code_user_said: {code_user}'\
                            f'\n\t\t\t client_iin: {client_iin}'
                logger.info(log_message)

                print('Робот сверяет код через Сервис ЦД')
                while attempts < max_retries:
                    start_time = time.time()
                    response = get_digital_code(code_user, client_iin) # чекам мэчиться или нет с переменным code_user(это код который сказал клиент)
                    end_time = time.time()

                    log_message = f'response: {response}'\
                                f'\n\t\t\t request completion time: {end_time - start_time:.2f} sec'
                    logger.info(log_message)

                    if response is not None:
                        if response == 'SUCCESS':
                            identified = True
                        else:
                            identified = False

                        antifraud = tracker.get_slot('antifraud')

                        if identified is True and antifraud is True:
                            # обозначаем как идентификацию прошел, и попытаемся разблокировать карту (был заблокирован, потому что был признак мошшеничество)

                            redirect_key = str(uuid).replace('-', '_')
                            dict_asterisk = json.loads(engine_redis.get(redirect_key).decode('utf-8'))

                            if lang == 'KZ':
                                operator_number = '79543'
                            else:
                                operator_number = '79540'

                            dict_asterisk['operator_number'] = operator_number
                            engine_redis.set(redirect_key, json.dumps(dict_asterisk))

                            max_retries = 3
                            attempts = 0

                            try:
                                id_home_bank = dict_to_redis['id_home_bank']
                            except Exception as e:
                                id_home_bank = None
                                log_message = f'Error type: {type(e).__name__}\n\t\t\t Message: {str(e)}\n\t\t\t Arguments: {e.args}'
                                logger.error(log_message)

                            phone_number = tracker.get_slot('phone_number')

                            print('вытаскиваем данные из апи')
                            while attempts < max_retries:
                                # response_for_id = get_dossier_info(phone_number)
                                # data_response_for_id = response_for_id.json()
                                # id_home_bank = data_response_for_id["idHomeBank"]
                                
                                # log_message = f'data_response_for_id: {data_response_for_id}'\
                                #             f'\n\t\t\t id_home_bank: {id_home_bank} sec'
                                # logger.info(log_message)

                                start_time = time.time()
                                response = get_antifraud(id_home_bank)
                                end_time = time.time()

                                log_message = f'response: {response.text}'\
                                            f'\n\t\t\t request completion time: {end_time - start_time:.2f} sec'
                                logger.info(log_message)

                                # data_response = response.json()
                                # hasDeny = data_response['hasDeny']
                                
                                if response is not None and response.status_code == 200:
                                    data_response = response.json()
                                    rule_id = data_response['rule_id']
                                    transaction_id = data_response['Клиентский идентификатор транзакции']

                                    if rule_id in ['9BEC283D720548FEB38B85D0F667CBA0', 'B3CF65F2CF8D4C7FBFB43EB7DD0DC9DF']:
                                        print('заблокирован по правилам E-9* или E-9**')

                                        dispatcher.utter_message(response=f'utter_notifySuspiciousActivity{lang}')
                                        dispatcher.utter_message(response=f'utter_q13{lang}')

                                        log_message = f'заблокирован по правилам E-9* или E-9**'
                                        logger.info(log_message)

                                        log_handler.close()
                                        logger.removeHandler(log_handler)

                                        return [SlotSet('identified', identified),
                                                SlotSet('identification_method', 'digital_code'),
                                                SlotSet('transaction_id', transaction_id),
                                                SlotSet('antifraud_rule_id', 'E-9'),
                                                ActionExecuted(f'utter_notifySuspiciousActivity{lang}'), 
                                                ActionExecuted(f'utter_q13{lang}')]
                                    
                                    elif rule_id in ['6A58C7D7A68F48F1A5E6B7F6D9E0E15C', 'C572DF74331D4129B54FCD051BD97E47', '4ea67607598444f4b938ff888f17422a']:
                                        print('заблокирован по правилам E-15* или E-15**')

                                        dispatcher.utter_message(response=f'utter_notifySuspiciousActivity{lang}')
                                        dispatcher.utter_message(response=f'utter_q25{lang}')
                                        
                                        log_message = f'заблокирован по правилам E-15* или E-15**'
                                        logger.info(log_message)

                                        log_handler.close()
                                        logger.removeHandler(log_handler)

                                        return [SlotSet('identified', identified),
                                                SlotSet('identification_method', 'digital_code'),
                                                SlotSet('transaction_id', transaction_id),
                                                SlotSet('antifraud_rule_id', 'E-15'),
                                                ActionExecuted(f'utter_notifySuspiciousActivity{lang}'), 
                                                ActionExecuted(f'utter_q25{lang}')]
                                    else:
                                        log_message = f'заблокирован по другим правилам:{rule_id}'
                                        logger.info(log_message)

                                        log_handler.close()
                                        logger.removeHandler(log_handler)

                                        dispatcher.utter_message(response=f'utter_toOperatorICant{lang}')
                                        return [ActionExecuted(f'utter_toOperatorICant{lang}'), ConversationPaused()]
                                attempts += 1

                            log_handler.close()
                            logger.removeHandler(log_handler)

                            dispatcher.utter_message(response=f'utter_toOperator{lang}')
                            return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
                        else:
                            log_handler.close()
                            logger.removeHandler(log_handler)

                            # переход на скрипт
                            return [
                                    SlotSet('identified', identified),
                                    SlotSet('identification_method', 'digital_code'),
                                    FollowupAction('action_switchToAnotherScript')
                                ]
                    attempts += 1

                log_handler.close()
                logger.removeHandler(log_handler)

                dispatcher.utter_message(response=f'utter_toOperator{lang}')
                return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
            else:
                # переход на скрипт как 'доверенный номер, но не прошел идентификацию'
                return[ SlotSet('identified', False),
                        SlotSet('identification_method', 'digital_code'),
                        FollowupAction('action_switchToAnotherScript')]


class ActionCheckCodeWord(Action):

    def name(self) -> Text:
        return 'action_checkCodeWord'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_checkCodeWord')

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        logger, log_handler = create_logger(tracker)
        log_message = f'RUN Action: action_checkCodeWord'
        logger.info(log_message)

        events = tracker.events
        all_utters = get_all_utters(events)

        text = tracker.latest_message['text']
        text = text.replace(' ', '')
        print('text:', text)

        lang, last_utter = get_last_utter_and_lang(tracker)

        client_iin = tracker.get_slot('client_iin')

        max_retries = 3
        attempts = 0

        log_message = f'keyword_client_said: {text}'\
                      f'\n\t\t\t client_iin: {client_iin}'
        logger.info(log_message)

        while attempts < max_retries:
            # чекам мэчиться или нет с переменным text (это кодовое слово который сказал клиент)
            identified = None
            start_time = time.time()
            response = get_keyword(client_iin)
            end_time = time.time()

            log_message = f'response: {response.text}'\
                          f'\n\t\t\t request completion time: {end_time - start_time:.2f} sec'
            logger.info(log_message)

            if response is not None and response.status_code == 200:
                data_response = response.json()
                keyword = data_response[0]['keyWD'].lower()

                if keyword == text:
                    identified = True

                    log_message = f'match_with_from_db: True'
                    logger.info(log_message)

                else:
                    identified = False

                    log_message = f'match_with_from_db: False'
                    logger.info(log_message)

                antifraud = tracker.get_slot('antifraud')

                if identified is True and antifraud is True:
                    # обозначаем как идентификацию прошел, и попытаемся разблокировать карту (был заблокирован, потому что был признак мошшеничество)

                    redirect_key = str(uuid).replace('-', '_')
                    dict_asterisk = json.loads(engine_redis.get(redirect_key).decode('utf-8'))

                    if lang == 'KZ':
                        operator_number = '79543'
                    else:
                        operator_number = '79540'

                    dict_asterisk['operator_number'] = operator_number
                    engine_redis.set(redirect_key, json.dumps(dict_asterisk))

                    max_retries = 3
                    attempts = 0
                    
                    try:
                        id_home_bank = dict_to_redis['id_home_bank']
                    except Exception as e:
                        id_home_bank = None
                        log_message = f'Error type: {type(e).__name__}\n\t\t\t Message: {str(e)}\n\t\t\t Arguments: {e.args}'
                        logger.error(log_message)

                    print('вытаскиваем данные из апи')
                    while attempts < max_retries:
                        start_time = time.time()
                        response = get_antifraud(id_home_bank)
                        end_time = time.time()
                        print(response, flush=True)

                        log_message = f'response: {response.text}'\
                                    f'\n\t\t\t request completion time: {end_time - start_time:.2f} sec'
                        logger.info(log_message)
                        
                        if response is not None and response.status_code == 200:
                            data_response = response.json()
                            rule_id = data_response['rule_id']
                            transaction_id = data_response['Клиентский идентификатор транзакции']

                            if rule_id in ['9BEC283D720548FEB38B85D0F667CBA0', 'B3CF65F2CF8D4C7FBFB43EB7DD0DC9DF']:
                                print('заблокирован по правилам E-9* или E-9**')
                                
                                dispatcher.utter_message(response=f'utter_notifySuspiciousActivity{lang}')
                                dispatcher.utter_message(response=f'utter_q13{lang}')
                                
                                log_message = f'заблокирован по правилам E-9* или E-9**'
                                logger.info(log_message)

                                log_handler.close()
                                logger.removeHandler(log_handler)

                                return [SlotSet('identified', identified),
                                        SlotSet('identification_method', 'keyword'),
                                        SlotSet('transaction_id', transaction_id),
                                        SlotSet('antifraud_rule_id', 'E-9'),
                                        ActionExecuted(f'utter_notifySuspiciousActivity{lang}'), 
                                        ActionExecuted(f'utter_q13{lang}')]
                            
                            elif rule_id in ['6A58C7D7A68F48F1A5E6B7F6D9E0E15C', 'C572DF74331D4129B54FCD051BD97E47', '4ea67607598444f4b938ff888f17422a']:
                                print('заблокирован по правилам E-15* или E-15**')

                                dispatcher.utter_message(response=f'utter_notifySuspiciousActivity{lang}')
                                dispatcher.utter_message(response=f'utter_q25{lang}')
                                
                                log_message = f'заблокирован по правилам E-15* или E-15**'
                                logger.info(log_message)

                                log_handler.close()
                                logger.removeHandler(log_handler)

                                return [SlotSet('identified', identified),
                                        SlotSet('identification_method', 'keyword'),
                                        SlotSet('transaction_id', transaction_id),
                                        SlotSet('antifraud_rule_id', 'E-15'),
                                        ActionExecuted(f'utter_notifySuspiciousActivity{lang}'), 
                                        ActionExecuted(f'utter_q25{lang}')]
                            else:
                                log_message = f'заблокирован по другим правилам:{rule_id}'
                                logger.info(log_message)

                                log_handler.close()
                                logger.removeHandler(log_handler)

                                dispatcher.utter_message(response=f'utter_toOperatorICant{lang}')
                                return [ActionExecuted(f'utter_toOperatorICant{lang}'), ConversationPaused()]
                        attempts += 1

                    log_handler.close()
                    logger.removeHandler(log_handler)

                    dispatcher.utter_message(response=f'utter_toOperator{lang}')
                    return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
                else:
                    log_handler.close()
                    logger.removeHandler(log_handler)

                    return [
                        SlotSet('identified', identified),
                        SlotSet('identification_method', 'keyword'),
                        FollowupAction('action_switchToAnotherScript')
                    ]
            attempts += 1  # увеличиваем количество попыток
            
        log_handler.close()
        logger.removeHandler(log_handler)

        dispatcher.utter_message(response=f'utter_toOperator{lang}')
        return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]


class ActionCardActivation(Action):

    def name(self) -> Text:
        return 'action_cardActivation'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_cardActivation')

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        logger, log_handler = create_logger(tracker)
        log_message = f'RUN Action: action_cardActivation'
        logger.info(log_message)

        lang, last_utter = get_last_utter_and_lang(tracker)

        max_retries = 3
        attempts = 0

        #transaction_id = dict_to_redis['transaction_id']
        transaction_id = tracker.get_slot('transaction_id')
        antifraud_rule_id = tracker.get_slot('antifraud_rule_id')

        try:
            id_home_bank = dict_to_redis['id_home_bank']
        except Exception as e:
            id_home_bank = None
            log_message = f'Error type: {type(e).__name__}\n\t\t\t Message: {str(e)}\n\t\t\t Arguments: {e.args}'
            logger.error(log_message)

        log_message = f'transaction_id: {transaction_id}'\
                      f'consumer_id: {id_home_bank}'
        logger.info(log_message)

        while attempts < max_retries:
            start_time = time.time()
            response = update_activity(transaction_id, id_home_bank, antifraud_rule_id)
            end_time = time.time()

            log_message = f'response: {response.text}'\
                        f'\n\t\t\t request completion time: {end_time - start_time:.2f} sec'
            logger.info(log_message)

            if response is not None and response.status_code == 200:
                data_response = response.json()
                return_text = data_response['return']

                if return_text == 'SUCCESS':
                    log_handler.close()
                    logger.removeHandler(log_handler)

                    dispatcher.utter_message(response = f'utter_thankAndOfferAssistance{lang}')
                    dispatcher.utter_message(response = f'utter_q2{lang}')
                    return [
                            SlotSet('antifraud', False),
                            ActionExecuted(f'utter_thankAndOfferAssistance{lang}'),
                            ActionExecuted(f'utter_q2{lang}'),
                    ]
                else:
                    log_handler.close()
                    logger.removeHandler(log_handler)

                    dispatcher.utter_message(response=f'utter_toOperator{lang}')
                    return [ActionExecuted(f'utter_toOperator{lang}')]

            attempts += 1

        log_handler.close()
        logger.removeHandler(log_handler)

        dispatcher.utter_message(response=f'utter_toOperator{lang}')
        return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]


class ActionReturnIdentText(Action):

    def name(self) -> Text:
        return 'action_returnIdentText'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_returnIdentText')

        events = tracker.events
        all_utters = get_all_utters(events)

        lang, last_utter = get_last_utter_and_lang(tracker)

        # ident = tracker.get_slot('identified')

        # if ident is False:
        #     dispatcher.utter_message(response = f'utter_failedIdentification{lang}')
        # elif ident is True:
        #     dispatcher.utter_message(response = f'utter_successfulIdentification{lang}')

        return [FollowupAction('action_switchToAnotherScript')]


class ActionScore(Action):

    def name(self) -> Text:
        return 'action_score'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_score')

        uuid = tracker.current_state()['sender_id']
        engine_metadata_key = uuid + '-engine_metadata'        
        engine_metadata_record = json.loads(engine_redis.get(engine_metadata_key).decode('utf-8'))

        events = tracker.events
        all_utters = get_all_utters(events)

        lang, last_utter = get_last_utter_and_lang(tracker)
        last_message = tracker.latest_message['text']
        print('last_message:', last_message)

        numbers = ['1', '2', '3', '4', '5']
        convertor_nps = {5: ['отлично', 'прекрасно', 'замечательно', 'очень хорошо', 'керемет', 'өте жақсы', 'күшті'],              
                         4: ['хорошо', 'жақсы'],              
                         3: ['нормально', 'так себе', 'удовлетворительно', 'норм', 'болады', 'орташа'],              
                         2: ['плохо', 'нашар', 'жаман'],              
                         1: ['ужасно', 'отвратительно', 'очень плохо', 'өте нашар', 'өте жаман']}

        score = 0 
        for i in numbers:
            if i in last_message:
                score = int(i)
            else:
                continue
        
        if score == 0:
            for k, v in convertor_nps.items():
                for j in v:
                    if j in last_message:
                        score = k
                        break
                    else:
                        continue
        
        print('Score:', score)

        engine_metadata_record['npl'] = score
        engine_redis.set(engine_metadata_key, json.dumps(engine_metadata_record))

        dispatcher.utter_message(response = f'utter_goodBye{lang}')
        return [ActionExecuted(f'utter_goodBye{lang}'), ConversationPaused()]


class ActionSwitchToAnotherScript(Action):
 
    def name(self) -> Text:
        return 'action_switchToAnotherScript'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_switchToAnotherScript')

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        logger, log_handler = create_logger(tracker)
        log_message = f'RUN Action: action_switchToAnotherScript'
        logger.info(log_message)

        scripttype = tracker.get_slot('intent_to_other_script')
        robot_counter = tracker.get_slot('robot_counter')
        operator_counter = tracker.get_slot('operator_counter')
        local_time = int(time.time())
        
        if robot_counter is None:
            robot_counter = 0

        if operator_counter is None:
            operator_counter = 0

        try:
            all_operator_config = dict_to_redis['all_operator_config']
            operator_number_ru = all_operator_config[scripttype]['operator_number_ru']
            operator_number_kz = all_operator_config[scripttype]['operator_number_kz']
            operator_number_default = all_operator_config[scripttype]['operator_number_default']
        except Exception as e:
            log_message = f'Error type: {type(e).__name__}\n\t\t\t Message: {str(e)}\n\t\t\t Arguments: {e.args}'
            logger.error(log_message)


        # set info about client
        dict_to_redis['client_iin'] = tracker.get_slot('client_iin')
        dict_to_redis['trusted_phone'] = tracker.get_slot('trusted_phone')
        dict_to_redis['antifraud'] = tracker.get_slot('antifraud')
        dict_to_redis['identified'] = tracker.get_slot('identified')
        dict_to_redis['identification_method'] = tracker.get_slot('identification_method')

        csv_path = f'/rasa/dialog_template_halyk_bank_{scripttype}.csv'
        audio_path = f'/mnt/nfs_share/audio_storage/response_sound/halyk_bank_{scripttype}'

        f_lang = dict_to_redis['f_language']

        if f_lang and f_lang[-1] != '': 
            language = f_lang[-1].upper() 
        else: 
            language = dict_to_redis['language'].upper()

        print('Переход на скрипт:', scripttype, flush=True)

        try:
            empty_columns = (check_csv_for_empty_values(csv_path))

            if empty_columns:
                print('Найдены пустые значения в следующих столбцах:', flush=True)
                for column, priorities in empty_columns.items():
                    print (f'- Столбец {column} имеет пустые значения в приоритетах: {priorities}', flush=True)
                    
                    log_message = f'- Столбец {column} имеет пустые значения в приоритетах: {priorities}'
                    logger.info(log_message)
            else:
                print('В файле нет пустых значений.', flush=True)

            data = prepare_dialog(language, csv_path, audio_path)
        except Exception as e:
            print('prepare_dialog не сработал и перевод на оператора')
            dispatcher.utter_message(response=f'utter_toOperator{language}')

            log_message = f'prepare_dialog did not work, script:{scripttype}, call was forwarded to the operator'\
                          f'\n\t\t\t Error type: {type(e).__name__}\n\t\t\t Message: {str(e)}\n\t\t\t Arguments: {e.args}'
            logger.error(log_message)

            log_handler.close()
            logger.removeHandler(log_handler)

            return [ActionExecuted(f'utter_toOperator{language}'), ConversationPaused()]

        # set changed csv, script settings
        data = data.to_dict('records')
        dict_to_redis['data'] = data
        dict_to_redis['name_script'] = f'halyk_bank_{scripttype}'
        dict_to_redis['priority'] = 0
        dict_to_redis['variant'] = 0
        dict_to_redis['priorities_list'] = []
        dict_to_redis['variants_list'] = []
        robot_list = dict_to_redis['robot_list']
        robot_list.append(f'halyk_bank_{scripttype}')
        dict_to_redis['robot_list'] = robot_list
        dict_to_redis['operator_number_ru'] = operator_number_ru
        dict_to_redis['operator_number_kz'] = operator_number_kz
        dict_to_redis['operator_number_default'] = operator_number_default
        dict_to_redis['robot_counter'] = robot_counter
        dict_to_redis['operator_counter'] = operator_counter
        dict_to_redis['robot_durations']['halyk_bank_identification']['end_datetime'] = local_time
        robot_durations = dict_to_redis['robot_durations']
        robot_durations[f'halyk_bank_{scripttype}'] = {'start_datetime': local_time}
        dict_to_redis['robot_durations'] = robot_durations
        engine_redis.set(uuid, json.dumps(dict_to_redis))

        engine_metadata_key = uuid + '-engine_metadata'
        engine_metadata_record = json.loads(engine_redis.get(engine_metadata_key).decode('utf-8'))
        engine_metadata_record['reload_template'] = True
        engine_redis.set(engine_metadata_key, json.dumps(engine_metadata_record))

        log_message = f'Transfer to script: halyk_bank_{scripttype}'
        logger.info(log_message)

        log_handler.close()
        logger.removeHandler(log_handler)

        dispatcher.utter_message(response = f"utter_repeat_question{language}")
        return [ActionExecuted(f'utter_repeat_question{language}')]


class ActionCounterDontKnow(Action):

    def name(self) -> Text:
        return 'action_counterDontKnow'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_counterDontKnow')

        events = tracker.events
        all_utters = get_all_utters(events)

        lang, last_utter = get_last_utter_and_lang(tracker)
        last_4 = all_utters[-4:]
        print(last_4)
        
        a = 0
        for i in last_4:
            if i == 'utter_tryToRememberRU' or i == 'utter_tryToRememberKZ':
                a += 1
            else:
                continue

        print('counter for last utter: ', a)

        if a == 1:
            return [
                SlotSet('identified', False),
                SlotSet('identification_method', 'keyword'),
                FollowupAction('action_switchToAnotherScript')
            ]
        else:
            dispatcher.utter_message(response=f'utter_tryToRemember{lang}')
            dispatcher.utter_message(response=f'utter_q11{lang}')
            return [ActionExecuted(f'utter_tryToRemember{lang}'), ActionExecuted(f'utter_q11{lang}')]


class ActionReturnQ14(Action):

    def name(self) -> Text:
        return 'action_returnq14'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_returnq14')

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        logger, log_handler = create_logger(tracker)
        log_message = f'RUN Action: action_returnq14'
        logger.info(log_message)

        events = tracker.events
        all_utters = get_all_utters(events)

        last_intent = tracker.latest_message['intent']['name']
        lang, last_utter = get_last_utter_and_lang(tracker)

        log_message = f'last_utter: {last_utter}'\
                      f'\n\t\t\t last_intent: {last_intent}'
        logger.info(log_message)

        max_retries = 3
        attempts = 0

        try:
            id_home_bank = dict_to_redis['id_home_bank']
        except Exception as e:
            id_home_bank = None
            log_message = f'Error type: {type(e).__name__}\n\t\t\t Message: {str(e)}\n\t\t\t Arguments: {e.args}'
            logger.error(log_message)

        print('вытаскиваем данные из апи')
        while attempts < max_retries:
            start_time = time.time()
            response = get_antifraud(id_home_bank)
            end_time = time.time()
            print(response, flush=True)

            log_message = f'response: {response.text}'\
                        f'\n\t\t\t request completion time: {end_time - start_time:.2f} sec'
            logger.info(log_message)
            
            log_handler.close()
            logger.removeHandler(log_handler)

            if response is not None and response.status_code == 200:
                data_response = response.json()
                summa = data_response['Сумма транзакции']
                currency = data_response['Валюта транзакции']

                if currency in ['KZT', 'USD', 'EUR']:
                    if lang == 'RU':
                        priority = 75
                    elif lang ==  'KZ':
                        priority = 76

                    summa = int(summa) / 100

                    send_external_audio_summa_q14(priority, lang, summa, currency, tracker)

                    dispatcher.utter_message(response=f'utter_q14text{lang}')
                    dispatcher.utter_message(response=f'utter_summa{lang}', summa=summa)
                    dispatcher.utter_message(response=f'utter_currency{lang}', currency=currency)
                    dispatcher.utter_message(response=f'utter_q14{lang}')
                    
                    return [ActionExecuted(f'utter_q14text{lang}'), ActionExecuted(f'utter_summa{lang}'), ActionExecuted(f'utter_currency{lang}'), ActionExecuted(f'utter_q14{lang}'),]  
                else:
                    dispatcher.utter_message(response=f'utter_toOperatorICant{lang}')
                    return [ActionExecuted(f'utter_toOperatorICant{lang}'), ConversationPaused()]
            attempts += 1

        log_handler.close()
        logger.removeHandler(log_handler)

        dispatcher.utter_message(response=f'utter_toOperator{lang}')
        return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]


class ActionReturnQ15(Action):

    def name(self) -> Text:
        return 'action_returnq15'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_returnq15')

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        logger, log_handler = create_logger(tracker)
        log_message = f'RUN Action: action_returnq15'
        logger.info(log_message)

        events = tracker.events
        all_utters = get_all_utters(events)

        last_intent = tracker.latest_message['intent']['name']
        lang, last_utter = get_last_utter_and_lang(tracker)

        log_message = f'last_utter: {last_utter}'\
                      f'\n\t\t\t last_intent: {last_intent}'
        logger.info(log_message)

        max_retries = 3
        attempts = 0
        
        try:
            id_home_bank = dict_to_redis['id_home_bank']
        except Exception as e:
            id_home_bank = None
            log_message = f'Error type: {type(e).__name__}\n\t\t\t Message: {str(e)}\n\t\t\t Arguments: {e.args}'
            logger.error(log_message)

        print('вытаскиваем данные из апи')
        while attempts < max_retries:
            start_time = time.time()
            response = get_antifraud(id_home_bank)
            end_time = time.time()
            print(response, flush=True)

            log_message = f'response: {response.text}'\
                        f'\n\t\t\t request completion time: {end_time - start_time:.2f} sec'
            logger.info(log_message)
            
            log_handler.close()
            logger.removeHandler(log_handler)

            if response is not None and response.status_code == 200:
                data_response = response.json()
                summa = data_response['Сумма транзакции']
                currency = data_response['Валюта транзакции']
                address = data_response['Город устройства']
                address = re.sub(r'[^\w]', '', address)

                if currency in ['KZT', 'USD', 'EUR']:
                    if lang == 'RU':
                        priority = 81
                    elif lang ==  'KZ':
                        priority = 82

                    summa = int(summa) / 100

                    send_external_audio_summa_q15(priority, lang, summa, currency, address, tracker)

                    dispatcher.utter_message(response=f'utter_q15text{lang}')
                    dispatcher.utter_message(response=f'utter_summa{lang}', summa=summa)
                    dispatcher.utter_message(response=f'utter_currency{lang}', currency=currency)
                    dispatcher.utter_message(response=f'utter_address{lang}', address=address)
                    dispatcher.utter_message(response=f'utter_q15{lang}')
                    
                    return [ActionExecuted(f'utter_q15text{lang}'), ActionExecuted(f'utter_summa{lang}'), ActionExecuted(f'utter_currency{lang}'), ActionExecuted(f'utter_address{lang}'), ActionExecuted(f'utter_q15{lang}'),]  
                else:
                    dispatcher.utter_message(response=f'utter_toOperatorICant{lang}')
                    return [ActionExecuted(f'utter_toOperatorICant{lang}'), ConversationPaused()]
            attempts += 1

        log_handler.close()
        logger.removeHandler(log_handler)

        dispatcher.utter_message(response=f'utter_toOperator{lang}')
        return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]


class ActionAfterQ2(Action):

    def name(self) -> Text:
        return 'action_q2'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_q2')
        
        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']

        intents_utters = {
            'yes': [f'utter_q7{lang}'],
            'whoIsIt': [f'utter_langDetect{lang}', f'utter_q2{lang}'],
            'soundlessly': [f'utter_q3{lang}'],
            'haveQuestion': [f'utter_q7{lang}'],
            'aboutCard': [f'utter_q22{lang}'],
            'aboutLoans': [f'utter_q23{lang}'],
            'interrupting': [f'utter_interrupting{lang}'],
            'another': [f'utter_q6{lang}'],
            'fraud': [f'utter_q6{lang}'],
            'noApplication': [f'utter_q6{lang}'],
        }

        to_other_script = ['loans_mortgage', 'remove_the_limit', 'limits', 'forgot_card', 'reset_pin', 'card_operation', 'current_loan', 'card_delivery', 'credit_card', 
                           'new_loan', 'block_card', 'overdue_debt', 'sysn', 'super_app', 'kino_kz', 'registration', 'payments_and_transfers', 'halyk_travel', 
                           'addresses_branches', 'brokerage', 'blockTheCard', 'unlockIt']

        if last_intent in intents_utters:
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))

            return actions
        elif last_intent in to_other_script:
            if last_intent == 'blockTheCard' or last_intent == 'unlockIt':
                last_intent = 'block_card'
            return [SlotSet('intent_to_other_script', last_intent),
                    FollowupAction('action_switchToAnotherScript'),]
        elif last_intent == 'no':
            dispatcher.utter_message(response = f'utter_goodBye{lang}')
            return [ActionExecuted(f'utter_goodBye{lang}'), ConversationPaused]
        elif last_intent == 'robot':
            return [FollowupAction(f'action_robot')]
        elif last_intent == 'operator':
            return [FollowupAction(f'action_operator')]
        elif last_intent == 'changeLangKZ' or last_intent == 'changeLangRU':
            return [FollowupAction('action_changelang')]
        elif last_intent == 'repeat':
            return [FollowupAction(f'action_repeat')]
        else:
            return [FollowupAction(f'action_counter')]

class ActionAfterQ26(Action):

    def name(self) -> Text:
        return 'action_q26'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_q26')

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        events = tracker.events
        all_utters = get_all_utters(events)

        lang, last_utter = get_last_utter_and_lang(tracker)
        
        last_intent = tracker.latest_message['intent']['name']

        return [FollowupAction(f'action_counter')]
