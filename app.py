from flask import Flask, render_template, request, jsonify, send_file, abort
import os
import uuid
import pandas as pd
import shutil
from functions import check_ted_policy, parse_csv
from urllib.parse import unquote


app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
user_id = str(uuid.uuid4())[:8]
file_path = f'uploads/user_{user_id}'
folder_name = 'default'
csvInput = ''

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/submit', methods=['POST'])
def submit():
    global csvInput
    data = request.get_json()
    selected_ids = data.get('selected', [])
    csvInput = data.get('csvInput', '')
    response_data = {}

    for cube_id in selected_ids:
        if cube_id == "checkTed":
            response = check_ted_policy(file_path)
            # response_data[cube_id] = "Проверка на TedPolicy завершена."
            print(response)
            response_data[cube_id] = response
        elif cube_id == "testList":
            response_data[cube_id] = "Создана таблица для тестирования."
        elif cube_id == "csv":
            response_data[cube_id] = "Ваши файлы: <a href='/download_csv' target='_blank' class='download-link'>Скачать CSV</a> <a href='/download_excel' target='_blank' class='download-link'>Скачать Excel</a>"
        elif cube_id == "audioProcessing":
            response_data[cube_id] = "Обработка аудио выполнена."
        else:
            response_data[cube_id] = f"Ответ для {cube_id}"
    
    return jsonify({"message": "Данные обработаны", "responses": response_data})

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
        "nlu": "data/nlu.yml"
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


if __name__ == '__main__':
    # app.run(host='0.0.0.0', port=5000)
    app.run(debug=True)  # Запуск сервера