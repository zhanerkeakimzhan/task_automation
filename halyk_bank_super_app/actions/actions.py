import random
from typing import Any, Text, Dict, List
import yaml
import pandas as pd
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
import requests
from rasa_sdk.events import ActionExecuted, SlotSet, ActiveLoop, FollowupAction, Restarted, ConversationPaused
from actions.test_api_super_app import get_gosusluga_status
from datetime import datetime
import redis
import json
import os
import time
import pytz
import logging


ENVIORENMENT = os.environ.get('ENVIORENMENT', 'dev')


if ENVIORENMENT == "PROD":
    config_file = 'endpoints_prod.yml'
    with open(f"/rasa/{config_file}") as file:
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

def get_all_utters(events: List[Dict[Text, Any]]) -> List[Text]:
    all_utters = []
    for event in events:
        if event['event'] == 'action' and event['name'].startswith('utter_'):
            all_utters.append(event['name'])
    return all_utters

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
                print("Exception")
                # agi.verbose(str(err))
    data.loc[0, 'Language'] = f'Audio{language}'
    return data


def check_intent(last_intent, tracker):
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
        
        return need_ident
    except Exception as e:
        need_ident = True #если не получиться вытащить интент, пройдет идентификацию
        return need_ident


class ActionSwitchToAnotherScript(Action):

    def name(self) -> Text:
        return "action_switchToAnotherScript"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_switchToAnotherScript", flush=True)

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        logger, log_handler = create_logger(tracker)
        log_message = f'RUN Action: action_switchToAnotherScript'
        logger.info(log_message)

        identified = dict_to_redis['identified']
        trusted_phone = dict_to_redis['trusted_phone']
        robot_list = dict_to_redis['robot_list']
        print("identified:", identified, flush=True)
        print("robot_list:", robot_list, flush=True)

        last_intent = tracker.latest_message['intent']['name']
        local_time = int(time.time())
        dont_need_ident = ["kino_kz", "registration", "payments_and_transfers", "halyk_travel", "addresses_branches", "brokerage", "remove_the_limit", "current_loan", "loans_mortgage", "new_loan"]
        need_ident = ['limits', 'block_card'] #тут
        my_intents = ['publicServices'] #тут список своих интентов для которых требуется идент

        f_lang = dict_to_redis['f_language']
        f_lang_last = f_lang[-1]
        if not f_lang_last.strip():
            language = dict_to_redis['language'].upper()
        else:
            language = f_lang_last.upper()

        # if identified is None:  #тут
        #     if last_intent in need_ident or last_intent in my_intents:
        #         scripttype = 'identification'
        #     elif last_intent in dont_need_ident:
        #         scripttype = last_intent
        #     else:
        #         need_ident = check_intent(last_intent, tracker)
        #         if need_ident:
        #             scripttype = 'identification'
        #         else:
        #             scripttype = last_intent
        # else:
        #             scripttype = last_intent

        if last_intent not in dont_need_ident and identified is None and trusted_phone is True:
            if last_intent in need_ident or last_intent in my_intents or check_intent(last_intent, tracker):
                scripttype = 'identification'
            else:
                scripttype = last_intent
        else:
            scripttype = last_intent


        all_operator_config = dict_to_redis['all_operator_config']
        operator_number_ru = all_operator_config[scripttype]['operator_number_ru']
        operator_number_kz = all_operator_config[scripttype]['operator_number_kz']
        operator_number_default = all_operator_config[scripttype]['operator_number_default']

        csv_path = f'/rasa/dialog_template_halyk_bank_{scripttype}.csv'
        audio_path = f'/mnt/nfs_share/audio_storage/response_sound/halyk_bank_{scripttype}'

        try:
            data = prepare_dialog(language, csv_path, audio_path)
        except Exception as e:
            print('prepare_dialog не сработал и перевод на оператора')
            dispatcher.utter_message(response=f'utter_toOperator{language}')

            log_message = f'prepare_dialog did not work, script:{scripttype}, call was forwarded to the operator'\
                          f'\n\t\t\t\t Error type: {type(e).__name__}\n\t\t\t\t Message: {str(e)}\n\t\t\t\t Arguments: {e.args}'
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
        robot_list.append(f'halyk_bank_{scripttype}')
        dict_to_redis['robot_list'] = robot_list
        dict_to_redis['operator_number_ru'] = operator_number_ru
        dict_to_redis['operator_number_kz'] = operator_number_kz
        dict_to_redis['operator_number_default'] = operator_number_default
        dict_to_redis['robot_counter'] = tracker.get_slot('robot_counter')
        dict_to_redis['operator_counter'] = tracker.get_slot('operator_counter')
        dict_to_redis['robot_durations']['halyk_bank_super_app']['end_datetime'] = local_time
        robot_durations = dict_to_redis['robot_durations']
        robot_durations[f'halyk_bank_{scripttype}'] = {'start_datetime': local_time}
        dict_to_redis['robot_durations'] = robot_durations
        engine_redis.set(uuid, json.dumps(dict_to_redis))

        print("After append:", robot_list, flush=True)

        engine_metadata_key = uuid + '-engine_metadata'
        engine_metadata_record = json.loads(engine_redis.get(engine_metadata_key).decode('utf-8'))
        engine_metadata_record['reload_template'] = True
        engine_redis.set(engine_metadata_key, json.dumps(engine_metadata_record))

        log_message = f'Transfer to script: halyk_bank_{scripttype}'
        logger.info(log_message)

        log_handler.close()
        logger.removeHandler(log_handler)

        dispatcher.utter_message(response = f"utter_repeat_question{language}")
        return[ActionExecuted(f'utter_repeat_question{language}')]


class ActionEmpty(Action):

    def name(self) -> Text:
        return "action_empty"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_empty")

        lang, last_utter = get_last_utter_and_lang(tracker)

        return[ActionExecuted(f'utter_q1{lang}')]


