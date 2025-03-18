from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import ActionExecuted, SlotSet, FollowupAction, ConversationPaused
import redis, time, json, pandas as pd, random, os, yaml, requests

ENVIORENMENT = os.environ.get("ENVIORENMENT", "dev")

if ENVIORENMENT == "PROD":
    config_file = "endpoints_prod.yml"
    with open(f"/rasa/{config_file}") as file:
        config_file = yaml.full_load(file)
    redis_ip = config_file["engine_redis"]["url"]
    redis_port = config_file["engine_redis"]["port"]
    redis_db_number = config_file["engine_redis"]["db"]
    redis_password = config_file["engine_redis"]["pass"]

else:
    redis_ip = "172.16.55.15"
    redis_password = "eg_redis_pass"
    redis_port = 6379
    redis_db_number = 0

engine_redis = redis.Redis(
    host=redis_ip, port=redis_port, db=redis_db_number, password=redis_password
)


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
            'overdue_debt': ['noReceipt', 'checkingTheAmount', 'monthlyPayment', 'debt', 'earlyRepayment',
                             'remainingDebt'],
            'super_app': ['publicServices'],
            'credit_card': ['smsWithOverdue', 'amountTotalDebt', 'howMuchNeedPay'],
            'forgot_card': ['whenBackCard', 'longCollectionATM', 'howGetMoneyWithoutCard', 'cardNotDelivery15Day'],
            'card_delivery': ['card_not_displayed_in_app', 'card_issue_rejection_reason'],
            'reset_pin': ['setPinCard', 'epinNotReceived'],
            'sysn': ['cardDetails'],
            'card_operation': ['card_balance'],
        }

        need_ident = False

        for k, v in need_ident_or_not.items():
            if last_intent == k:
                if internal_intent in v:
                    need_ident = True

        return need_ident
    except Exception as e:
        need_ident = True  # если не получиться вытащить интент, пройдет идентификацию
        return need_ident


def get_all_utters(events: List[Dict[Text, Any]]) -> List[Text]:
    """
    Функция, которая проходит по событиям и возвращает список действий бота, начинающихся с 'utter_'.

    Аргументы:
    - events: список событий из трекера.

    returns:
    - a list of all utters that were present during the conversation
    """
    all_utters = []
    for event in events:
        if event['event'] == 'action' and event['name'].startswith('utter_'):
            all_utters.append(event['name'])
    return all_utters

def get_utters_between_two_intents(events: List[Dict[Text, Any]]) -> List[Text]:
    """
    returns:
    - a list of all utters that were between the last two intents(user events)
    """
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
    print(f_lang)

    if f_lang and f_lang[-1] != '':
        lang = f_lang[-1].upper()
    elif all_utters:
        last_utter = all_utters[-1]
        lang = last_utter[-2:]
        print("язык предыдущего уттера:", lang)
    else:
        lang = dict_to_redis['language'].upper()

    print("язык c редиса:", lang)
    last_utter = f"utter_q1{lang}"

    return lang, last_utter

class ActionRepeat(Action):
    def name(self) -> Text:
        return "action_repeat"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        events = tracker.events
        del events[-2:]
        rev_events = reversed(events)
        # print(events)
        responses = []
        for j in rev_events:
            # print(j)
            if j['event'] == 'bot':
                responses.append(j['metadata']['utter_action'])
            elif j['event'] == 'user':
                break
            else:
                continue
        print(responses)


        for utter in reversed(responses):
            response = utter
            # print(response)
            dispatcher.utter_message(response=response)
        return [ActionExecuted(i) for i in reversed(responses)]

class ActionChangeLang(Action):
    def name(self) -> Text:
        return "action_changelang"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        events = tracker.events
        all_utters = get_utters_between_two_intents(events)

        last_intent = tracker.latest_message['intent']['name']

        lang = last_intent[-2:]

        exceptions = ["utter_soundLesslyRU", "utter_soundLesslyKZ"]

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

        return returns

