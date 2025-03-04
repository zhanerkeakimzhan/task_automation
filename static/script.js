// скролл между двумя страничками
let currentContainer = 1; // Отслеживаем, какой контейнер активен

// Функция для обновления точек-индикаторов
function updateDots() {
    document.querySelectorAll(".dot").forEach((dot, index) => {
        dot.classList.toggle("active", index + 1 === currentContainer);
    });
}

// Функция для переключения контейнеров при клике на точки
function scrollToContainer(containerNumber) {
    let firstContainer = document.getElementById("firstContainer");
    let secondContainer = document.getElementById("secondContainer");

    if (containerNumber === 1) {
        firstContainer.classList.remove("hidden");
        secondContainer.classList.remove("visible");
        currentContainer = 1;
    } else {
        firstContainer.classList.add("hidden");
        secondContainer.classList.add("visible");
        currentContainer = 2;
    }

    
    // Убираем выделение у всех .cube при прокрутке
    document.querySelectorAll(".cube.selected").forEach(cube => {
        cube.classList.remove("selected");
        csvInputContainer.style.display = "none";
        csvInput.value = "";
        preRecordingInputContainer.style.display = "none";
        preRecordingInput.value = "";
        preRecordingListName.value = "";
        document.querySelectorAll('.gender-button').forEach(btn => btn.classList.remove('selected'));
        projectFileContainer.style.display = "none";
        testListInputContainer.style.display = "none";
        testListInput.value = "";
    });

    // Обновляем точки-индикаторы
    updateDots();
}

// выборка кубиков
function toggleSelection(element) {
    element.classList.toggle("selected");
    // checkContinueButton();
}

// для выбора пол робота
document.querySelectorAll('.gender-button').forEach(button => {
    button.addEventListener('click', function () {
        // Сброс выделения у всех кнопок
        document.querySelectorAll('.gender-button').forEach(btn => btn.classList.remove('selected'));

        // Добавление выделения только на выбранную кнопку
        this.classList.add('selected');
        selectedGender = this.dataset.gender;
        localStorage.setItem("selectedGender", selectedGender);
    });
});


// нажимаешь на кубик и нужные инпуты появляется снизу
document.addEventListener("DOMContentLoaded", function () {
    let projectFileContainer = document.getElementById("projectFileContainer");

    function checkProjectFileVisibility() {
        let isAnySelected = document.querySelectorAll(".cube.selected").length > 0;
        projectFileContainer.style.display = isAnySelected ? "flex" : "none";
    }

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
        checkProjectFileVisibility();
    });

    let testListCube = document.getElementById("testList");
    let testListInputContainer = document.getElementById("testListInputContainer");
    let testListInput = document.getElementById("testListInput");

    testListCube.addEventListener("click", function () {
        if (testListCube.classList.contains("selected")) {
            testListInputContainer.style.display = "flex";
        } else {
            testListInputContainer.style.display = "none";
            testListInput.value = "";
        }
        checkProjectFileVisibility();
    });

    let preRecordingCube = document.getElementById("preRecording");
    let preRecordingInputContainer = document.getElementById("preRecordingInputContainer");
    let preRecordingInput = document.getElementById("preRecordingInput");
    let preRecordingListName = document.getElementById("preRecordingListName");

    preRecordingCube.addEventListener("click", function () {
        if (preRecordingCube.classList.contains("selected")) {
            preRecordingInputContainer.style.display = "flex";
        } else {
            preRecordingInputContainer.style.display = "none";
            preRecordingInput.value = "";
            preRecordingListName.value = "";
            document.querySelectorAll('.gender-button').forEach(btn => btn.classList.remove('selected'));
        }
        checkProjectFileVisibility();
    });

    
    let checkTedCube = document.getElementById("checkTed");
    checkTedCube.addEventListener("click", function () {
        checkProjectFileVisibility();
    });

    checkProjectFileVisibility();
});


// после кнопки продолжить срабатывает, опеределяет на какую функцию дальше отправить
function submitSelection() {
    let selectedCubes = document.querySelectorAll(".cube.selected");
    let selectedIds = Array.from(selectedCubes).map(cube => cube.id);
    let csvInput = document.getElementById('csvInput').value.trim();
    let testListInput = document.getElementById('testListInput').value.trim();

    console.log(csvInput);
    console.log(testListInput);

    // Проверяем, выбрал ли пользователь "testList"
    if (selectedIds.includes("testList")) {
        checkExistsList(selectedIds, csvInput, testListInput)
    } else {
        // Если "testList" не выбран, просто продолжаем отправку
        continueSubmit(selectedIds, csvInput, testListInput);
    }
}

