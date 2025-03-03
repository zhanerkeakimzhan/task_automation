from typing import Any, Text, Dict, List
import pandas as pd
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
import requests
from rasa_sdk.events import ActionExecuted, SlotSet, ActiveLoop, FollowupAction, Restarted, ConversationPaused
from datetime import datetime
import redis
import json
import yaml
import random
import os
import asyncio
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

        f_lang = dict_to_redis['f_language']
        if f_lang and f_lang[-1] != '': 
            language = f_lang[-1].upper() 
        else: 
            language = dict_to_redis['language'].upper()

        # if last_intent in dont_need_ident or identified is not None or trusted_phone is False:
        #     scripttype = last_intent
        # else:
        #     scripttype = 'identification'

        if last_intent not in dont_need_ident and identified is None and trusted_phone is True:
            if last_intent in need_ident or check_intent(last_intent, tracker):
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
        dict_to_redis['robot_durations']['halyk_bank_loans_mortgage']['end_datetime'] = local_time
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


class ActionSlotSet(Action):
    def name(self) -> Text:
        return "action_slotSet"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        last_intent = tracker.latest_message['intent']['name']

        print("last intent:", last_intent)

        if last_intent == "conditionsHalykSale" or last_intent == "conditionsBiGroup":
            return [SlotSet("full_info", last_intent)]
        else:
            return []


class ActionRepeat(Action):
    def name(self) -> Text:
        return "action_repeat"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        logger, log_handler = create_logger(tracker)
        log_message = f'RUN Action: action_repeat'
        logger.info(log_message)

        events = tracker.events
        responses = get_utters_between_two_intents(events)

        print(responses)
        exception = ["utter_checkInfo", "utter_soundLesslyRU", "utter_soundLesslyKZ"]

        if not responses:
            responses.append("utter_q1RU")

        for i in responses:
            if exception in str(i):
                responses.remove(i)

        for utter in reversed(responses):
            response = utter
            # print(response)
            dispatcher.utter_message(response=response)
            ActionExecuted(response)

        log_message = f'return_responses: {responses}'
        logger.info(log_message)

        log_handler.close()
        logger.removeHandler(log_handler)

        return [ActionExecuted(i) for i in reversed(responses)]


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

        events = tracker.events
        all_utters = get_all_utters(events)

        lang, last_utter = get_last_utter_and_lang(tracker)

        print(lang)
        print(last_utter)

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
        
        print(all_utters)

        last_intent = tracker.latest_message['intent']['name']

        lang = last_intent[-2:]
        print('перевод на этот язык:', lang)

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
        
        # print(returns)

        return returns