class ActionCounterRU(Action):
    def name(self) -> Text:
        return "action_counterRU"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        events = tracker.events
        all_actions = []
        for i in events:
            if i['event'] == 'action' and i['name'].startswith('utter_'):
                all_actions.append(i['name'])
        if not all_actions:  # Проверяем, что список не пуст
            response = "utter_q1RU"  # Ответ по умолчанию, если действий нет
            dispatcher.utter_message(response=response)
            return [ActionExecuted(response)]
        last_2 = all_actions[-7:]
        cur_q = str(all_actions[-1])
        if cur_q in ['utter_q3RU', 'utter_q4RU', 'utter_interruptingRU', 'utter_q5RU', 'utter_q7RU', 'utter_repeat_questionRU']:
            cur_q = 'utter_q1RU'
        a = 0
        for i in last_2:
            if str(i) == cur_q:
                a += 1
            else:
                continue

        if a == 3:
            response = "utter_operatorRU"
            dispatcher.utter_message(response=response)
            return [ActionExecuted(response), ConversationPaused()]
        else:
            response = cur_q
            dispatcher.utter_message(response=response)
            return [ActionExecuted(response)]

class ActionCounterKZ(Action):
    def name(self) -> Text:
        return "action_counterKZ"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        events = tracker.events
        all_actions = []

        if not all_actions:
            dispatcher.utter_message(response="utter_q1KZ")
            return [ActionExecuted("utter_q1KZ")]

        for i in events:
            if i['event'] == 'action' and i['name'].startswith('utter_'):
                all_actions.append(i['name'])
        if not all_actions:  # Проверяем, что список не пуст
            response = "utter_q1KZ"  # Ответ по умолчанию, если действий нет
            dispatcher.utter_message(response=response)
            return [ActionExecuted(response)]

        last_2 = all_actions[-7:]
        cur_q = str(all_actions[-1])
        if cur_q in ['utter_q3KZ', 'utter_q4KZ', 'utter_interruptingKZ', 'utter_q5KZ', 'utter_q7KZ', 'utter_repeat_questionKZ']:
            cur_q = 'utter_q1KZ'
        a = 0
        for i in last_2:
            if str(i) == cur_q:
                a += 1
            else:
                continue

        if a == 3:
            response = "utter_operatorKZ"
            dispatcher.utter_message(response=response)
            return [ActionExecuted(response), ConversationPaused()]
        else:
            response = cur_q
            dispatcher.utter_message(response=response)
            return [ActionExecuted(response)]

