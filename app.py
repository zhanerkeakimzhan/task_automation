from flask import Flask, render_template, request, jsonify, send_file, abort
import os
import uuid
import pandas as pd
import shutil
from functions import check_ted_policy, parse_csv, check_test_list_name, prerecording_list, test_list
from console_main import audio_processing
from urllib.parse import unquote


app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
user_id = str(uuid.uuid4())[:8]
file_path = f'uploads/user_{user_id}'
wav_path = ''
folder_name = 'default'
csvInput = ''
testListInput = ''
audioProcessingInput = ''

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/submit', methods=['POST'])
def submit():
    global csvInput
    global testListInput
    data = request.get_json()

    selected_ids = data.get('selected', [])
    csvInput = data.get('csvInput', '')
    testListInput = data.get('testListInput', '')
    preRecordingInput = data.get('preRecordingInput', '')
    preRecordingListName = data.get('preRecordingListName', '')
    selectedGender = data.get('selectedGender', '')
    audioProcessingInput = data.get('audioProcessingInput', '')
    selectedLang = data.get('selectedLang', '')

    response_data = {}
    print(selected_ids)
    print(selectedGender)

    for cube_id in selected_ids:
        if cube_id == "checkTed":
            response = check_ted_policy(file_path)
            # response_data[cube_id] = "Проверка на TedPolicy завершена."
            print(response)
            response_data[cube_id] = response
        elif cube_id == "preRecording":
            domain = f'{file_path}/domain.yml'
            response = prerecording_list(domain, selectedGender, preRecordingInput, preRecordingListName)
            print(response)
            response_data[cube_id] = response
        elif cube_id == "testList":
            response = test_list(file_path, testListInput)
            print(response)
            response_data[cube_id] = response
        elif cube_id == "csv":
            response_data[cube_id] = "Ваши файлы: <a href='/download_csv' target='_blank' class='download-link'>Скачать CSV</a> <a href='/download_excel' target='_blank' class='download-link'>Скачать Excel</a>"
        elif cube_id == "audioProcessing":
            response = audio_processing(wav_path, selectedLang, audioProcessingInput)
            response_data[cube_id] = "Аудио обработано: <a href='/download_zip' target='_blank' class='download-link'>Скачать zip с аудио</a> "
        else:
            response_data[cube_id] = f"Ответ для {cube_id}"
    print(response_data)
    return jsonify({"message": "Данные обработаны", "responses": response_data})

@app.route('/check_list_exists')
def check_list_exists():
    name = request.args.get('name')
    exists = check_test_list_name(name)  # Функция, которая проверяет существование листа
    return jsonify({"exists": exists})


@app.route('/download_csv', methods=['GET'])
def download_csv():
    # file_path = create_excel_file()
    csv_file_path, excel_file_path = parse_csv(file_path, csvInput, folder_name)
    if not os.path.exists(csv_file_path):  # Проверяем, существует ли файл
        print(f"Файл не найден: {csv_file_path}")  # Вывод в логи сервера
        return abort(404, description="CSV файл не найден")  # Отправляем ошибку 404
    return send_file(csv_file_path, as_attachment=True, download_name=f"{folder_name}.csv",
                     mimetype="text/csv")


@app.route('/download_excel', methods=['GET'])
def download_excel():
    # file_path = create_excel_file()
    csv_file_path, excel_file_path = parse_csv(file_path, csvInput, folder_name)
    return send_file(excel_file_path, as_attachment=True, download_name=f"{folder_name}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

#обработка аудио
@app.route('/download_zip', methods=['GET'])
def download_zip():
    global wav_path
    folder_path = os.path.dirname(file_path)
    print(folder_path)

    zip_path = f'{folder_path}/{audioProcessingInput}'
    
    return send_file(zip_path, as_attachment=True, download_name="archive.zip", mimetype="application/zip")


@app.route('/delete_folder', methods=['POST'])
def delete_folder():
    if os.path.exists(file_path):
        try:
            shutil.rmtree(file_path, ignore_errors=True)
            return jsonify({"status": "success", "message": "Folder deleted"}), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    else:
        return jsonify({"status": "error", "message": "Folder not found"}), 404


@app.route('/upload', methods=['POST'])
def upload_files():
    global folder_name
    folder_name = request.form.get("folderName", "default_folder")

    required_files = {
        "domain": "domain.yml",
        "rules": "data/rules.yml",
        "stories": "data/stories.yml",
        "nlu": "data/nlu.yml",
        "actions": "actions/actions.py"
    }
    received_files = {}

    base_dir = os.path.join(UPLOAD_FOLDER, f"user_{user_id}")
    os.makedirs(base_dir, exist_ok=True)

    for key, relative_path in required_files.items():
        if key in request.files:
            file = request.files[key]

            # Полный путь к файлу
            file_path = os.path.join(base_dir, relative_path)

            # Создаем всю структуру папок
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            # Сохраняем файл
            file.save(file_path)
            received_files[key] = file_path  # Храним полный путь загруженного файла

    return jsonify({
        "message": "Файлы успешно загружены!",
        "user_folder": base_dir,
        "files": received_files
    }), 200

@app.route('/uploadWAV', methods=['POST'])
def upload_wav():
    global wav_path
    if "wavFile" not in request.files:
        return jsonify({"error": "Файл не найден!"}), 400

    file = request.files["wavFile"]

    if file.filename == "":
        return jsonify({"error": "Файл не выбран!"}), 400

    if not file.filename.lower().endswith(".wav"):
        return jsonify({"error": "Неверный формат файла! Требуется .wav"}), 400

    base_dir = os.path.join(UPLOAD_FOLDER, f"user_{user_id}")
    os.makedirs(base_dir, exist_ok=True)
    wav_path = f'{UPLOAD_FOLDER}/user_{user_id}/{file.filename}'
    file.save(wav_path)

    print(file.filename)
    print(wav_path)

    
    return jsonify({
        "message": "Файлы успешно загружены!",
        "user_folder": base_dir
    }), 200


if __name__ == '__main__':
    # app.run(host='0.0.0.0', port=5000)
    app.run(debug=True)  # Запуск сервера