#q0 
class ActionAfterQ0(Action):

    def name(self) -> Text:
        return "action_q0"

    # async def restart_bot(self, uuid: str):
    #     target_url = f"http://halyk_bank_identification:5012/webhooks/rest/webhook"
    #     try:
    #         response = await asyncio.to_thread(requests.post, target_url, json={"sender": uuid, "message": "это робот"})
    #         print(f"Sent /restart to {target_url}: {response.status_code} {response.json()}", flush=True)
    #     except Exception as e:
    #         print(f"Error sending /restart: {e}", flush=True)
    #     return response

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q0")

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        logger, log_handler = create_logger(tracker)
        log_message = f'Script: halyk_bank_loans_mortgage, Action: action_q0, uuid: {uuid}'
        logger.info(log_message)

        try:
            robot_counter = dict_to_redis['robot_counter']
            operator_counter = dict_to_redis['operator_counter']
            print("robot_counter:", robot_counter)
            print("operator_counter:", operator_counter)
        except Exception as e:
            log_message = f'\n\t\t\t\t Error type: {type(e).__name__}\n\t\t\t\t Message: {str(e)}\n\t\t\t\t Arguments: {e.args}'
            logger.error(log_message)

        log_handler.close()
        logger.removeHandler(log_handler)

        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']

        intents_utters = {
            "changeLangKZ": ["utter_q1KZ"],
            "changeLangRU": ["utter_q1RU"],
            "no": [f"utter_score{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q1{lang}"],
            "soundlessly": [f"utter_q3{lang}"],
            "haveQuestion": [f"utter_q7{lang}"],
            "hostelForMortgage": [f"utter_availableMortgageOptions{lang}", f"utter_q8{lang}"],
            "conditions": [f"utter_availableMortgageOptions{lang}", f"utter_q8{lang}"],
            "mortgage72025": [f"utter_info72025{lang}", f"utter_q2{lang}"],
            "mortgageHalykSale": [f"utter_infoHalykSale{lang}", f"utter_q2{lang}"],
            "conditionsHalykSale": [f"utter_conditionsHalykSale{lang}", f"utter_q9{lang}"],
            "mortgageBazisa": [f"utter_infoBazisA{lang}", f"utter_q2{lang}"],
            "mortgageBiGroup": [f"utter_infoBiGroup{lang}", f"utter_q2{lang}"],
            "conditionsBiGroup": [f"utter_conditionsBiGroup{lang}", f"utter_q9{lang}"],
            "mortgageHalyk": [f"utter_infoHalyk{lang}", f"utter_q2{lang}"],
            "conditionsHalyk": [f"utter_conditionsHalyk{lang}", f"utter_q2{lang}"],
            "when72025": [f"utter_when72025{lang}", f"utter_q2{lang}"],
            "bet": [f"utter_whatIsBet{lang}", f"utter_q2{lang}"],
            "whatIsDigital": [f"utter_digitalCarLoans{lang}", f"utter_q2{lang}"],
            "autoDigitalCredit": [f"utter_digitalAutoLoanProcess{lang}", f"utter_q16{lang}"],
            "autoDigitalCreditConditions": [f"utter_digitalAutoLoanTerms{lang}", f"utter_q18{lang}"],
            "autoCredit": [f"utter_q15{lang}"],
            "autoPreferentialCredit": [f"utter_autoPreferentialCredit{lang}", f"utter_q19{lang}"],
            "autoPreferentialCreditConditions": [f"utter_autoPreferentialCreditConditions{lang}", f"utter_q20{lang}"],
            "exactProcentBet": [f"utter_exactProcentBet{lang}", f"utter_q2{lang}"],
            "interestRate": [f"utter_interestRate{lang}", f"utter_q10{lang}"],
            "refinancing": [f"utter_refinancing{lang}", f"utter_q11{lang}"],
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
            
            return [SlotSet('robot_counter', robot_counter), SlotSet('operator_counter', operator_counter), *actions]
        elif last_intent == 'another':
            dispatcher.utter_message(response=f"utter_toOperator{lang}")
            return [SlotSet('robot_counter', robot_counter), SlotSet('operator_counter', operator_counter), ActionExecuted(f"utter_toOperator{lang}"), ConversationPaused()]
        elif last_intent in to_another_script:
            dispatcher.utter_message(response = f'utter_q1{lang}')
            return [SlotSet('robot_counter', robot_counter), SlotSet('operator_counter', operator_counter), ActionExecuted(f'utter_q1{lang}')]
        elif last_intent == "robot":
            return [SlotSet('robot_counter', robot_counter), SlotSet('operator_counter', operator_counter), FollowupAction(f"action_robot")]
        elif last_intent == "operator":
            return [SlotSet('robot_counter', robot_counter), SlotSet('operator_counter', operator_counter), FollowupAction(f"action_operator")]
        else:
            return [SlotSet('robot_counter', robot_counter), SlotSet('operator_counter', operator_counter), FollowupAction(f"action_counter")]


class ActionAfterQ1(Action):

    def name(self) -> Text:
        return "action_q1"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q1")

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']

        intents_utters = {
            "changeLangKZ": ["utter_q1KZ"],
            "changeLangRU": ["utter_q1RU"],
            "no": [f"utter_score{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q1{lang}"],
            "soundlessly": [f"utter_q3{lang}"],
            "haveQuestion": [f"utter_q7{lang}"],
            "hostelForMortgage": [f"utter_availableMortgageOptions{lang}", f"utter_q8{lang}"],
            "mortgage72025": [f"utter_info72025{lang}", f"utter_q2{lang}"],
            "mortgageHalykSale": [f"utter_infoHalykSale{lang}", f"utter_q2{lang}"],
            "conditionsHalykSale": [f"utter_conditionsHalykSale{lang}", f"utter_q9{lang}"],
            "mortgageBazisa": [f"utter_infoBazisA{lang}", f"utter_q2{lang}"],
            "mortgageBiGroup": [f"utter_infoBiGroup{lang}", f"utter_q2{lang}"],
            "conditionsBiGroup": [f"utter_conditionsBiGroup{lang}", f"utter_q9{lang}"],
            "mortgageHalyk": [f"utter_infoHalyk{lang}", f"utter_q2{lang}"],
            "conditionsHalyk": [f"utter_conditionsHalyk{lang}", f"utter_q2{lang}"],
            "when72025": [f"utter_when72025{lang}", f"utter_q2{lang}"],
            "bet": [f"utter_whatIsBet{lang}", f"utter_q2{lang}"],
            "whatIsDigital": [f"utter_digitalCarLoans{lang}", f"utter_q2{lang}"],
            "autoDigitalCredit": [f"utter_digitalAutoLoanProcess{lang}", f"utter_q16{lang}"],
            "autoDigitalCreditConditions": [f"utter_digitalAutoLoanTerms{lang}", f"utter_q18{lang}"],
            "autoCredit": [f"utter_q15{lang}"],
            "autoPreferentialCredit": [f"utter_autoPreferentialCredit{lang}", f"utter_q19{lang}"],
            "autoPreferentialCreditConditions": [f"utter_autoPreferentialCreditConditions{lang}", f"utter_q20{lang}"],
            "exactProcentBet": [f"utter_exactProcentBet{lang}", f"utter_q2{lang}"],
            "interestRate": [f"utter_interestRate{lang}", f"utter_q10{lang}"],
            "refinancing": [f"utter_refinancing{lang}", f"utter_q11{lang}"],
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
        elif last_intent == 'conditions':
            events = tracker.events
            utters_before = get_utters_between_two_intents(events)
            exception = ['utter_info72025RU', 'utter_info72025KZ', 'utter_infoHalykSaleRU', 'utter_infoHalykSaleKZ',
                        'utter_infoBazisARU', 'utter_infoBazisAKZ', 'utter_infoBiGroupRU', 'utter_infoBiGroupKZ',
                        'utter_infoHalykRU', 'utter_infoHalykKZ', 'utter_infoForDormitoryRU', 'utter_infoForDormitoryKZ']

            for i in utters_before:
                for exc in exception:
                    if exc in i:
                        utter_for_conditions = exc

            utters_conditions = {
                'utter_info72025RU': [f'utter_anotherQuestionMortagage{lang}', f'utter_q2{lang}'], 
                'utter_info72025KZ': [f'utter_anotherQuestionMortagage{lang}', f'utter_q2{lang}'], 
                'utter_infoHalykSaleRU': [f'utter_conditionsHalykSale{lang}', f'utter_q9{lang}'], 
                'utter_infoHalykSaleKZ': [f'utter_conditionsHalykSale{lang}', f'utter_q9{lang}'],
                'utter_infoBazisARU': [f'utter_anotherQuestionMortagage{lang}', f'utter_q2{lang}'], 
                'utter_infoBazisAKZ': [f'utter_anotherQuestionMortagage{lang}', f'utter_q2{lang}'], 
                'utter_infoBiGroupRU': [f'utter_conditionsBiGroup{lang}', f'utter_q9{lang}'], 
                'utter_infoBiGroupKZ': [f'utter_conditionsBiGroup{lang}', f'utter_q9{lang}'],
                'utter_infoHalykRU': [f'utter_conditionsHalyk{lang}', f'utter_q2{lang}'], 
                'utter_infoHalykKZ': [f'utter_conditionsHalyk{lang}', f'utter_q2{lang}'], 
                'utter_infoForDormitoryRU': [f'utter_conditionsHalyk{lang}', f'utter_q2{lang}'], 
                'utter_infoForDormitoryKZ': [f'utter_conditionsHalyk{lang}', f'utter_q2{lang}']
            }
            if utter_for_conditions in utters_conditions:
                print("utter_for_conditions in utters_conditions")
                messages = utters_conditions[utter_for_conditions]
                actions = []
                
                for message in messages:
                    dispatcher.utter_message(response=message)
                    actions.append(ActionExecuted(message))
                
                return actions
            else:
                return [FollowupAction(f"action_counter")]
        elif last_intent == 'another':
            dispatcher.utter_message(response=f"utter_toOperator{lang}")
            return [ActionExecuted(f"utter_toOperator{lang}"), ConversationPaused()]
        elif last_intent in to_another_script:
            return [FollowupAction("action_switchToAnotherScript")]
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

        last_intent = tracker.latest_message['intent']['name']
        print("last intent:", last_intent)

        lang, last_utter = get_last_utter_and_lang(tracker)

        intents_utters = {
            "yes": [f"utter_q7{lang}"],
            "no": [f"utter_score{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q2{lang}"],
            "haveQuestion": [f"utter_q7{lang}"],
            "iCant": [f"utter_score{lang}"],
            "callBack": [f"utter_score{lang}"],
            "later": [f"utter_score{lang}"],
            "busy": [f"utter_score{lang}"],
            "hostelForMortgage": [f"utter_availableMortgageOptions{lang}", f"utter_q8{lang}"],
            "mortgage72025": [f"utter_info72025{lang}", f"utter_q2{lang}"],
            "mortgageHalykSale": [f"utter_infoHalykSale{lang}", f"utter_q2{lang}"],
            "conditionsHalykSale": [f"utter_conditionsHalykSale{lang}", f"utter_q9{lang}"],
            "mortgageBazisa": [f"utter_infoBazisA{lang}", f"utter_q2{lang}"],
            "mortgageBiGroup": [f"utter_infoBiGroup{lang}", f"utter_q2{lang}"],
            "conditionsBiGroup": [f"utter_conditionsBiGroup{lang}", f"utter_q9{lang}"],
            "mortgageHalyk": [f"utter_infoHalyk{lang}", f"utter_q2{lang}"],
            "conditionsHalyk": [f"utter_conditionsHalyk{lang}", f"utter_q2{lang}"],
            "when72025": [f"utter_when72025{lang}", f"utter_q2{lang}"],
            "bet": [f"utter_whatIsBet{lang}", f"utter_q2{lang}"],
            "whatIsDigital": [f"utter_digitalCarLoans{lang}", f"utter_q2{lang}"],
            "autoDigitalCredit": [f"utter_digitalAutoLoanProcess{lang}", f"utter_q16{lang}"],
            "autoDigitalCreditConditions": [f"utter_digitalAutoLoanTerms{lang}", f"utter_q18{lang}"],
            "autoCredit": [f"utter_q15{lang}"],
            "autoPreferentialCredit": [f"utter_autoPreferentialCredit{lang}", f"utter_q19{lang}"],
            "autoPreferentialCreditConditions": [f"utter_autoPreferentialCreditConditions{lang}", f"utter_q20{lang}"],
            "exactProcentBet": [f"utter_exactProcentBet{lang}", f"utter_q2{lang}"],
            "interestRate": [f"utter_interestRate{lang}", f"utter_q10{lang}"],
            "refinancing": [f"utter_refinancing{lang}", f"utter_q11{lang}"],
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
        elif last_intent == 'conditions':
            events = tracker.events
            utters_before = get_utters_between_two_intents(events)
            exception = ['utter_info72025RU', 'utter_info72025KZ', 'utter_infoHalykSaleRU', 'utter_infoHalykSaleKZ',
                        'utter_infoBazisARU', 'utter_infoBazisAKZ', 'utter_infoBiGroupRU', 'utter_infoBiGroupKZ',
                        'utter_infoHalykRU', 'utter_infoHalykKZ', 'utter_infoForDormitoryRU', 'utter_infoForDormitoryKZ']

            for i in utters_before:
                for exc in exception:
                    if exc in i:
                        utter_for_conditions = exc

            utters_conditions = {
                'utter_info72025RU': [f'utter_anotherQuestionMortagage{lang}', f'utter_q2{lang}'], 
                'utter_info72025KZ': [f'utter_anotherQuestionMortagage{lang}', f'utter_q2{lang}'], 
                'utter_infoHalykSaleRU': [f'utter_conditionsHalykSale{lang}', f'utter_q9{lang}'], 
                'utter_infoHalykSaleKZ': [f'utter_conditionsHalykSale{lang}', f'utter_q9{lang}'],
                'utter_infoBazisARU': [f'utter_anotherQuestionMortagage{lang}', f'utter_q2{lang}'], 
                'utter_infoBazisAKZ': [f'utter_anotherQuestionMortagage{lang}', f'utter_q2{lang}'], 
                'utter_infoBiGroupRU': [f'utter_conditionsBiGroup{lang}', f'utter_q9{lang}'], 
                'utter_infoBiGroupKZ': [f'utter_conditionsBiGroup{lang}', f'utter_q9{lang}'],
                'utter_infoHalykRU': [f'utter_conditionsHalyk{lang}', f'utter_q2{lang}'], 
                'utter_infoHalykKZ': [f'utter_conditionsHalyk{lang}', f'utter_q2{lang}'], 
                'utter_infoForDormitoryRU': [f'utter_conditionsHalyk{lang}', f'utter_q2{lang}'], 
                'utter_infoForDormitoryKZ': [f'utter_conditionsHalyk{lang}', f'utter_q2{lang}']
            }
            if utter_for_conditions in utters_conditions:
                print("utter_for_conditions in utters_conditions")
                messages = utters_conditions[utter_for_conditions]
                actions = []
                
                for message in messages:
                    dispatcher.utter_message(response=message)
                    actions.append(ActionExecuted(message))
                
                return actions
            else:
                return [FollowupAction(f"action_counter")]
        elif last_intent == 'another':
            dispatcher.utter_message(response = f"utter_toOperator{lang}")
            return [ActionExecuted(f"utter_toOperator{lang}"), ConversationPaused()]
        elif last_intent == 'whatDocuments':
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


class ActionAfterQ3(Action):

    def name(self) -> Text:
        return "action_q3"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q3")

        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']
        print("last intent:", last_intent)

        intents_utters = {
            "changeLangKZ": ["utter_q1KZ"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q1{lang}"],
            "haveQuestion": [f"utter_q7{lang}"],
            "hostelForMortgage": [f"utter_availableMortgageOptions{lang}", f"utter_q8{lang}"],
            "mortgage72025": [f"utter_info72025{lang}", f"utter_q2{lang}"],
            "mortgageHalykSale": [f"utter_infoHalykSale{lang}", f"utter_q2{lang}"],
            "conditionsHalykSale": [f"utter_conditionsHalykSale{lang}", f"utter_q9{lang}"],
            "mortgageBazisa": [f"utter_infoBazisA{lang}", f"utter_q2{lang}"],
            "mortgageBiGroup": [f"utter_infoBiGroup{lang}", f"utter_q2{lang}"],
            "conditionsBiGroup": [f"utter_conditionsBiGroup{lang}", f"utter_q9{lang}"],
            "mortgageHalyk": [f"utter_infoHalyk{lang}", f"utter_q2{lang}"],
            "conditionsHalyk": [f"utter_conditionsHalyk{lang}", f"utter_q2{lang}"],
            "when72025": [f"utter_when72025{lang}", f"utter_q2{lang}"],
            "bet": [f"utter_whatIsBet{lang}", f"utter_q2{lang}"],
            "whatIsDigital": [f"utter_digitalCarLoans{lang}", f"utter_q2{lang}"],
            "autoDigitalCredit": [f"utter_digitalAutoLoanProcess{lang}", f"utter_q16{lang}"],
            "autoDigitalCreditConditions": [f"utter_digitalAutoLoanTerms{lang}", f"utter_q18{lang}"],
            "autoCredit": [f"utter_q15{lang}"],
            "autoPreferentialCredit": [f"utter_autoPreferentialCredit{lang}", f"utter_q19{lang}"],
            "autoPreferentialCreditConditions": [f"utter_autoPreferentialCreditConditions{lang}", f"utter_q20{lang}"],
            "exactProcentBet": [f"utter_exactProcentBet{lang}", f"utter_q2{lang}"],
            "interestRate": [f"utter_interestRate{lang}", f"utter_q10{lang}"],
            "refinancing": [f"utter_refinancing{lang}", f"utter_q11{lang}"],
            "interrupting": [f"utter_interrupting{lang}"],
        }

        intents_to_q1 = ["changeLangRU", "yes", "no", "repeat", "iCant", "callBack", "knowHow"]

        to_another_script = {"loans_mortgage", "remove_the_limit", "limits", "forgot_card", "reset_pin", "card_operation", "current_loan", "card_delivery", "credit_card", "new_loan", 
                             "block_card", "overdue_debt", "sysn", "super_app", "kino_kz", "registration", "payments_and_transfers", "halyk_travel", "addresses_branches", "brokerage", }

        if last_intent in intents_to_q1:
            dispatcher.utter_message(response= f"utter_q1{lang}")
            return [ActionExecuted(f"utter_q1{lang}")]
        elif last_intent == 'another':
            dispatcher.utter_message(response = f"utter_toOperator{lang}")
            return [ActionExecuted(f"utter_toOperator{lang}"), ConversationPaused()]
        elif last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))
            
            return actions
        elif last_intent == 'conditions':
            events = tracker.events
            utters_before = get_utters_between_two_intents(events)
            exception = ['utter_info72025RU', 'utter_info72025KZ', 'utter_infoHalykSaleRU', 'utter_infoHalykSaleKZ',
                        'utter_infoBazisARU', 'utter_infoBazisAKZ', 'utter_infoBiGroupRU', 'utter_infoBiGroupKZ',
                        'utter_infoHalykRU', 'utter_infoHalykKZ', 'utter_infoForDormitoryRU', 'utter_infoForDormitoryKZ']

            for i in utters_before:
                for exc in exception:
                    if exc in i:
                        utter_for_conditions = exc

            utters_conditions = {
                'utter_info72025RU': [f'utter_anotherQuestionMortagage{lang}', f'utter_q2{lang}'], 
                'utter_info72025KZ': [f'utter_anotherQuestionMortagage{lang}', f'utter_q2{lang}'], 
                'utter_infoHalykSaleRU': [f'utter_conditionsHalykSale{lang}', f'utter_q9{lang}'], 
                'utter_infoHalykSaleKZ': [f'utter_conditionsHalykSale{lang}', f'utter_q9{lang}'],
                'utter_infoBazisARU': [f'utter_anotherQuestionMortagage{lang}', f'utter_q2{lang}'], 
                'utter_infoBazisAKZ': [f'utter_anotherQuestionMortagage{lang}', f'utter_q2{lang}'], 
                'utter_infoBiGroupRU': [f'utter_conditionsBiGroup{lang}', f'utter_q9{lang}'], 
                'utter_infoBiGroupKZ': [f'utter_conditionsBiGroup{lang}', f'utter_q9{lang}'],
                'utter_infoHalykRU': [f'utter_conditionsHalyk{lang}', f'utter_q2{lang}'], 
                'utter_infoHalykKZ': [f'utter_conditionsHalyk{lang}', f'utter_q2{lang}'], 
                'utter_infoForDormitoryRU': [f'utter_conditionsHalyk{lang}', f'utter_q2{lang}'], 
                'utter_infoForDormitoryKZ': [f'utter_conditionsHalyk{lang}', f'utter_q2{lang}']
            }
            if utter_for_conditions in utters_conditions:
                print("utter_for_conditions in utters_conditions")
                messages = utters_conditions[utter_for_conditions]
                actions = []
                
                for message in messages:
                    dispatcher.utter_message(response=message)
                    actions.append(ActionExecuted(message))
                
                return actions
            else:
                return [FollowupAction(f"action_counter")]
        elif last_intent in to_another_script:
            return [FollowupAction("action_switchToAnotherScript")]
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

        events = tracker.events
        all_utters = get_all_utters(events)

        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']
        print("last intent:", last_intent)

        intents_utters = {
            "changeLangKZ": ["utter_q1KZ"],
            "changeLangRU": ["utter_q1RU"],
            "no": [f"utter_score{lang}"],
            "repeat": [f"utter_q1{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q1{lang}"],
            "soundlessly": [f"utter_q3{lang}"],
            "haveQuestion": [f"utter_q7{lang}"],
            "hostelForMortgage": [f"utter_availableMortgageOptions{lang}", f"utter_q8{lang}"],
            "mortgage72025": [f"utter_info72025{lang}", f"utter_q2{lang}"],
            "mortgageHalykSale": [f"utter_infoHalykSale{lang}", f"utter_q2{lang}"],
            "conditionsHalykSale": [f"utter_conditionsHalykSale{lang}", f"utter_q9{lang}"],
            "mortgageBazisa": [f"utter_infoBazisA{lang}", f"utter_q2{lang}"],
            "mortgageBiGroup": [f"utter_infoBiGroup{lang}", f"utter_q2{lang}"],
            "conditionsBiGroup": [f"utter_conditionsBiGroup{lang}", f"utter_q9{lang}"],
            "mortgageHalyk": [f"utter_infoHalyk{lang}", f"utter_q2{lang}"],
            "conditionsHalyk": [f"utter_conditionsHalyk{lang}", f"utter_q2{lang}"],
            "when72025": [f"utter_when72025{lang}", f"utter_q2{lang}"],
            "bet": [f"utter_whatIsBet{lang}", f"utter_q2{lang}"],
            "autoDigitalCredit": [f"utter_digitalAutoLoanProcess{lang}", f"utter_q16{lang}"],
            "autoDigitalCreditConditions": [f"utter_digitalAutoLoanTerms{lang}", f"utter_q18{lang}"],
            "autoCredit": [f"utter_q15{lang}"],
            "autoPreferentialCredit": [f"utter_autoPreferentialCredit{lang}", f"utter_q19{lang}"],
            "autoPreferentialCreditConditions": [f"utter_autoPreferentialCreditConditions{lang}", f"utter_q20{lang}"],
            "exactProcentBet": [f"utter_exactProcentBet{lang}", f"utter_q2{lang}"],
            "interestRate": [f"utter_interestRate{lang}", f"utter_q10{lang}"],
            "refinancing": [f"utter_refinancing{lang}", f"utter_q11{lang}"],
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
            dispatcher.utter_message(response = f"utter_toOperator{lang}")
            return [ActionExecuted(f"utter_toOperator{lang}"), ConversationPaused()]
        elif last_intent == 'whatDocuments':
            dispatcher.utter_message(response = f"utter_toOperatorICant{lang}")
            return [ActionExecuted(f"utter_toOperatorICant{lang}"), ConversationPaused()]
        elif last_intent in to_another_script:
            return [FollowupAction("action_switchToAnotherScript")]
        elif last_intent == "repeat":
            return [FollowupAction("action_repeat")]
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
        print("last intent:", last_intent)

        intents_utters = {
            "repeat": [f"utter_availableMortgageOptions{lang}", f"utter_q8{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q8{lang}"],
            "soundlessly": [f"utter_soundLessly{lang}", f"utter_availableMortgageOptions{lang}", f"utter_q8{lang}"],
            "mortgage72025": [f"utter_info72025{lang}", f"utter_q2{lang}"],
            "mortgageHalykSale": [f"utter_infoHalykSale{lang}", f"utter_q2{lang}"],
            "conditionsHalykSale": [f"utter_conditionsHalykSale{lang}", f"utter_q9{lang}"],
            "mortgageBazisa": [f"utter_infoBazisA{lang}", f"utter_q2{lang}"],
            "mortgageBiGroup": [f"utter_infoBiGroup{lang}", f"utter_q2{lang}"],
            "conditionsBiGroup": [f"utter_conditionsBiGroup{lang}", f"utter_q9{lang}"],
            "mortgageHalyk": [f"utter_infoHalyk{lang}", f"utter_q2{lang}"],
            "conditionsHalyk": [f"utter_conditionsHalyk{lang}", f"utter_q2{lang}"],
            "when72025": [f"utter_when72025{lang}", f"utter_q2{lang}"],
            "bet": [f"utter_whatIsBet{lang}", f"utter_q2{lang}"],
            "whatIsDigital": [f"utter_digitalCarLoans{lang}", f"utter_q2{lang}"],
            "autoDigitalCredit": [f"utter_digitalAutoLoanProcess{lang}", f"utter_q16{lang}"],
            "autoDigitalCreditConditions": [f"utter_digitalAutoLoanTerms{lang}", f"utter_q18{lang}"],
            "autoCredit": [f"utter_q15{lang}"],
            "autoPreferentialCredit": [f"utter_autoPreferentialCredit{lang}", f"utter_q19{lang}"],
            "autoPreferentialCreditConditions": [f"utter_autoPreferentialCreditConditions{lang}", f"utter_q20{lang}"],
            "exactProcentBet": [f"utter_exactProcentBet{lang}", f"utter_q2{lang}"],
            "interestRate": [f"utter_interestRate{lang}", f"utter_q10{lang}"],
            "refinancing": [f"utter_refinancing{lang}", f"utter_q11{lang}"],
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
        elif last_intent == "robot":
            return [FollowupAction("action_robot")]
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
        print("last intent:", last_intent)

        intents_utters = {
            "yes": [f"utter_fullInfo{lang}", f"utter_q2{lang}"],
            "no": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q9{lang}"],
            "callBack": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "later": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "bankBrunch": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "knowHow": [f"utter_understood{lang}", f"utter_q2{lang}"],
        }

        to_operator = ['iCant', 'internet']

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []

            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))

            return actions
        elif last_intent in to_operator:
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


class ActionAfterQ10(Action):

    def name(self) -> Text:
        return "action_q10"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q10")
        
        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']
        print("last intent:", last_intent)

        intents_utters = {
            "changeLangRU": ["utter_interestRateRU", "utter_q10RU"],
            "changeLangKZ": ["utter_interestRateKZ", "utter_q10KZ"],
            "repeat": [f"utter_interestRate{lang}", f"utter_q10{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q10{lang}"],
            "soundlessly": [f"utter_soundLessly{lang}", f"utter_interestRate{lang}", f"utter_q10{lang}"],
            "hostelForMortgage": [f"utter_availableMortgageOptions{lang}", f"utter_q8{lang}"],
            "mortgage72025": [f"utter_rate72025{lang}", f"utter_q2{lang}"],
            "mortgageHalykSale": [f"utter_rateHalykSale{lang}", f"utter_q2{lang}"],
            "mortgageBazisa": [f"utter_rateBazisA{lang}", f"utter_q2{lang}"],
            "mortgageBiGroup": [f"utter_infoBiGroup{lang}", f"utter_q2{lang}"],
            "mortgageHalyk": [f"utter_rateHalyk{lang}", f"utter_q2{lang}"],
            "when72025": [f"utter_when72025{lang}", f"utter_q2{lang}"],
            "bet": [f"utter_whatIsBet{lang}", f"utter_q2{lang}"],
            "whatIsDigital": [f"utter_digitalCarLoans{lang}", f"utter_q2{lang}"],
            "autoDigitalCredit": [f"utter_digitalAutoLoanProcess{lang}", f"utter_q16{lang}"],
            "autoDigitalCreditConditions": [f"utter_digitalAutoLoanTerms{lang}", f"utter_q18{lang}"],
            "autoCredit": [f"utter_q15{lang}"],
            "autoPreferentialCredit": [f"utter_autoPreferentialCredit{lang}", f"utter_q19{lang}"],
            "autoPreferentialCreditConditions": [f"utter_autoPreferentialCreditConditions{lang}", f"utter_q20{lang}"],
            "exactProcentBet": [f"utter_exactProcentBet{lang}", f"utter_q2{lang}"],
            "interestRate": [f"utter_interestRate{lang}", f"utter_q10{lang}"],
            "refinancing": [f"utter_refinancing{lang}", f"utter_q11{lang}"],
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
        
        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']
        print("last intent:", last_intent)

        intents_utters = {
            "changeLangKZ": ["utter_refinancingKZ", "utter_q11KZ"],
            "changeLangRU": ["utter_refinancingRU", "utter_q11RU"],
            "repeat": [f"utter_refinancing{lang}", f"utter_q11{lang}"],
            "soundlessly": [f"utter_soundLessly{lang}", f"utter_refinancing{lang}", f"utter_q11{lang}"],
            "yes": [f"utter_howToDoRefinancing{lang}", f"utter_q12{lang}"],
            "no": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q11{lang}"],
            "callBack": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "later": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "bankBrunch": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "knowHow": [f"utter_understood{lang}", f"utter_q2{lang}"],
        }

        to_another_script = {"loans_mortgage", "remove_the_limit", "limits", "forgot_card", "reset_pin", "card_operation", "current_loan", "card_delivery", "credit_card", "new_loan", 
                             "block_card", "overdue_debt", "sysn", "super_app", "kino_kz", "registration", "payments_and_transfers", "halyk_travel", "addresses_branches", "brokerage", }

        to_operator = ['iCant', 'internet']

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []
            
            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))
            
            return actions
        elif last_intent in to_operator:
            dispatcher.utter_message(response = f"utter_toOperatorICant{lang}")
            return [ActionExecuted(f"utter_toOperatorICant{lang}"), ConversationPaused()]
        elif last_intent in to_another_script:
            return [FollowupAction("action_switchToAnotherScript")]
        elif last_intent == "robot":
            return [FollowupAction("action_robot")]
        elif last_intent == "operator":
            return [FollowupAction("action_operator")]
        else:
            return [FollowupAction("action_counter")]


class ActionAfterQ12(Action):

    def name(self) -> Text:
        return "action_q12"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q12")
        
        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']
        print("last intent:", last_intent)

        intents_utters = {
            "changeLangKZ": ["utter_q12KZ"],
            "changeLangRU": ["utter_q12RU"],
            "repeat": [f"utter_repeatHowToDoRefinancing{lang}", f"utter_q14{lang}"],
            "soundlessly": [f"utter_soundLessly{lang}", f"utter_howToDoRefinancing{lang}", f"utter_q12{lang}"],
            "yes": [f"utter_waitingInLine{lang}", f"utter_q13{lang}"],
            "no": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q12{lang}"],
            "callBack": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "bankBrunch": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "knowHow": [f"utter_waitingInLine{lang}", f"utter_q13{lang}"],
        }

        to_operator = ['iCant', 'later', 'internet']

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []

            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))

            return actions
        elif last_intent in to_operator:
            dispatcher.utter_message(response = f"utter_toOperatorICant{lang}")
            return [ActionExecuted(f"utter_toOperatorICant{lang}"), ConversationPaused()]
        elif last_intent == "robot":
            return [FollowupAction("action_robot")]
        elif last_intent == "operator":
            return [FollowupAction("action_operator")]
        else:
            return [FollowupAction("action_counter")]