class ActionInfoAboutClient(Action):
    def name(self) -> Text:
        return "action_info"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_info")


        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        logger, log_handler = create_logger(tracker)
        log_message = f'Script: halyk_bank_super_app, Action: action_info, uuid: {uuid}'
        logger.info(log_message)

        try:
            client_iin = dict_to_redis['client_iin']
            phone_number = dict_to_redis['phone_number']
            trusted_phone = dict_to_redis['trusted_phone']
            identified = dict_to_redis['identified']
            identification_method = dict_to_redis['identification_method']
            robot_counter = dict_to_redis['robot_counter']
            operator_counter = dict_to_redis['operator_counter']
        except:
            client_iin = None
            trusted_phone = None
            identified = None
            identification_method = None

        log_message = f'INITIAL INFORMATION'\
        f'\n\t\t\t\t trusted_phone: {trusted_phone}'\
        f'\n\t\t\t\t identified: {identified}'\
        f'\n\t\t\t\t identification_method: {identification_method}'\
        f'\n\t\t\t\t client_iin: {client_iin}'\
        f'\n\t\t\t\t robot_counter: {robot_counter}'\
        f'\n\t\t\t\t operator_counter: {operator_counter}'
        logger.info(log_message)

        
        print("phone_number:", phone_number)
        print("client_iin:", client_iin)
        print("trusted_phone:", trusted_phone)
        print("identified:", identified)
        print("identification_method:", identification_method)
        print("robot_counter:", robot_counter)
        print("operator_counter:", operator_counter)

        log_handler.close()
        logger.removeHandler(log_handler)

        return [SlotSet('identification_method', identification_method), 
                SlotSet('identified', identified), 
                SlotSet('trusted_phone', trusted_phone), 
                SlotSet('phone_number', phone_number), 
                SlotSet('client_iin', client_iin),
                SlotSet('robot_counter', robot_counter),
                SlotSet('operator_counter', operator_counter),]


class ActionSlotSet(Action):
    def name(self) -> Text:
        return "action_slotSet"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_slotSet")

        last_intent = tracker.latest_message['intent']['name']

        values_for_general = ["howOpenCard", "howCloseCard", "howReissueCard", "publicServices", ]

        if last_intent in values_for_general:
            return [SlotSet("general", last_intent)]
        else:
            return []


class ActionCheckApplicationStatus(Action):
    def name(self) -> Text:
        return "action_checkApplicationStatus"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_checkApplicationStatus")

        logger, log_handler = create_logger(tracker)
        log_message = f'RUN Action: action_checkApplicationStatus'
        logger.info(log_message)

        lang, last_utter = get_last_utter_and_lang(tracker)

        trusted_phone = tracker.get_slot('trusted_phone')
        identified = tracker.get_slot('identified')
        client_iin = tracker.get_slot('client_iin')

        print(trusted_phone)
        print(identified)

        if trusted_phone is True and identified is True:
            print("Для доверенных/Если успешно пройдена")

            dispatcher.utter_message(response = f"utter_checkInfo{lang}")

            max_retries = 3
            attempts = 0

            while attempts < max_retries:
                start_time = time.time()
                response = get_gosusluga_status(client_iin)
                end_time = time.time()
                
                log_message = f'response: {response.text}'\
                            f'\n\t\t\t\t request completion time: {end_time - start_time:.2f} sec'
                logger.info(log_message)

                if response is not None and response.status_code == 200:
                    data_response = response.json()
                    data = data_response.get('data', [])
                    if data:  # Проверяем, что data не пустой
                        status = data[0].get("status")  # берем статус из нулевого индекса

                        log_message = f'data: {data}'\
                                      f'last_request_status: {status}'
                        logger.info(log_message)

                        log_handler.close()
                        logger.removeHandler(log_handler)

                        approved = ['NEW', 'APPROVED', 'WAITING', 'AGREED',]
                        completed = ['DONE',]
                        wasnt_considered = ['NONE', 'PAID', 'EXPIRED',]

                        if status in approved:
                            return [SlotSet("status", 'approved'), FollowupAction("action_returnQ16")]
                        elif status in completed:
                            return [SlotSet("status", 'completed'), FollowupAction("action_returnQ16")]
                        elif status in wasnt_considered:
                            return [SlotSet("status", 'wasnt_considered'), FollowupAction("action_returnQ16")]
                        elif status == 'DECLINED':
                            dispatcher.utter_message(response = f'utter_statusDeclined{lang}')
                            dispatcher.utter_message(response = f'utter_q2{lang}')
                            return [ActionExecuted(f'utter_statusDeclined{lang}'), ActionExecuted(f'utter_q2{lang}'),]
                        else:
                            
                            log_handler.close()
                            logger.removeHandler(log_handler)

                            dispatcher.utter_message(response = f'utter_toOperator{lang}')
                            return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
                    else:
                        log_message = f'data is empty, transfering to operator'
                        logger.info(log_message)

                        log_handler.close()
                        logger.removeHandler(log_handler)

                        dispatcher.utter_message(response = f'utter_toOperator{lang}')
                        return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]

                attempts += 1  # увеличиваем количество попыток

            log_handler.close()
            logger.removeHandler(log_handler)

            dispatcher.utter_message(response=f'utter_toOperator{lang}')
            return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
        elif trusted_phone is True and identified is False:
            print("Не прошел идентификацию по кодовому слову")
            dispatcher.utter_message(response=f"utter_failedIdentification{lang}")
            dispatcher.utter_message(response=f"utter_q17{lang}")
            return [ActionExecuted(f"utter_failedIdentification{lang}"), ActionExecuted(f"utter_q17{lang}")]
        elif trusted_phone is True and identified is None:
            log_handler.close()
            logger.removeHandler(log_handler)
            return [FollowupAction("action_switchToAnotherScript")]
        else:
            print("Для не доверенных/Не подтвержденный")
            dispatcher.utter_message(response=f"utter_failedIdentUntrustedNumber{lang}")
            dispatcher.utter_message(response=f"utter_q17{lang}")
            return [ActionExecuted(f"utter_failedIdentUntrustedNumber{lang}"), ActionExecuted(f"utter_q17{lang}")]


class ActionReturnQ16(Action):
    def name(self) -> Text:
        return "action_returnQ16"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_returnQ16")

        lang, last_utter = get_last_utter_and_lang(tracker)

        dispatcher.utter_message(response=f"utter_publicServicesStatus{lang}")
        dispatcher.utter_message(response=f"utter_q16{lang}")
        return [ActionExecuted(f"utter_publicServicesStatus{lang}"), ActionExecuted(f"utter_q16{lang}")]


