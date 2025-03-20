import requests
import json
from requests.auth import HTTPBasicAuth


def get_gosusluga_status(iin):
    print('API: getGosUslugaStatus')

    # data = {'username': 'TEST', 'password': 'test1111'}
    # 
    # data = {
    #     'username': 'IVR_ROBOT',
    #     'password': 'IVR_ROBOT1111'
    # }

    iin = '941219351509'

    headers = {"Content-Type": "application/json"}

    url_getGosUslugaStatus = f'https://test-govtech.halykbank.nb/statuses/api/v1/iin/{iin}'

    # try:
    #     response = requests.get(url_getGosUslugaStatus, headers=headers, verify=False)
    # except Exception as err:
    #     print(str(err))
    #     response = None
    
    try:
        response = {
            "status": 200,
            "message": "OK",
            "request_id": "360c05082472811daa00949015e60738",
            "version": "0.0.1",
            "timestamp": "2023-12-04T11:36:51.154404833+06:00",
            "data": [{
                "id": 1481235,
                "iin": "010407551606",
                "created_at": "2023-12-04T10:04:00.548739Z",
                "updated_at": "2023-12-04T10:04:00.548739Z",
                "status": 'APPROVED',
                "title_ru": "Сервис регистрации транспортного средства",
                "title_kz": "Сервис регистрации транспортного средства",
                "service_id": 38
            },{
                "id": 1481233,
                "iin": "010407551606",
                "created_at": "2023-12-04T09:34:54.008485Z",
                "updated_at": "2023-12-04T09:34:54.008485Z",
                "status": 'DONE',
                "title_ru": "Сервис регистрации транспортного средства",
                "title_kz": "Сервис регистрации транспортного средства",
                "service_id": 38
            },]
        }

    except Exception as err:
        print(str(err))
        response = None
    
    return response
