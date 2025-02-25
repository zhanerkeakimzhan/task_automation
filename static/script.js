function toggleSelection(element) {
    element.classList.toggle("selected");
    // checkContinueButton();
}

document.addEventListener("DOMContentLoaded", function () {
    let csvCube = document.getElementById("csv");
    let csvInputContainer = document.getElementById("csvInputContainer");
    let csvInput = document.getElementById("csvInput");

    csvCube.addEventListener("click", function () {
        if (csvCube.classList.contains("selected")) {
            csvInputContainer.style.display = "flex"; // Показываем инпут
        } else {
            csvInputContainer.style.display = "none";  // Скрываем, если убрали выбор
            csvInput.value = ""; // Очищаем поле ввода
        }
    });
});


function submitSelection() {
    let selectedCubes = document.querySelectorAll(".cube.selected"); //Собирает все .cube, у которых есть класс "selected".
    let selectedIds = Array.from(selectedCubes).map(cube => cube.id); //Из каждого выбранного cube берет id и кладет в массив selectedIds.
    let csvInput = document.getElementById('csvInput').value.trim();
    console.log(csvInput)

    let data = { selected: selectedIds };
    if (selectedIds.includes("csv") && csvInput) {
        data.csvInput = csvInput;
    }

    if (selectedIds.length > 0) {
        fetch('/submit', { 
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data) //Отправляет POST-запрос на /submit, передавая массив selectedIds. { selected: ["id1", "id2", ...] } в формате JSON.
        })
        .then(response => response.json()) //Преобразует ответ от сервера в JSON.
        .then(data => {
            let modalContent = document.getElementById("modal-content");
            modalContent.innerHTML = ""; // Очищает содержимое #modal-content #modal-content — блок, в который вставят новый текст.
            
            console.log(JSON.stringify(data, null, 2)); // Логируем весь ответ

            if (!data.responses) {
                console.error("Поле 'responses' отсутствует в ответе");
                return;
            }

            let responses = data.responses; // Теперь responses — это объект с ключами

             // Перебираем все ключи из ответа
             Object.keys(responses).forEach(key => {
                let section = document.createElement("div");
                section.style.marginBottom = "15px";

                let title = document.createElement("h3");
                if (key == "checkTed") {
                    title.innerText = "Проверка на TedPolicy:";
                    section.appendChild(title);
                } else if (key == "testList"){
                    title.innerText = "Создание таблицы для тестировани:";
                    section.appendChild(title);
                } else if (key == "csv"){
                    title.innerText = "Создание CSV:";
                    section.appendChild(title);
                } else if (key == "audioProcessing"){
                    title.innerText = "Обработка аудио:";
                    section.appendChild(title);
                }

                if (Array.isArray(responses[key])) {
                    responses[key].forEach(item => {
                        let p = document.createElement("p");
                        p.innerText = item;
                        p.style.textAlign = "left";

                        // // Если ключ - checkTed, красим текст в красный
                        // if (key === "checkTed") {
                        //     p.style.color = "black";
                        // }

                        section.appendChild(p);
                    });
                } else {
                    let p = document.createElement("p");
                    p.style.textAlign = "left";
                    p.innerHTML = responses[key]; // Вставляем HTML (для ссылок в csv)
                    section.appendChild(p);
                }

                modalContent.appendChild(section);
            });
            
            // Object.values(data.responses).forEach(text => { //Перебирает responses из ответа сервера.
            //     let p = document.createElement("p");
            //     p.innerHTML = text; // Создает p и вставляет в него text
            //     modalContent.appendChild(p); //Добавляет p в modalContent
            // });

            // Если выбран CSV, показываем кнопку скачивания
            if (selectedIds.includes("csv")) {
                let csvDownload = document.createElement("a");
                csvDownload.href = "/download_csv";
                document.body.appendChild(csvDownload);
                csvDownload.click();
                document.body.removeChild(csvDownload);
            
                // Добавляем задержку перед скачиванием Excel
                setTimeout(() => {
                    let excelDownload = document.createElement("a");
                    excelDownload.href = "/download_excel";
                    document.body.appendChild(excelDownload);
                    excelDownload.click();
                    document.body.removeChild(excelDownload);
                }, 1000); // 500 мс задержка (можно увеличить, если не срабатывает)
            }
            
            showModal(); // Функция для отображения модального окна
        })
        .catch(error => console.error("Ошибка при загрузке данных:", error));
    } else {
        alert("Выберите хотя бы один вариант!");
    }
}