class ActionRepeat(Action):
    def name(self) -> Text:
        return "action_repeat"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        logger, log_handler = create_logger(tracker)
        log_message = f'RUN Action: action_repeat'
        logger.info(log_message)

        events = tracker.events
        responses = get_utters_between_two_intents(events)

        print(responses)
        exception = ["utter_checkInfo", "utter_soundLesslyRU", "utter_soundLesslyKZ"]

        if not responses:
            responses.append("utter_q1RU")

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

        events = tracker.events
        all_utters = get_all_utters(events)

        lang, last_utter = get_last_utter_and_lang(tracker)

        last_3 = all_utters[-3:]
        print(last_3)
        
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

        print('counter for last utter: ', a)

        if a == 3:
            dispatcher.utter_message(response = f'utter_operator{lang}')
            return [ActionExecuted(f'utter_operator{lang}'), ConversationPaused()]
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

        lang, last_utter = get_last_utter_and_lang(tracker)

        for_q5 = ['utter_q1RU', 'utter_q3RU', 'utter_q4RU', 'utter_q7RU', 'utter_q1KZ', 'utter_q3KZ', 'utter_q4KZ', 'utter_q7KZ', 'utter_interruptingRU', 'utter_interruptingKZ']

        operator = tracker.get_slot('operator_counter')
        if operator is None:
            operator = 0
        print('operator_counter before append:', operator)

        log_message = f'operator_counter_before_append: {operator}'
        logger.info(log_message)

        if operator > 0:
                log_message = f'-- operator > 0 -- logic has worked, call was forwarded to the operator'
                logger.info(log_message)

                log_handler.close()
                logger.removeHandler(log_handler)

                dispatcher.utter_message(response = f'utter_toOperator{lang}')
                return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
        else:
            if last_utter in for_q5:
                dispatcher.utter_message(response= f'utter_q5{lang}')

                operator += 1
                print('operator_counter after append:', operator)

                log_message = f'operator_counter_after_append: {operator}'
                logger.info(log_message)

                log_handler.close()
                logger.removeHandler(log_handler)

                return [SlotSet('operator_counter', operator), ActionExecuted(f'utter_q5{lang}')]
            else:
                dispatcher.utter_message(response = f'utter_justOperator{lang}')
                dispatcher.utter_message(response = last_utter)

                operator += 1
                print('operator_counter after append:', operator)

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
        
        logger, log_handler = create_logger(tracker)
        log_message = f'RUN Action: action_robot'
        logger.info(log_message)

        lang, last_utter = get_last_utter_and_lang(tracker)

        last_intent = tracker.latest_message['intent']['name']
        print('last utter:', last_utter)
        print('last intent:', last_intent)

        exceptions = ['utter_q4RU', 'utter_q3RU', 'utter_q5RU', 'utter_q7RU','utter_q4KZ', 'utter_q3KZ', 'utter_q5KZ', 'utter_q7KZ', 'utter_interruptingRU', 'utter_interruptingKZ']

        if last_utter in exceptions:
            last_utter = f'utter_q1{lang}'

        robot = tracker.get_slot('robot_counter')
        if robot is None:
            robot = 0
        print('robot_counter before append:', robot)

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
        return "action_changelang"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_changelang")

        events = tracker.events
        all_utters = get_utters_between_two_intents(events)
        
        print(all_utters)

        last_intent = tracker.latest_message['intent']['name']

        lang = last_intent[-2:]
        print("перевод на этот язык:", lang)

        exceptions = ["utter_checkInfo", "utter_soundLesslyRU", "utter_soundLesslyKZ"]

        if not all_utters:
            all_utters.append("utter_q1RU")

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
        
        # print(returns)

        return returns

class ActionAfterQ0(Action):

    def name(self) -> Text:
        return "action_q0"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q0")

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        logger, log_handler = create_logger(tracker)
        log_message = f'RUN Action: action_q0'
        logger.info(log_message)

        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']

        print("last utter:", last_utter)
        print("last intent:", last_intent)

        identified = tracker.get_slot('identified')
        robot_list = dict_to_redis['robot_list']

        print('robot_list:', robot_list)

        if robot_list[-2] == 'halyk_bank_identification' and identified is True:
            dispatcher.utter_message(response=f'utter_successfulIdentification{lang}')
        elif robot_list[-2] == 'halyk_bank_identification' and identified is False:
            dispatcher.utter_message(response=f'utter_failedIdentificationFirst{lang}')

        intents_utters = {
            "changeLangKZ": ["utter_q1KZ"],
            "changeLangRU": ["utter_q1RU"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q1{lang}"],
            "soundlessly": [f"utter_q3{lang}"],
            "haveQuestion": [f"utter_q7{lang}"],
            "no": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "dontKnow": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "callBack": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "whatIsTrustNumber": [f"utter_aboutTrustedNumber{lang}",f"utter_q2{lang}"],
            "later": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "bankBrunch": [f"tter_brunchAddress{lang}",f"utter_q2{lang}"],
            "brunchAddress": [f"tter_brunchAddress{lang}",f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "internet": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "howOpenCard": [f"utter_openCardOptions{lang}",f"utter_q8{lang}"],
            "howCloseCard": [f"utter_howCloseCard{lang}",f"utter_q19{lang}"],
            "howReissueCard": [f"utter_howReissueCard{lang}",f"utter_q12{lang}"],
            "howMakeRefund": [f"utter_q15{lang}"],
            "callCenter": [f"utter_callCenter{lang}",f"utter_q2{lang}"],
            "returnedTheProduct": [f"utter_returnedTheProduct{lang}",f"utter_q2{lang}"],
            "interrupting": [f"utter_interrupting{lang}"],
        }

        to_another_script = {"loans_mortgage", "remove_the_limit", "limits", "forgot_card", "reset_pin", "card_operation", "current_loan", "card_delivery", "credit_card", "new_loan", 
                             "block_card", "overdue_debt", "sysn", "super_app", "kino_kz", "registration", "payments_and_transfers", "halyk_travel", "addresses_branches", "brokerage", }

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))
            
            log_handler.close()
            logger.removeHandler(log_handler)

            return actions
        elif last_intent == 'another':
            dispatcher.utter_message(response = f'utter_toOperator{lang}')
            
            log_handler.close()
            logger.removeHandler(log_handler)

            return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
        elif last_intent in to_another_script:
            dispatcher.utter_message(response = f'utter_q1{lang}')
            
            log_handler.close()
            logger.removeHandler(log_handler)

            return [ActionExecuted(f'utter_q1{lang}')]
        elif last_intent == "publicServices":
            
            log_handler.close()
            logger.removeHandler(log_handler)

            return [FollowupAction("action_checkApplicationStatus")]
        elif last_intent == "robot":
            
            log_handler.close()
            logger.removeHandler(log_handler)

            return [FollowupAction(f"action_robot")]
        elif last_intent == "operator":
            
            log_handler.close()
            logger.removeHandler(log_handler)

            return [FollowupAction(f"action_operator")]
        else:
            return [FollowupAction(f"action_counter")]