# class ActionOperator(Action):
#     def name(self) -> Text:
#         return "action_operator"
#
#     def run(self, dispatcher: CollectingDispatcher,
#             tracker: Tracker,
#             domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
#         print("\nВНУТРИ action_operator")
#
#         events = tracker.events
#         all_utters = get_all_utters(events)
#
#         uuid = tracker.current_state()['sender_id']
#         dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))
#
#         if all_utters:
#             last_utter = all_utters[-1]
#             lang = last_utter[-2:]
#             print("язык предыдущего уттера:", lang)
#         else:
#             lang = dict_to_redis['language'].upper()
#
#             print("язык c редиса:", lang)
#             last_utter = f"utter_q1{lang}"
#
#         print(lang)
#         print(last_utter)
#
#         for_q5 = ["utter_q1RU", "utter_q3RU", "utter_q4RU", "utter_q7RU", "utter_q1KZ", "utter_q3KZ", "utter_q4KZ",
#                   "utter_q7KZ", "utter_interruptingRU", "utter_interruptingKZ"]
#
#         operator = dict_to_redis['operator_counter']
#         if operator > 0:
#             dispatcher.utter_message(response=f"utter_toOperator{lang}")
#             return [ActionExecuted(f"utter_toOperator{lang}"), ConversationPaused()]
#         else:
#             if last_utter in for_q5:
#                 dispatcher.utter_message(response=f"utter_q5{lang}")
#                 return [ActionExecuted(f"utter_q5{lang}")]
#             else:
#                 dispatcher.utter_message(response=f"utter_justOperator{lang}")
#                 dispatcher.utter_message(response=last_utter)
#                 return [ActionExecuted(f"utter_justOperator{lang}"), ActionExecuted(last_utter)]
#
# class ActionRobot(Action):
#     def name(self) -> Text:
#         return "action_robot"
#
#     def run(self, dispatcher: CollectingDispatcher,
#             tracker: Tracker,
#             domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
#         print("\nВНУТРИ action_robot")
#
#         events = tracker.events
#         all_utters = get_all_utters(events)
#
#         uuid = tracker.current_state()['sender_id']
#         dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))
#
#         if all_utters:
#             last_utter = all_utters[-1]
#             lang = last_utter[-2:]
#             print("язык предыдущего уттера:", lang)
#         else:
#             lang = dict_to_redis['language'].upper()
#
#             print("язык c редиса:", lang)
#             last_utter = f"utter_q1{lang}"
#
#         last_intent = tracker.latest_message['intent']['name']
#         print("last utter:", last_utter)
#         print("last intent:", last_intent)
#
#         exceptions = ["utter_q4RU", "utter_q3RU", "utter_q5RU", "utter_q7RU", "utter_q4KZ", "utter_q3KZ", "utter_q5KZ",
#                       "utter_q7KZ", "utter_interruptingRU", "utter_interruptingKZ"]
#
#         if last_utter in exceptions:
#             last_utter = f"utter_q1{lang}"
#
#         # robot redis
#         robot = dict_to_redis['robot_counter']
#
#         if robot > 1:
#             dispatcher.utter_message(response=f'utter_robotThird{lang}')
#             dispatcher.utter_message(response=f'utter_toOperator{lang}')
#             return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
#         elif robot == 1:
#             dispatcher.utter_message(response=f'utter_robotSecond{lang}')
#             dispatcher.utter_message(response=last_utter)
#             robot += 1
#             dict_to_redis['robot_counter'] = robot
#             engine_redis.set(uuid, json.dumps(dict_to_redis))
#             return [ActionExecuted(f'utter_robotSecond{lang}'), ActionExecuted(last_utter)]
#         else:
#             dispatcher.utter_message(response=f'utter_robotFirst{lang}')
#             dispatcher.utter_message(response=last_utter)
#             robot += 1
#             dict_to_redis['robot_counter'] = robot
#             engine_redis.set(uuid, json.dumps(dict_to_redis))
#             return [ActionExecuted(f'utter_robotSecond{lang}'), ActionExecuted(last_utter)]