class ActionAfterQ13(Action):

    def name(self) -> Text:
        return "action_q13"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_q13")
        
        lang, last_utter = get_last_utter_and_lang(tracker)
        last_intent = tracker.latest_message['intent']['name']
        print("last intent:", last_intent)

        intents_utters = {
            "changeLangKZ": ["utter_waitingInLineKZ", "utter_q13KZ"],
            "changeLangRU": ["utter_waitingInLineRU", "utter_q13RU"],
            "repeat": [f"utter_repeatHowToDoRefinancing{lang}", f"utter_q14{lang}"],
            "soundlessly": [f"utter_soundLessly{lang}", f"utter_repeatHowToDoRefinancing{lang}", f"utter_q13{lang}"],
            "yes": [f"utter_silence3sec{lang}", f"utter_silence3sec{lang}", f"utter_silence3sec{lang}", f"utter_q14{lang}"],
            "no": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q13{lang}"],
            "callBack": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "bankBrunch": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "knowHow": [f"utter_q14{lang}"],
        }

        to_operator = ['iCant', 'later', 'internet']

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []

            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))

            return actions
        elif last_intent in to_operator:
            dispatcher.utter_message(response = f"utter_toOperatorICant{lang}")
            return [ActionExecuted(f"utter_toOperatorICant{lang}"), ConversationPaused()]
        elif last_intent == "robot":
            return [FollowupAction("action_robot")]
        elif last_intent == "operator":
            return [FollowupAction("action_operator")]
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
            "changeLangKZ": ["utter_q14KZ"],
            "changeLangRU": ["utter_q14RU"],
            "repeat": [f"utter_repeatHowToDoRefinancing{lang}", f"utter_q14{lang}"],
            "soundlessly": [f"utter_soundLessly{lang}", f"utter_q14{lang}"],
            "yes": [f"utter_good{lang}", f"utter_q2{lang}"],
            "no": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q14{lang}"],
            "callBack": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "bankBrunch": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "knowHow": [f"utter_q14{lang}"],
        }

        last_3 = all_utters[-6:]
        print(last_3)

        counter = 0
        for action in last_3:
            if action ==  f"utter_waiting{lang}":
                counter += 1
            else:
                continue
        print("Counter:", counter)

        to_operator = ['iCant', 'later', 'internet']

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []

            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))

            return actions
        elif last_intent in to_operator:
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
                dispatcher.utter_message(response = f"utter_silence3sec{lang}")
                dispatcher.utter_message(response = f"utter_silence3sec{lang}")
                dispatcher.utter_message(response = f"utter_silence3sec{lang}")
                dispatcher.utter_message(response = f"utter_q14{lang}")
                return(ActionExecuted(f"utter_waiting{lang}"), ActionExecuted(f"utter_q14{lang}"))


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
            "hostelForMortgage": [f"utter_availableMortgageOptions{lang}", f"utter_q8{lang}"],
            "mortgage72025": [f"utter_info72025{lang}", f"utter_q2{lang}"],
            "mortgageHalykSale": [f"utter_infoHalykSale{lang}", f"utter_q2{lang}"],
            "conditionsHalykSale": [f"utter_conditionsHalykSale{lang}", f"utter_q9{lang}"],
            "mortgageBazisa": [f"utter_infoBazisA{lang}", f"utter_q2{lang}"],
            "mortgageBiGroup": [f"utter_infoBiGroup{lang}", f"utter_q2{lang}"],
            "conditionsBiGroup": [f"utter_conditionsBiGroup{lang}", f"utter_q9{lang}"],
            "mortgageHalyk": [f"utter_infoHalyk{lang}", f"utter_q2{lang}"],
            "conditionsHalyk": [f"utter_conditionsHalyk{lang}", f"utter_q2{lang}"],
            "when72025": [f"utter_when72025{lang}", f"utter_q2{lang}"],
            "bet": [f"utter_whatIsBet{lang}", f"utter_q2{lang}"],
            "whatIsDigital": [f"utter_digitalCarLoans{lang}", f"utter_q2{lang}"],
            "autoDigitalCredit": [f"utter_digitalAutoLoanProcess{lang}", f"utter_q16{lang}"],
            "autoDigitalCreditConditions": [f"utter_digitalAutoLoanTerms{lang}", f"utter_q18{lang}"],
            "aboutTwoAutoCredit": [f"utter_aboutTwoAutoCredit{lang}", f"utter_q16{lang}"],
            "autoPreferentialCredit": [f"utter_autoPreferentialCredit{lang}", f"utter_q19{lang}"],
            "autoPreferentialCreditConditions": [f"utter_autoPreferentialCreditConditions{lang}", f"utter_q20{lang}"],
            "exactProcentBet": [f"utter_exactProcentBet{lang}", f"utter_q2{lang}"],
            "interestRate": [f"utter_interestRate{lang}", f"utter_q10{lang}"],
            "refinancing": [f"utter_refinancing{lang}", f"utter_q11{lang}"],
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
            "changeLangKZ": ["utter_digitalAutoLoanProcessKZ", "utter_q16KZ"],
            "changeLangRU": ["utter_digitalAutoLoanProcessRU", "utter_q16RU"],
            "repeat": [f"utter_repeatDigitalAutoLoanProcess{lang}", f"utter_q16{lang}"],
            "soundlessly": [f"utter_soundLessly{lang}", f"utter_digitalAutoLoanProcess{lang}", f"utter_q16{lang}"],
            "yes": [f"utter_q17{lang}"],
            "no": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q16{lang}"],
            "callBack": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "bankBrunch": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "knowHow": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "seeSolution": [f"utter_whereToSeeSolution{lang}", f"utter_q16{lang}"],
            "stateDuty": [f"utter_whereToPayStateDuty{lang}", f"utter_q16{lang}"],
            "whereSign": [f"utter_whereSign{lang}", f"utter_q16{lang}"],
        }

        to_operator = ['iCant', 'later', 'internet', 'branchAddress']

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []

            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))

            return actions
        elif last_intent in to_operator:
            dispatcher.utter_message(response = f"utter_toOperatorICant{lang}")
            return [ActionExecuted(f"utter_toOperatorICant{lang}"), ConversationPaused()]
        elif last_intent == "robot":
            return [FollowupAction("action_robot")]
        elif last_intent == "operator":
            return [FollowupAction("action_operator")]
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
            "changeLangKZ": ["utter_q17KZ"],
            "changeLangRU": ["utter_q17RU"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q17{lang}"],
            "repeat": [f"utter_silence{lang}", f"utter_q17{lang}"],
            "soundlessly": [f"utter_soundLessly{lang}", f"utter_q17{lang}"],
            "newCar": [f"utter_newCar{lang}", f"utter_q2{lang}"],
            "withMileageCar": [f"utter_withMileageCar{lang}", f"utter_q2{lang}"],
            "newAndWithMileageCars": [f"utter_newAndWithMileageCars{lang}", f"utter_q2{lang}"],
            "newElectroCar": [f"utter_newElectroCar{lang}", f"utter_q2{lang}"],
            "withMileageElectroCar": [f"utter_withMileageElectroCar{lang}", f"utter_q2{lang}"],
            "newAndWithMileageElectroCars": [f"utter_newAndWithMileageElectroCars{lang}", f"utter_q2{lang}"],
            "aboutEverythingCars": [f"utter_aboutEverythingCars{lang}", f"utter_q2{lang}"],
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
            "yes": [f"utter_digitalAutoLoanProcess{lang}", f"utter_q16{lang}"],
            "no": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q18{lang}"],
            "repeat": [f"utter_repeatDigitalAutoLoanTerms{lang}", f"utter_q18{lang}"],
            "iCant": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "callBack": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "later": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "internet": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "knowHow": [f"utter_understood{lang}", f"utter_q2{lang}"],
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
            "changeLangRU": ["utter_autoPreferentialCreditRU", "utter_q19RU"],
            "changeLangKZ": ["utter_autoPreferentialCreditKZ", "utter_q19KZ"],
            "yes": [f"utter_waitingAtBank{lang}", f"utter_q2{lang}"],
            "no": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "repeat": [f"utter_autoPreferentialCredit{lang}", f"utter_q19{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q19{lang}"],
            "soundlessly": [f"utter_soundLessly{lang}", f"utter_autoPreferentialCredit{lang}", f"utter_q19{lang}"],
            "iCant": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "callBack": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "later": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "bankBrunch": [f"utter_bankBrunch{lang}", f"utter_q19{lang}"],
            "busy": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "internet": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "knowHow": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "branchAddress": [f"utter_bankBrunch{lang}", f"utter_q19{lang}"],
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
            "whoIsIt": [f"utter_autoPreferentialCredit{lang}", f"utter_q19{lang}"],
            "whoIsIt": [f"utter_langDetect{lang}", f"utter_q19{lang}"],
            "callBack": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "later": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "busy": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "knowHow": [f"utter_understood{lang}", f"utter_q2{lang}"],
            "permanentBasis": [f"utter_permanentBasis{lang}", f"utter_q20{lang}"],
        }

        to_operator = ['iCant', 'internet']

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []

            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))

            return actions
        elif last_intent in to_operator:
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