class ActionAfterQ1(Action):

    def name(self) -> Text:
        return "action_q1"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q1")

        lang, last_utter = get_last_utter_and_lang(tracker)

        last_intent = tracker.latest_message['intent']['name']

        print("last utter:", last_utter)
        print("last intent:", last_intent)

        intents_utters = {
            "changeLangKZ": ["utter_q1KZ"],
            "changeLangRU": ["utter_q1RU"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q1{lang}"],
            "soundlessly": [f"utter_q3{lang}"],
            "haveQuestion": [f"utter_q7{lang}"],
            "no": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "dontKnow": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "callBack": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "whatIsTrustNumber": [f"utter_aboutTrustedNumber{lang}",f"utter_q2{lang}"],
            "later": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "bankBrunch": [f"tter_brunchAddress{lang}",f"utter_q2{lang}"],
            "brunchAddress": [f"tter_brunchAddress{lang}",f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "internet": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "howOpenCard": [f"utter_openCardOptions{lang}",f"utter_q8{lang}"],
            "howCloseCard": [f"utter_howCloseCard{lang}",f"utter_q19{lang}"],
            "howReissueCard": [f"utter_howReissueCard{lang}",f"utter_q12{lang}"],
            "howMakeRefund": [f"utter_q15{lang}"],
            "callCenter": [f"utter_callCenter{lang}",f"utter_q2{lang}"],
            "returnedTheProduct": [f"utter_returnedTheProduct{lang}",f"utter_q2{lang}"],
            "interrupting": [f"utter_interrupting{lang}"],
        }

        to_another_script = {"loans_mortgage", "remove_the_limit", "limits", "forgot_card", "reset_pin", "card_operation", "current_loan", "card_delivery", "credit_card", "new_loan", 
                             "block_card", "overdue_debt", "sysn", "super_app", "kino_kz", "registration", "payments_and_transfers", "halyk_travel", "addresses_branches", "brokerage", }

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))
            
            return actions
        elif last_intent == 'another':
            dispatcher.utter_message(response = f'utter_toOperator{lang}')
            return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
        elif last_intent in to_another_script:
            return [FollowupAction("action_switchToAnotherScript")]
        elif last_intent == "publicServices":
            return [FollowupAction("action_checkApplicationStatus")]
        elif last_intent == "robot":
            return [FollowupAction(f"action_robot")]
        elif last_intent == "operator":
            return [FollowupAction(f"action_operator")]
        else:
            return [FollowupAction(f"action_counter")]


class ActionAfterQ2(Action):

    def name(self) -> Text:
        return "action_q2"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q2")
        
        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']

        intents_utters = {
            "yes": [f"utter_q7{lang}"],
            "no": [f"utter_score{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q2{lang}"],
            "haveQuestion": [f"utter_q7{lang}"],
            "dontKnow": [f"utter_score{lang}"],
            "callBack": [f"utter_score{lang}"],
            "whatIsTrustNumber": [f"utter_aboutTrustedNumber{lang}",f"utter_q2{lang}"],
            "later": [f"utter_score{lang}"],
            "bankBrunch": [f"utter_brunchAddress{lang}",f"utter_q2{lang}"],
            "brunchAddress": [f"utter_brunchAddress{lang}",f"utter_q2{lang}"],
            "busy": [f"utter_score{lang}"],
            "howOpenCard": [f"utter_openCardOptions{lang}",f"utter_q8{lang}"],
            "howCloseCard": [f"utter_howCloseCard{lang}",f"utter_q19{lang}"],
            "howReissueCard": [f"utter_howReissueCard{lang}",f"utter_q12{lang}"],
            "howMakeRefund": [f"utter_q15{lang}"],
            "callCenter": [f"utter_callCenter{lang}",f"utter_q2{lang}"],
            "returnedTheProduct": [f"utter_returnedTheProduct{lang}",f"utter_q2{lang}"],
            "interrupting": [f"utter_interrupting{lang}"],
        }

        to_another_script = {"loans_mortgage", "remove_the_limit", "limits", "forgot_card", "reset_pin", "card_operation", "current_loan", "card_delivery", "credit_card", "new_loan", 
                             "block_card", "overdue_debt", "sysn", "super_app", "kino_kz", "registration", "payments_and_transfers", "halyk_travel", "addresses_branches", "brokerage", }

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))
            
            return actions
        elif last_intent == 'another':
            dispatcher.utter_message(response = f'utter_toOperator{lang}')
            return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
        elif last_intent in to_another_script:
            return [FollowupAction("action_switchToAnotherScript")]
        elif last_intent == "publicServices":
            return [FollowupAction("action_checkApplicationStatus")]
        elif last_intent == "repeat":
            return [FollowupAction("action_repeat")]
        elif last_intent == "robot":
            return [FollowupAction("action_robot")]
        elif last_intent == "soundlessly":
            dispatcher.utter_message(response = f"utter_soundLessly{lang}")
            return [ActionExecuted(f"utter_soundLessly{lang}"), FollowupAction("action_repeat")]
        elif last_intent == "operator":
            return [FollowupAction("action_operator")]
        elif last_intent == "changeLangKZ" or last_intent == "changeLangRU":
            return [FollowupAction("action_changelang")]
        else:
            return [FollowupAction("action_counter")]