# class ActionOperatorDeepQRU(Action):
#     def name(self) -> Text:
#         return "action_operatorDeepQRU"
#
#     def run(self, dispatcher: CollectingDispatcher,
#             tracker: Tracker,
#             domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
#
#         operator_counter = int(tracker.get_slot('operator_counter'))
#
#         events = tracker.events
#         all_actions = []
#         for i in events:
#             if i['event'] == 'action' and i['name'].startswith('utter_'):
#                 all_actions.append(i['name'])
#             else:
#                 continue
#
#         cur_q = str(all_actions[-1])
#
#         if operator_counter == 0:
#             response = "utter_q5RU"
#             dispatcher.utter_message(response=response)
#             dispatcher.utter_message(response=cur_q)
#             operator_counter += 1
#             return [ActionExecuted(response), ActionExecuted(cur_q), SlotSet('operator_counter', operator_counter)]
#         else:
#             response = "utter_toOperatorRU"
#             dispatcher.utter_message(response=response)
#             return [ActionExecuted(response), ConversationPaused()]
#
#
#
# class ActionOperatorDeepQKZ(Action):
#     def name(self) -> Text:
#         return "action_operatorDeepQKZ"
#
#     def run(self, dispatcher: CollectingDispatcher,
#             tracker: Tracker,
#             domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
#
#         operator_counter = int(tracker.get_slot('operator_counter'))
#
#         events = tracker.events
#         all_actions = []
#         for i in events:
#             if i['event'] == 'action' and i['name'].startswith('utter_'):
#                 all_actions.append(i['name'])
#             else:
#                 continue
#
#         cur_q = str(all_actions[-1])
#
#         if operator_counter == 0:
#             response = "utter_q5KZ"
#             dispatcher.utter_message(response=response)
#             dispatcher.utter_message(response=cur_q)
#             operator_counter += 1
#             return [ActionExecuted(response), ActionExecuted(cur_q), SlotSet('operator_counter', operator_counter)]
#         else:
#             response = "utter_toOperatorKZ"
#             dispatcher.utter_message(response=response)
#             return [ActionExecuted(response), ConversationPaused()]
#
#
# class ActionRobotRU(Action):
#     def name(self) -> Text:
#         return "action_robotCounterRU"
#
#     def run(self, dispatcher: CollectingDispatcher,
#             tracker: Tracker,
#             domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
#         robot_counter = int(tracker.get_slot('robot_counter'))
#
#         events = tracker.events
#         all_actions = []
#         for i in events:
#             if i['event'] == 'action' and i['name'].startswith('utter_'):
#                 all_actions.append(i['name'])
#             else:
#                 continue
#
#         cur_q = str(all_actions[-1])
#         if cur_q in ['utter_q3RU', 'utter_q4RU', 'utter_interruptingRU', 'utter_q7RU']:
#             cur_q = 'utter_q1RU'
#
#         if robot_counter == 0:
#             dispatcher.utter_message(response='utter_robotFirstRU')
#             dispatcher.utter_message(response=cur_q)
#             robot_counter += 1
#             return [ActionExecuted('utter_robotFirstRU'), SlotSet('robot_counter', robot_counter), ActionExecuted(cur_q)]
#         elif robot_counter == 1:
#             dispatcher.utter_message(response='utter_robotSecondRU')
#             dispatcher.utter_message(response=cur_q)
#             robot_counter += 1
#             return [ActionExecuted('utter_robotSecondRU'), SlotSet('robot_counter', robot_counter), ActionExecuted(cur_q)]
#         else:
#             dispatcher.utter_message(response='utter_robotThirdRU')
#             dispatcher.utter_message(response="utter_toOperatorRU")
#             robot_counter += 1
#             return [ActionExecuted('utter_robotSecondRU'), ActionExecuted("utter_toOperatorRU"), ConversationPaused()]
#
#
# class ActionRobotKZ(Action):
#     def name(self) -> Text:
#         return "action_robotCounterKZ"
#
#     def run(self, dispatcher: CollectingDispatcher,
#             tracker: Tracker,
#             domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
#         robot_counter = int(tracker.get_slot('robot_counter'))
#
#         events = tracker.events
#         all_actions = []
#         for i in events:
#             if i['event'] == 'action' and i['name'].startswith('utter_'):
#                 all_actions.append(i['name'])
#             else:
#                 continue
#
#         cur_q = str(all_actions[-1])
#         if cur_q in ['utter_q3KZ', 'utter_q4KZ', 'utter_interruptingKZ', 'utter_q7KZ']:
#             cur_q = 'utter_q1KZ'
#
#         if robot_counter == 0:
#             dispatcher.utter_message(response='utter_robotFirstKZ')
#             dispatcher.utter_message(response=cur_q)
#             robot_counter += 1
#             return [ActionExecuted('utter_robotFirstKZ'), SlotSet('robot_counter', robot_counter), ActionExecuted(cur_q)]
#         elif robot_counter == 1:
#             dispatcher.utter_message(response='utter_robotSecondKZ')
#             dispatcher.utter_message(response=cur_q)
#             robot_counter += 1
#             return [ActionExecuted('utter_robotSecondKZ'), SlotSet('robot_counter', robot_counter), ActionExecuted(cur_q)]
#         else:
#             dispatcher.utter_message(response='utter_robotThirdKZ')
#             dispatcher.utter_message(response="utter_toOperatorKZ")
#             robot_counter += 1
#             return [ActionExecuted('utter_robotSecondKZ'), ActionExecuted("utter_toOperatorKZ"), ConversationPaused()]