// проверка для test-list, существует лист с таким названием
function checkExistsList(selectedIds, csvInput, testListInput){
    localStorage.setItem("selectedIds", JSON.stringify(selectedIds));
    localStorage.setItem("csvInput", csvInput);
    localStorage.setItem("testListInput", testListInput);

    fetch(`/check_list_exists?name=${encodeURIComponent(testListInput)}`)
            .then(response => response.json())
            .then(data => {
                console.log(data)
                console.log("EXISTS")
                if (data.exists) {
                    showTestListModal()
                } else {
                    continueSubmit(selectedIds, csvInput, testListInput);
                }
            })
            .catch(error => console.error("Ошибка при проверке списка:", error));
}

// отправка данных после проверки testList /submit
function continueSubmit(selectedIds, csvInput, testListInput){
    let data = { selected: selectedIds };
    let preRecordingInput = document.getElementById('preRecordingInput').value.trim();
    let preRecordingListName = document.getElementById('preRecordingListName').value.trim();
    selectedGender = localStorage.getItem("selectedGender");


    if (selectedIds.includes("csv") && csvInput) {
        data.csvInput = csvInput;
    } else if (selectedIds.includes("testList") && testListInput) {
        data.testListInput = testListInput;
    } else if (selectedIds.includes("preRecording") && preRecordingInput && preRecordingListName && selectedGender) {
        data.preRecordingInput = preRecordingInput;
        data.preRecordingListName = preRecordingListName;
        data.selectedGender = selectedGender;
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
                    title.innerText = "Создание таблицы для тестирование:";
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

// модальное окно для ответов с сервера "создалось, т.д"
function showModal() {
    let modal = document.getElementById("modal");
    modal.style.display = "block"; //Показывает #modal, устанавливая display: block
}

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

// для название листа test-list, если есть перезаписать или новое название
function showTestListModal() {
    let modal = document.getElementById("modal-test-list");
    modal.style.display = "block"; // Показываем модальное окно

    let modalContent = document.getElementById("modal-content-test-list");
    modalContent.innerHTML = `
        <p>Такой лист уже существует. Что сделать?</p>
        <button id="overwriteListBtn" onclick="overwriteList()">Перезаписать</button>
        <input type="text" id="newTestListName" placeholder="Введите название">
        <button id="submitNewNameBtn" onclick="submitNewName()">Отправить новое название</button>
    `;
}

function overwriteList() {
    let modal = document.getElementById("modal-test-list");
    let selectedIds = JSON.parse(localStorage.getItem("selectedIds"));
    let csvInput = localStorage.getItem("csvInput");
    let testListInput = localStorage.getItem("testListInput");

    closeModal();
    continueSubmit(selectedIds, csvInput, testListInput);
}

function submitNewName() {
    let selectedIds = JSON.parse(localStorage.getItem("selectedIds"));
    let csvInput = localStorage.getItem("csvInput");
    let newTestListName = document.getElementById('newTestListName').value.trim();
    localStorage.setItem("testListInput", newTestListName);
    
    closeModal();

    console.log(newTestListName)
    checkExistsList(selectedIds, csvInput, newTestListName)
}

function closeModal() {
    let modal = document.getElementById("modal-test-list");
    modal.style.display = "none";
}

document.getElementById("close-modal-test-list").addEventListener("click", function() {
    document.getElementById("modal-test-list").style.display = "none"; //Закрывает #modal
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


// если нужно вручную ввести данные для test-list
function showActionsModal() {
    let modal = document.getElementById("modal-actions");
    modal.style.display = "block"; // Показываем модальное окно

    let modalContent = document.getElementById("modal-content-actions");
    modalContent.innerHTML = `
        <p>Есть рулс который уходить на экшны</p>
        <button id="skipBtn" onclick="overwriteList()">Пропустить</button>
        <button id="manuallyBtn" onclick="enterManually()">Ввести вопросы вручную</button>
    `;
}

function enterManually() {
    let selectedIds = JSON.parse(localStorage.getItem("selectedIds"));
    let csvInput = localStorage.getItem("csvInput");
    let newTestListName = document.getElementById('newTestListName').value.trim();
    localStorage.setItem("testListInput", newTestListName);
    
    console.log(newTestListName)
    checkExistsList(selectedIds, csvInput, newTestListName)
}


// загрузка файла
document.getElementById('folderInput').addEventListener('change', function(event) {
    let files = event.target.files; //Получает загруженные файлы
    let fileMap = { //Создает fileMap с нужными файлами
        "domain.yml": null, 
        "data/rules.yml": null, 
        "data/stories.yml": null,
        "data/nlu.yml": null,
        "actions/actions.py": null
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
        } else if (file.webkitRelativePath.includes("actions/actions.py")) {
            fileMap["actions/actions.py"] = file;
            formData.append("actions", file);
        }
    }

    let fileInfo = document.getElementById('fileInfo');

    if (fileMap["domain.yml"] && fileMap["data/rules.yml"] && fileMap["data/stories.yml"] && fileMap["data/nlu.yml"] && fileMap["actions/actions.py"]) {
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