class ActionAfterQ3(Action):

    def name(self) -> Text:
        return "action_q3"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q3")

        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']

        intents_utters = {
            "changeLangKZ": ["utter_q1KZ"],
            "changeLangRU": ["utter_q1RU"],
            "yes": [f"utter_q1{lang}"],
            "no": [f"utter_q1{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q1{lang}"],
            "haveQuestion": [f"utter_q7{lang}"],
            "dontKnow": [f"utter_q1{lang}"],
            "callBack": [f"utter_q1{lang}"],
            "howOpenCard": [f"utter_openCardOptions{lang}",f"utter_q8{lang}"],
            "howCloseCard": [f"utter_howCloseCard{lang}",f"utter_q19{lang}"],
            "howReissueCard": [f"utter_howReissueCard{lang}",f"utter_q12{lang}"],
            "howMakeRefund": [f"utter_q15{lang}"],
            "callCenter": [f"utter_callCenter{lang}",f"utter_q2{lang}"],
            "returnedTheProduct": [f"utter_returnedTheProduct{lang}",f"utter_q2{lang}"],
            "interrupting": [f"utter_interrupting{lang}"],
        }

        to_another_script = {"loans_mortgage", "remove_the_limit", "limits", "forgot_card", "reset_pin", "card_operation", "current_loan", "card_delivery", "credit_card", "new_loan", 
                             "block_card", "overdue_debt", "sysn", "super_app", "kino_kz", "registration", "payments_and_transfers", "halyk_travel", "addresses_branches", "brokerage", }

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))
            
            return actions
        elif last_intent == 'another':
            dispatcher.utter_message(response = f'utter_toOperator{lang}')
            return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
        elif last_intent in to_another_script:
            return [FollowupAction("action_switchToAnotherScript")]
        elif last_intent == "publicServices":
            return [FollowupAction("action_checkApplicationStatus")]
        elif last_intent == "robot":
            return [FollowupAction("action_robot")]
        elif last_intent == "operator":
            return [FollowupAction("action_operator")]
        else:
            return [FollowupAction("action_counter")]

#q4, q5, q7
class ActionQuestions(Action):

    def name(self) -> Text:
        return "action_questions"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_questions")
        
        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']

        intents_utters = {
            "changeLangKZ": ["utter_q1KZ"],
            "changeLangRU": ["utter_q1RU"],
            "repeat": [f"utter_q1{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q1{lang}"],
            "soundlessly": [f"utter_q3{lang}"],
            "haveQuestion": [f"utter_q7{lang}"],
            "howOpenCard": [f"utter_openCardOptions{lang}",f"utter_q8{lang}"],
            "howCloseCard": [f"utter_howCloseCard{lang}",f"utter_q19{lang}"],
            "howReissueCard": [f"utter_howReissueCard{lang}",f"utter_q12{lang}"],
            "howMakeRefund": [f"utter_q15{lang}"],
            "callCenter": [f"utter_callCenter{lang}",f"utter_q2{lang}"],
            "returnedTheProduct": [f"utter_returnedTheProduct{lang}",f"utter_q2{lang}"],
            "interrupting": [f"utter_interrupting{lang}"],
        }

        to_another_script = {"loans_mortgage", "remove_the_limit", "limits", "forgot_card", "reset_pin", "card_operation", "current_loan", "card_delivery", "credit_card", "new_loan", 
                             "block_card", "overdue_debt", "sysn", "super_app", "kino_kz", "registration", "payments_and_transfers", "halyk_travel", "addresses_branches", "brokerage", }

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))
            
            return actions
        elif last_intent == 'another':
            dispatcher.utter_message(response = f'utter_toOperator{lang}')
            return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
        elif last_intent in to_another_script:
            return [FollowupAction("action_switchToAnotherScript")]
        elif last_intent == "publicServices":
            return [FollowupAction(f"action_checkApplicationStatus")]
        elif last_intent == "robot":
            return [FollowupAction("action_robot")]
        elif last_intent == "operator":
            return [FollowupAction("action_operator")]
        else:
            return[FollowupAction("action_counter")]


class ActionAfterQ8(Action):

    def name(self) -> Text:
        return "action_q8"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q8")
        
        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']

        intents_utters = {
            "yes": [f"utter_instructions{lang}", f"utter_phoneSupport{lang}", f"utter_q9{lang}"],
            "no": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q8{lang}"],
            "haveQuestion": [f"utter_q7{lang}"],
            "callBack": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "later": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "bankBrunch": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "brunchAddress": [f"utter_brunchAddress{lang}",f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "knowHow": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "howCloseCard": [f"utter_howCloseCard{lang}",f"utter_q19{lang}"],
            "howReissueCard": [f"utter_howReissueCard{lang}",f"utter_q12{lang}"],
            "howMakeRefund": [f"utter_q15{lang}"],
            "needPlasticCard": [f"utter_needPlasticCard{lang}", f"utter_q8{lang}"],
            "specialCard": [f"utter_specialCard{lang}", f"utter_q2{lang}"],
            "callCenter": [f"utter_callCenter{lang}",f"utter_q2{lang}"],
            "returnedTheProduct": [f"utter_returnedTheProduct{lang}",f"utter_q2{lang}"],
            "interrupting": [f"utter_interrupting{lang}"],
        }

        to_another_script = {"loans_mortgage", "remove_the_limit", "limits", "forgot_card", "reset_pin", "card_operation", "current_loan", "card_delivery", "credit_card", "new_loan", 
                             "block_card", "overdue_debt", "sysn", "super_app", "kino_kz", "registration", "payments_and_transfers", "halyk_travel", "addresses_branches", "brokerage", }

        to_oper = ['dontKnow', 'internet']

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))
            
            return actions
        elif last_intent in to_oper:
            dispatcher.utter_message(response = f"utter_toOperatorICant{lang}")
            return [ActionExecuted(f"utter_toOperatorICant{lang}"), ConversationPaused()]
        elif last_intent in to_another_script:
            return [FollowupAction("action_switchToAnotherScript")]
        elif last_intent == "publicServices":
            return [FollowupAction("action_checkApplicationStatus")]
        elif last_intent == "repeat":
            return [FollowupAction("action_repeat")]
        elif last_intent == "robot":
            return [FollowupAction("action_robot")]
        elif last_intent == "soundlessly":
            dispatcher.utter_message(response = f"utter_soundLessly{lang}")
            return [ActionExecuted(f"utter_soundLessly{lang}"), FollowupAction("action_repeat")]
        elif last_intent == "operator":
            return [FollowupAction("action_operator")]
        elif last_intent == "changeLangKZ" or last_intent == "changeLangRU":
            return [FollowupAction("action_changelang")]
        else:
            return [FollowupAction("action_counter")]