class ActionOperator(Action):
    def name(self) -> Text:
        return 'action_operator'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_operator')

        events = tracker.events
        all_utters = get_all_utters(events)

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        # Определяем язык
        if all_utters:
            last_utter = all_utters[-1]
            lang = last_utter[-2:]
            print('язык предыдущего уттера:', lang)
        else:
            lang = dict_to_redis['language'].upper()
            print('язык c редиса:', lang)
            last_utter = f'utter_q1{lang}'

        print(lang)
        print(last_utter)

        # Список уттеров для q5
        for_q5 = [
            'utter_q1RU', 'utter_q3RU', 'utter_q4RU', 'utter_q7RU',
            'utter_q1KZ', 'utter_q3KZ', 'utter_q4KZ', 'utter_q7KZ',
            'utter_interruptingRU', 'utter_interruptingKZ'
        ]

        operator = tracker.get_slot('operator_counter')
        if operator is None:
            operator = 0
        print('operator_counter before append:', operator)

        # Логика обработки
        if operator > 0:
                dispatcher.utter_message(response=f'utter_toOperator{lang}')
                return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
        else:
            if last_utter in for_q5:
                dispatcher.utter_message(response=f'utter_q5{lang}')
                operator += 1
                print('operator_counter after append:', operator)
                return [SlotSet('operator_counter', operator), ActionExecuted(f'utter_q5{lang}')]
            else:
                dispatcher.utter_message(response=f'utter_justOperator{lang}')
                dispatcher.utter_message(response=last_utter)
                operator += 1
                print('operator_counter after append::', operator)
                return [
                    SlotSet('operator_counter', operator),
                    ActionExecuted(f'utter_justOperator{lang}'),
                    ActionExecuted(last_utter)
                ]

class ActionRobot(Action):
    def name(self) -> Text:
        return 'action_robot'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_robot')

        events = tracker.events
        all_utters = get_all_utters(events)

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        if all_utters:
            last_utter = all_utters[-1]
            lang = last_utter[-2:]
            print('язык предыдущего уттера:', lang)
        else:
            lang = dict_to_redis['language'].upper()

            print('язык c редиса:', lang)
            last_utter = f'utter_q1{lang}'

        last_intent = tracker.latest_message['intent']['name']
        print('last utter:', last_utter)
        print('last intent:', last_intent)

        exceptions = ['utter_q4RU', 'utter_q3RU', 'utter_q5RU', 'utter_q7RU', 'utter_q4KZ', 'utter_q3KZ', 'utter_q5KZ',
                      'utter_q7KZ', 'utter_interruptingRU', 'utter_interruptingKZ']

        if last_utter in exceptions:
            last_utter = f'utter_q1{lang}'

        robot = tracker.get_slot('robot_counter')
        if robot is None:
            robot = 0
        print('robot_counter before append:', robot)

        if robot > 1:
            dispatcher.utter_message(response=f'utter_robotThird{lang}')
            dispatcher.utter_message(response=f'utter_toOperator{lang}')
            return [ActionExecuted(f'utter_toOperator{lang}'), ConversationPaused()]
        elif robot == 1:
            dispatcher.utter_message(response=f'utter_robotSecond{lang}')
            dispatcher.utter_message(response=last_utter)

            robot += 1
            print('robot_counter after append:', robot)

            return [SlotSet('robot_counter', robot), ActionExecuted(f'utter_robotSecond{lang}'),
                    ActionExecuted(last_utter)]
        else:
            dispatcher.utter_message(response=f'utter_robotFirst{lang}')
            dispatcher.utter_message(response=last_utter)

            robot += 1
            print('robot_counter after append:', robot)

            return [SlotSet('robot_counter', robot), ActionExecuted(f'utter_robotFirst{lang}'),
                    ActionExecuted(last_utter)]

class ActionSoundlesslyRU(Action):
    def name(self) -> Text:
        return "action_soundlesslyRU"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        events = tracker.events
        del events[-2:]
        rev_events = reversed(events)
        print(events)
        responses = []

        for j in rev_events:
            print(j)
            if j['event'] == 'bot':
                responses.append(j['metadata']['utter_action'])
            elif j['event'] == 'user':
                break
            else:
                continue
        print(responses)

        utter_s = 'utter_soundLesslyRU'
        if utter_s not in responses:
            responses.append(utter_s)

        for utter in reversed(responses):
            response = utter
            print(response)
            dispatcher.utter_message(response=response)
        return [ActionExecuted(i) for i in reversed(responses)]