// Функция для отображения модального окна
function showModal() {
    let modal = document.getElementById("modal");
    modal.style.display = "block"; //Показывает #modal, устанавливая display: block
}

// Закрытие модального окна
document.getElementById("close-modal").addEventListener("click", function() {
    document.getElementById("modal").style.display = "none"; //Закрывает #modal
    fetch('/delete_folder', { // Отправляет POST-запрос на /delete_folder
        method: 'POST',
    }).then(response => response.json())
      .then(data => {
          console.log('Folder deleted successfully:', data);
      })
      .catch(error => {
          console.error('Error deleting folder:', error);
      });
    location.reload();
});

document.getElementById('folderInput').addEventListener('change', function(event) {
    let files = event.target.files; //Получает загруженные файлы
    let fileMap = { //Создает fileMap с нужными файлами
        "domain.yml": null, 
        "data/rules.yml": null, 
        "data/stories.yml": null 
    };

    let formData = new FormData();
    let folderName = "";

    for (let file of files) { // Проверяет, есть ли в загруженных файлах нужные .yml Добавляет их в FormData
        let pathParts = file.webkitRelativePath.split("/"); // Разбиваем путь по /
        if (!folderName) {
            folderName = pathParts[0]; // Берём первую часть как имя папки
            console.log(folderName)
            formData.append("folderName", folderName)
        }

        if (file.webkitRelativePath.includes("domain.yml")) {
            fileMap["domain.yml"] = file;
            formData.append("domain", file);
        } else if (file.webkitRelativePath.includes("data/rules.yml")) {
            fileMap["data/rules.yml"] = file;
            formData.append("rules", file);
        } else if (file.webkitRelativePath.includes("data/stories.yml")) {
            fileMap["data/stories.yml"] = file;
            formData.append("stories", file);
        } else if (file.webkitRelativePath.includes("data/nlu.yml")) {
            fileMap["data/nlu.yml"] = file;
            formData.append("nlu", file);
        }
    }

    let fileInfo = document.getElementById('fileInfo');

    if (fileMap["domain.yml"] && fileMap["data/rules.yml"] && fileMap["data/stories.yml"]) {
        fileInfo.innerText = "Файлы загружены!";
        fileInfo.style.color = "green";

        fetch('/upload', { //Отправляет файлы на /upload
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => console.log("Ответ от сервера:", data))
        .catch(error => console.error("Ошибка загрузки:", error));

    } else {
        fileInfo.innerText = "Не все файлы найдены!";
        fileInfo.style.color = "red";
    }

    checkContinueButton();
});

// Функция проверки кнопки "Продолжить"
function checkContinueButton() {
    let selectedCubes = document.querySelectorAll(".cube.selected").length > 0;
    let filesUploaded = document.getElementById("fileInfo").innerText === "Файлы загружены!";
    
    console.log("Выбраны кубы:", selectedCubes);
    console.log("Файлы загружены:", filesUploaded);

    let btn = document.getElementById("continueBtn");
    if (selectedCubes && filesUploaded) {
        btn.removeAttribute("disabled"); // Убираем disabled
        btn.onclick = submitSelection; // Назначаем обработчик клика
    } else {
        btn.setAttribute("disabled", "true"); // Ставим обратно, если условия не выполнены
        btn.onclick = null; // Убираем обработчик клика
    }
}