class ActionAfterQ9(Action):

    def name(self) -> Text:
        return "action_q9"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q9")
        
        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']

        intents_utters = {
            "changeLangRU": ["utter_q9RU"],
            "changeLangKZ": ["utter_q9KZ"],
            "yes": [f"utter_waitingInLine{lang}", f"utter_q10{lang}"],
            "knowHow": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "no": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "repeat": [f"utter_repeatInstructions{lang}",f"utter_q11{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q9{lang}"],
            "soundlessly": [f"utter_soundLessly{lang}", f"utter_q9{lang}"],
            "callBack": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "later": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "bankBrunch": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}",f"utter_q2{lang}"],
        }

        to_oper = ['dontKnow', 'internet']

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))
            
            return actions
        elif last_intent in to_oper:
            dispatcher.utter_message(response = f"utter_toOperatorICant{lang}")
            return [ActionExecuted(f"utter_toOperatorICant{lang}"), ConversationPaused()]
        elif last_intent == "robot":
            return [FollowupAction("action_robot")]
        elif last_intent == "operator":
            return [FollowupAction("action_operator")]
        else:
            return [FollowupAction("action_counter")]


class ActionAfterQ10(Action):

    def name(self) -> Text:
        return "action_q10"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q10")
        
        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']

        intents_utters = {
            "changeLangRU": ["utter_q10RU"],
            "changeLangKZ": ["utter_q10KZ"],
            "yes": [f"utter_q11{lang}"],
            "no": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "repeat": [f"utter_repeatInstructions{lang}",f"utter_q11{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q10{lang}"],
            "soundlessly": [f"utter_soundLessly{lang}", f"utter_q10{lang}"],
            "callBack": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "later": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "bankBrunch": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "knowHow": [f"utter_understood{lang}",f"utter_q2{lang}"],
        }

        to_oper = ['dontKnow', 'internet']

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))
            
            return actions
        elif last_intent in to_oper:
            dispatcher.utter_message(response = f"utter_toOperatorICant{lang}")
            return [ActionExecuted(f"utter_toOperatorICant{lang}"), ConversationPaused()]
        elif last_intent == "robot":
            return [FollowupAction("action_robot")]
        elif last_intent == "operator":
            return [FollowupAction("action_operator")]
        else:
            return [FollowupAction("action_counter")]


class ActionAfterQ11(Action):

    def name(self) -> Text:
        return "action_q11"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q11")
        
        events = tracker.events
        all_utters = get_all_utters(events)

        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']

        last_3 = all_utters[-6:]
        print(last_3)

        counter = 0
        for action in last_3:
            if action ==  f"utter_awaiting{lang}":
                counter += 1
            else:
                continue
        print("Counter:", counter)

        intents_utters = {
            "changeLangRU": ["utter_q11RU"],
            "changeLangKZ": ["utter_q11KZ"],
            "yes": [f"utter_good{lang}",f"utter_q2{lang}"],
            "repeat": [f"utter_repeatInstructions{lang}",f"utter_q11{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q11{lang}"],
            "soundlessly": [f"utter_soundLessly{lang}", f"utter_q11{lang}"],
            "callBack": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "later": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "bankBrunch": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "knowHow": [f"utter_understood{lang}",f"utter_q2{lang}"],
        }

        to_oper = ['dontKnow', 'no']

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))
            
            return actions
        elif last_intent in to_oper:
            dispatcher.utter_message(response = f"utter_toOperatorICant{lang}")
            return [ActionExecuted(f"utter_toOperatorICant{lang}"), ConversationPaused()]
        elif last_intent == "internet":
            slot = tracker.get_slot("general")
            if slot == "howReissueCard":
                dispatcher.utter_message(response = f"utter_q14{lang}")
                return [ActionExecuted(f"utter_q14{lang}")]
            else:
                dispatcher.utter_message(response = f"utter_toOperatorICant{lang}")
                return [ActionExecuted(f"utter_toOperatorICant{lang}"), ConversationPaused()]
        elif last_intent == "robot":
            return [FollowupAction("action_robot")]
        elif last_intent == "operator":
            return [FollowupAction("action_operator")]
        else:
            if counter == 3:
                dispatcher.utter_message(response = f"utter_toOperatorICant{lang}")
                return [ActionExecuted(f"utter_toOperatorICant{lang}"), ConversationPaused()]
            else:
                dispatcher.utter_message(response = f"utter_waiting{lang}")
                dispatcher.utter_message(response = f"utter_q11{lang}")
                return(ActionExecuted(f"utter_waiting{lang}"), ActionExecuted(f"utter_q11{lang}"))


class ActionAfterQ12(Action):

    def name(self) -> Text:
        return "action_q12"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q12")
        
        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']

        intents_utters = {
            "yes": [f"utter_instructions{lang}", f"utter_q9{lang}"],
            "no": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q12{lang}"],
            "haveQuestion": [f"utter_q7{lang}"],
            "callBack": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "later": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "bankBrunch": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "brunchAddress": [f"utter_brunchAddress{lang}",f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "knowHow": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "howOpenCard": [f"utter_openCardOptions{lang}",f"utter_q8{lang}"],
            "howCloseCard": [f"utter_howCloseCard{lang}",f"utter_q19{lang}"],
            "howMakeRefund": [f"utter_q15{lang}"],
            "needPlasticCard": [f"utter_needPlasticCard{lang}", f"utter_q8{lang}"],
            "specialCard": [f"utter_specialCard{lang}", f"utter_q2{lang}"],
            "justUnlock": [f"utter_justUnlock{lang}", f"utter_q12{lang}"],
            "specialCard": [f"utter_specialCard{lang}", f"utter_q2{lang}"],
            "willCardStayWithMe": [f"cardReplacementOptions{lang}",f"utter_q2{lang}"],
            "returnedTheProduct": [f"utter_returnedTheProduct{lang}",f"utter_q2{lang}"],
            "interrupting": [f"utter_interrupting{lang}"],
        }

        to_another_script = {"loans_mortgage", "remove_the_limit", "limits", "forgot_card", "reset_pin", "card_operation", "current_loan", "card_delivery", "credit_card", "new_loan", 
                             "block_card", "overdue_debt", "sysn", "super_app", "kino_kz", "registration", "payments_and_transfers", "halyk_travel", "addresses_branches", "brokerage", }

        to_oper = ['dontKnow', 'internet']

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))
            
            return actions
        elif last_intent in to_oper:
            dispatcher.utter_message(response = f"utter_toOperatorICant{lang}")
            return [ActionExecuted(f"utter_toOperatorICant{lang}"), ConversationPaused()]
        elif last_intent in to_another_script:
            return [FollowupAction("action_switchToAnotherScript")]
        elif last_intent == "publicServices":
            return [FollowupAction("action_checkApplicationStatus")]
        elif last_intent == "repeat":
            return [FollowupAction("action_repeat")]
        elif last_intent == "robot":
            return [FollowupAction("action_robot")]
        elif last_intent == "soundlessly":
            dispatcher.utter_message(response = f"utter_soundLessly{lang}")
            return [ActionExecuted(f"utter_soundLessly{lang}"), FollowupAction("action_repeat")]
        elif last_intent == "operator":
            return [FollowupAction("action_operator")]
        elif last_intent == "changeLangKZ" or last_intent == "changeLangRU":
            return [FollowupAction("action_changelang")]
        else:
            return [FollowupAction("action_counter")]