class ActionSoundlesslyKZ(Action):
    def name(self) -> Text:
        return "action_soundlesslyKZ"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        events = tracker.events
        del events[-2:]
        rev_events = reversed(events)
        responses = []

        for j in rev_events:
            if j['event'] == 'bot':
                responses.append(j['metadata']['utter_action'])
            elif j['event'] == 'user':
                break
            else:
                continue
        print(responses)

        utter_s = 'utter_soundLesslyKZ'
        if utter_s not in responses:
            responses.append(utter_s)

        for utter in reversed(responses):
            response = utter
            dispatcher.utter_message(response=response)
        return [ActionExecuted(i) for i in reversed(responses)]

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

class ActionSwitchToAnotherScript(Action):

    def name(self) -> Text:
        return "action_switchToAnotherScript"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_switchToAnotherScript", flush=True)

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))

        local_time = int(time.time())
        identified = dict_to_redis['identified']
        robot_list = dict_to_redis['robot_list']
        trusted_phone = dict_to_redis['trusted_phone']
        print("identified:", identified, flush=True)
        print("robot_list:", robot_list, flush=True)
        print("trusted_phone:", trusted_phone, flush=True)

        last_intent = tracker.latest_message['intent']['name']
        need_ident = ['limits', 'block_card']

        f_lang = dict_to_redis['f_language']
        if len(f_lang) > 1:
            language = f_lang[-1].upper()
        else:
            language = dict_to_redis['language'].upper()

        if identified is None and trusted_phone is True:
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
        except:
            dispatcher.utter_message(response=f'utter_toOperator{language}')
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
        dict_to_redis['robot_durations']['halyk_bank_brokerage']['end_datetime'] = local_time
        robot_durations = dict_to_redis['robot_durations']
        robot_durations[f'halyk_bank_{scripttype}'] = {'start_datetime': local_time}

        dict_to_redis['robot_durations'] = robot_durations
        engine_redis.set(uuid, json.dumps(dict_to_redis))

        print("After append:", robot_list, flush=True)

        engine_redis.set(uuid, json.dumps(dict_to_redis))
        engine_metadata_key = uuid + '-engine_metadata'
        engine_metadata_record = json.loads(engine_redis.get(engine_metadata_key).decode('utf-8'))
        engine_metadata_record['reload_template'] = True
        engine_redis.set(engine_metadata_key, json.dumps(engine_metadata_record))

        dispatcher.utter_message(response = f"utter_repeat_question{language}")
        return [FollowupAction(f"utter_repeat_question{language}")]

class ActionEmpty(Action):

    def name(self) -> Text:
        return "action_empty"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_empty")

        events = tracker.events
        all_utters = get_all_utters(events)

        last_utter = all_utters[-1] if all_utters else "utter_q1RU"
        print("last utter:", last_utter)

        lang = last_utter[-2:]
        print("язык предыдущего уттера:", lang)

        return[ActionExecuted(f'utter_q1{lang}')]

class ActionAfterQ1(Action):

    def name(self) -> Text:
        return 'action_q1'

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print('\nВНУТРИ action_q1')

        events = tracker.events

        all_utters = []
        for event in events:
            if event['event'] == 'action' and event['name'].startswith('utter_'):
                all_utters.append(event['name'])

        uuid = tracker.current_state()['sender_id']
        dict_to_redis = json.loads(engine_redis.get(uuid).decode('utf-8'))
        robot_counter = dict_to_redis['robot_counter']
        operator_counter = dict_to_redis['operator_counter']
        print("robot_counter:", robot_counter)
        print("operator_counter:", operator_counter)

        f_lang = dict_to_redis['f_language']
        print('f_lang', f_lang)
        last_utter = None
        if all_utters:
            last_utter = all_utters[-1]
            lang = last_utter[-2:]
            print("язык предыдущего уттера:", lang)
        else:
            if f_lang and f_lang[-1] != '':
                lang = f_lang[-1].upper()
            else:
                lang = dict_to_redis['language'].upper()

        last_intent = tracker.latest_message['intent']['name']

        print('last utter:', last_utter)
        print('last intent:', last_intent)
        print('lang:', lang)

        intents_utters = {
            'langDetectRU': ['utter_q4RU'],
            'langDetectKZ': ['utter_q4KZ'],
            'changeLangKZ': ['utter_q1KZ'],
            'changeLangRU': ['utter_q1RU'],
            'no': [f'utter_q2{lang}'],
            'idk': [f'utter_q2{lang}'],
            'whoIsIt': [f'utter_langDetect{lang}', f'utter_q1{lang}'],
            'soundlessly': [f'utter_q3{lang}'],
            'haveQuestion': [f'utter_q7{lang}'],
            'interrupting': [f'utter_interrupting{lang}'],
            'wait': [f'utter_okWait{lang}', f'utter_q1{lang}'],
            'stockNoView': [f'utter_globalCaseHalyk{lang}', f'utter_q2{lang}'],
            'investNoOpen': [f'utter_q8{lang}'],
            'stockAnalystAct': [f'utter_q9{lang}'],
            'bagQues': [f'utter_q10{lang}'],
            'freeMoneyAct': [f'utter_q11{lang}'],
        }

        to_another_script = {"loans_mortgage", "limits", "forgot_card", "reset_pin", "card_operation", "current_loan",
                             "card_delivery", "credit_card", "new_loan",
                             "block_card", "overdue_debt", "sysn", "super_app", "kino_kz", "registration",
                             "payments_and_transfers", "halyk_travel", "addresses_branches", "remove_the_limit"}

        if last_intent in intents_utters:
            print("last_intent in intents_utters")
            messages = intents_utters[last_intent]
            actions = []

            for message in messages:
                dispatcher.utter_message(response=message)
                actions.append(ActionExecuted(message))

            return [SlotSet('robot_counter', robot_counter), SlotSet('operator_counter', operator_counter), *actions]
        elif last_intent == 'another':
            dispatcher.utter_message(response=f"utter_toOperatorICant{lang}")
            return [SlotSet('robot_counter', robot_counter), SlotSet('operator_counter', operator_counter),
                    ActionExecuted(f"utter_toOperatorICant{lang}"), ConversationPaused()]
        elif last_intent in to_another_script:
            dispatcher.utter_message(response=f'utter_q1{lang}')
            return [SlotSet('robot_counter', robot_counter), SlotSet('operator_counter', operator_counter),
                    ActionExecuted(f'utter_q1{lang}')]
        elif last_intent == "robot":
            return [SlotSet('robot_counter', robot_counter), SlotSet('operator_counter', operator_counter),
                    FollowupAction(f"action_robot")]
        elif last_intent == "operator":
            return [SlotSet('robot_counter', robot_counter), SlotSet('operator_counter', operator_counter),
                    FollowupAction(f"action_operator")]
        else:
            return [SlotSet('robot_counter', robot_counter), SlotSet('operator_counter', operator_counter),
                    FollowupAction(f"action_counter{lang}")]

class ActionAnotherOperator(Action):
    def name(self) -> Text:
        return "action_another_operator"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        events = tracker.events
        all_utters = get_all_utters(events)
        last_utter = all_utters[-1] if all_utters else 'utter_q1RU'
        lang = last_utter[-2:]
        print('язык предыдущего уттера:', lang)

        dispatcher.utter_message(response=f'utter_toOperatorICant{lang}')
        return [ActionExecuted(f'utter_toOperatorICant{lang}'), ConversationPaused()]

class ActionScore(Action):

    def name(self) -> Text:
        return "action_score"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("\nВНУТРИ action_score", flush=True)

        events = tracker.events
        all_utters = get_all_utters(events)
        last_utter = all_utters[-1] if all_utters else 'utter_q1RU'
        lang = last_utter[-2:]

        uuid = tracker.current_state()['sender_id']
        engine_metadata_key = uuid + '-engine_metadata'
        engine_metadata_record = json.loads(engine_redis.get(engine_metadata_key).decode('utf-8'))

        last_message = tracker.latest_message['text']
        print('last_message: ', last_message, flush=True)
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
        print(score)
        print('Итоговый Score: ', score, flush=True)
        engine_metadata_record['npl'] = score
        engine_redis.set(engine_metadata_key, json.dumps(engine_metadata_record))

        dispatcher.utter_message(response=f'utter_goodBye{lang}')
        return [ActionExecuted(f'utter_goodBye{lang}'), ConversationPaused()]