class ActionAfterQ14(Action):

    def name(self) -> Text:
        return "action_q14"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q14")
        
        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']

        intents_utters = {
            "changeLangRU": ["utter_q14RU"],
            "changeLangKZ": ["utter_q14KZ"],
            "yes": [f"utter_veryGood{lang}",f"utter_q2{lang}"],
            "repeat": [f"utter_silence{lang}",f"utter_q14{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q14{lang}"],
            "soundlessly": [f"utter_soundLessly{lang}", f"utter_q14{lang}"],
            "callBack": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "later": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "bankBrunch": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "knowHow": [f"utter_understood{lang}",f"utter_q2{lang}"],
        }

        to_oper = ['dontKnow', 'internet', 'no']

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))
            
            return actions
        elif last_intent in to_oper:
            dispatcher.utter_message(response = f"utter_toOperatorICant{lang}")
            return [ActionExecuted(f"utter_toOperatorICant{lang}"), ConversationPaused()]
        elif last_intent == "robot":
            return [FollowupAction("action_robot")]
        elif last_intent == "operator":
            return [FollowupAction("action_operator")]
        else:
            return [FollowupAction("action_counter")]


class ActionAfterQ15(Action):

    def name(self) -> Text:
        return "action_q15"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q15")
        
        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']

        intents_utters = {
            "changeLangRU": ["utter_q15RU"],
            "changeLangKZ": ["utter_q15KZ"],
            "repeat": [f"utter_silence{lang}", f"utter_q15{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q15{lang}"],
            "soundlessly": [f"utter_soundLessly{lang}", f"utter_q15{lang}"],
            "haveQuestion": [f"utter_q7{lang}"],
            "dontKnow": [f"utter_dontKnowTypeLoan{lang}",f"utter_q2{lang}"],
            "brunchAddress": [f"utter_brunchAddress{lang}",f"utter_q2{lang}"],
            "howOpenCard": [f"utter_openCardOptions{lang}",f"utter_q8{lang}"],
            "howCloseCard": [f"utter_howCloseCard{lang}",f"utter_q19{lang}"],
            "howReissueCard": [f"utter_howReissueCard{lang}",f"utter_q12{lang}"],
            "cashLoan": [f"utter_cashLoan{lang}",f"utter_q2{lang}"],
            "commodityLoan": [f"utter_commodityLoan{lang}",f"utter_q2{lang}"],
            "bothLoans": [f"utter_bothLoans{lang}",f"utter_q2{lang}"],
            "dontKnowTypeLoan": [f"utter_dontKnowTypeLoan{lang}",f"utter_q2{lang}"],
            "returnedTheProduct": [f"utter_returnedTheProduct{lang}",f"utter_q2{lang}"],
            "interrupting": [f"utter_interrupting{lang}"],
        }

        to_another_script = {"loans_mortgage", "remove_the_limit", "limits", "forgot_card", "reset_pin", "card_operation", "current_loan", "card_delivery", "credit_card", "new_loan", 
                             "block_card", "overdue_debt", "sysn", "super_app", "kino_kz", "registration", "payments_and_transfers", "halyk_travel", "addresses_branches", "brokerage", }

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))
            
            return actions
        elif last_intent in to_another_script:
            return [FollowupAction("action_switchToAnotherScript")]
        elif last_intent == "publicServices":
            return [FollowupAction("action_checkApplicationStatus")]
        elif last_intent == "robot":
            return [FollowupAction("action_robot")]
        elif last_intent == "operator":
            return [FollowupAction("action_operator")]
        else:
            return [FollowupAction("action_counter")]


class ActionAfterQ16(Action):

    def name(self) -> Text:
        return "action_q16"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q16")
        
        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']

        intents_utters = {
            "yes": [f"utter_next{lang}",f"utter_q2{lang}"],
            "no": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q2{lang}"],
            "dontKnow": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "callBack": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "later": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "bankBrunch": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "knowHow": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "whyRefused": [f"utter_whyRefused{lang}",f"utter_q2{lang}"],
            "whenApprovalCome": [f"utter_whenApprovalCome{lang}",f"utter_q2{lang}"],
        }

        to_another_script = {"loans_mortgage", "remove_the_limit", "limits", "forgot_card", "reset_pin", "card_operation", "current_loan", "card_delivery", "credit_card", "new_loan", 
                             "block_card", "overdue_debt", "sysn", "super_app", "kino_kz", "registration", "payments_and_transfers", "halyk_travel", "addresses_branches", "brokerage", }

        to_oper = ['internet']

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))
            
            return actions
        elif last_intent in to_oper:
            dispatcher.utter_message(response = f"utter_toOperatorICant{lang}")
            return [ActionExecuted(f"utter_toOperatorICant{lang}"), ConversationPaused()]
        elif last_intent in to_another_script:
            return [FollowupAction("action_switchToAnotherScript")]
        elif last_intent == "repeat":
            return [FollowupAction("action_repeat")]
        elif last_intent == "robot":
            return [FollowupAction("action_robot")]
        elif last_intent == "soundlessly":
            dispatcher.utter_message(response = f"utter_soundLessly{lang}")
            return [ActionExecuted(f"utter_soundLessly{lang}"), FollowupAction("action_repeat")]
        elif last_intent == "operator":
            return [FollowupAction("action_operator")]
        elif last_intent == "changeLangKZ" or last_intent == "changeLangRU":
            return [FollowupAction("action_changelang")]
        else:
            return [FollowupAction("action_counter")]


class ActionAfterQ17(Action):

    def name(self) -> Text:
        return "action_q17"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q17")
        
        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']

        intents_utters = {
            "yes": [f"utter_instructions{lang}",f"utter_q9{lang}"],
            "no": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q17{lang}"],
            "callBack": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "later": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "bankBrunch": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "knowHow": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "whatIsTrustNumber": [f"utter_aboutTrustedNumber{lang}",f"utter_q18{lang}"],
        }

        to_another_script = {"loans_mortgage", "remove_the_limit", "limits", "forgot_card", "reset_pin", "card_operation", "current_loan", "card_delivery", "credit_card", "new_loan", 
                             "block_card", "overdue_debt", "sysn", "super_app", "kino_kz", "registration", "payments_and_transfers", "halyk_travel", "addresses_branches", "brokerage", }

        to_oper = ['dontKnow', 'internet']

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))
            
            return actions
        elif last_intent in to_oper:
            dispatcher.utter_message(response = f"utter_toOperatorICant{lang}")
            return [ActionExecuted(f"utter_toOperatorICant{lang}"), ConversationPaused()]
        elif last_intent in to_another_script:
            return [FollowupAction("action_switchToAnotherScript")]
        elif last_intent == "repeat":
            return [FollowupAction("action_repeat")]
        elif last_intent == "robot":
            return [FollowupAction("action_robot")]
        elif last_intent == "soundlessly":
            dispatcher.utter_message(response = f"utter_soundLessly{lang}")
            return [ActionExecuted(f"utter_soundLessly{lang}"), FollowupAction("action_repeat")]
        elif last_intent == "operator":
            return [FollowupAction("action_operator")]
        elif last_intent == "changeLangKZ" or last_intent == "changeLangRU":
            return [FollowupAction("action_changelang")]
        else:
            return [FollowupAction("action_counter")]


class ActionAfterQ18(Action):

    def name(self) -> Text:
        return "action_q18"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q18")
        
        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']

        intents_utters = {
            "yes": [f"utter_changeTrustedNumber{lang}",f"utter_q2{lang}"],
            "no": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q18{lang}"],
            "callBack": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "later": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "bankBrunch": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "knowHow": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "logInWithTrustedNumber": [f"utter_logInWithTrustedNumber{lang}",f"utter_q17{lang}"],
        }

        to_oper = ['dontKnow', 'internet']

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))
            
            return actions
        elif last_intent in to_oper:
            dispatcher.utter_message(response = f"utter_toOperatorICant{lang}")
            return [ActionExecuted(f"utter_toOperatorICant{lang}"), ConversationPaused()]
        elif last_intent == "repeat":
            return [FollowupAction("action_repeat")]
        elif last_intent == "robot":
            return [FollowupAction("action_robot")]
        elif last_intent == "soundlessly":
            dispatcher.utter_message(response = f"utter_soundLessly{lang}")
            return [ActionExecuted(f"utter_soundLessly{lang}"), FollowupAction("action_repeat")]
        elif last_intent == "operator":
            return [FollowupAction("action_operator")]
        elif last_intent == "changeLangKZ" or last_intent == "changeLangRU":
            return [FollowupAction("action_changelang")]
        else:
            return [FollowupAction("action_counter")]


class ActionAfterQ19(Action):

    def name(self) -> Text:
        return "action_q19"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q19")
        
        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']

        intents_utters = {
            "changeLangRU": ["utter_howCloseCardRU", "utter_q19RU"],
            "changeLangKZ": ["utter_howCloseCardKZ", "utter_q19KZ"],
            "yes": [f"utter_cardClosureConditions{lang}", f"utter_q20{lang}"],
            "waysCloseCard": [f"utter_cardClosureConditions{lang}", f"utter_q20{lang}"],
            "repeat": [f"utter_howCloseCard{lang}", f"utter_q19{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q19{lang}"],
            "soundlessly": [f"utter_soundLessly{lang}", f"utter_howCloseCard{lang}", f"utter_q19{lang}"],
            "haveQuestion": [f"utter_q7{lang}"],
            "dontKnow": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "later": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "bankBrunch": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "brunchAddress": [f"utter_brunchAddress{lang}",f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "knowHow": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "howOpenCard": [f"utter_openCardOptions{lang}",f"utter_q8{lang}"],
            "howCloseCard": [f"utter_howCloseCard{lang}",f"utter_q19{lang}"],
            "howReissueCard": [f"utter_howReissueCard{lang}",f"utter_q12{lang}"],
            "howMakeRefund": [f"utter_q15{lang}"],
            "interrupting": [f"utter_interrupting{lang}"],
        }

        to_another_script = {"loans_mortgage", "remove_the_limit", "limits", "forgot_card", "reset_pin", "card_operation", "current_loan", "card_delivery", "credit_card", "new_loan", 
                             "block_card", "overdue_debt", "sysn", "super_app", "kino_kz", "registration", "payments_and_transfers", "halyk_travel", "addresses_branches", "brokerage", }

        to_oper = ['internet']

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))
            
            return actions
        elif last_intent in to_oper:
            dispatcher.utter_message(response = f"utter_toOperatorICant{lang}")
            return [ActionExecuted(f"utter_toOperatorICant{lang}"), ConversationPaused()]
        elif last_intent in to_another_script:
            return [FollowupAction("action_switchToAnotherScript")]
        elif last_intent == "publicServices":
            return [FollowupAction("action_checkApplicationStatus")]
        elif last_intent == "robot":
            return [FollowupAction("action_robot")]
        elif last_intent == "operator":
            return [FollowupAction("action_operator")]
        else:
            return [FollowupAction("action_counter")]


class ActionAfterQ20(Action):

    def name(self) -> Text:
        return "action_q20"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q20")
        
        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']

        intents_utters = {
            "yes": [f"utter_instructions{lang}", f"utter_waitingInLine{lang}", f"utter_q10{lang}"],
            "no": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "repeat": [f"utter_cardClosureLimits{lang}", f"utter_q20{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q20{lang}"],
            "soundlessly": [f"utter_soundLessly{lang}", f"utter_cardClosureConditions{lang}", f"utter_q20{lang}"],
            "dontKnow": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "internet": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "callBack": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "later": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "bankBrunch": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "knowHow": [f"utter_understood{lang}",f"utter_q2{lang}"],
            "haveMoney": [f"utter_moneyOnTheCard{lang}",f"utter_q2{lang}"],
            "arestLimits": [f"utter_arestLimits{lang}",f"utter_q2{lang}"],
        }

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))
            
            return actions
        elif last_intent == "robot":
            return [FollowupAction("action_robot")]
        elif last_intent == "operator":
            return [FollowupAction("action_operator")]
        elif last_intent == "changeLangKZ" or last_intent == "changeLangRU":
            return [FollowupAction("action_changelang")]
        else:
            return [FollowupAction("action_counter")]


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