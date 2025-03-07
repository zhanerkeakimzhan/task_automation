// скролл между двумя страничками
let currentContainer = 1; // Отслеживаем, какой контейнер активен

document.addEventListener("wheel", function (event) {
    let firstContainer = document.getElementById("firstContainer");
    let secondContainer = document.getElementById("secondContainer");

    // Проверяем направление скролла
    if (event.deltaY > 0) { 
        // Скроллим вниз → показываем второй контейнер
        firstContainer.classList.add("hidden");
        secondContainer.classList.add("visible");
        currentContainer = 2;
    } else { 
        // Скроллим вверх → показываем первый контейнер
        firstContainer.classList.remove("hidden");
        secondContainer.classList.remove("visible");
        currentContainer = 1;
    }
    
    // Блокируем скролл всей страницы
    event.preventDefault();
     
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
}, { passive: false }); // Важно: предотвращаем стандартное поведение

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

document.querySelectorAll("#secondContainer .cube").forEach(cube => {
    cube.addEventListener("click", function () {
        // Убираем выделение со всех кубов в контейнере
        document.querySelectorAll("#secondContainer .cube").forEach(c => c.classList.remove("selected"));
        
        // Добавляем выделение только выбранному кубу
        this.classList.add("selected");
    });
});


document.addEventListener("DOMContentLoaded", function () {
    const modal = document.getElementById("modal");
    const modalContent = document.getElementById("modal-content");
    const openModalBtn = document.createElement("button");
    openModalBtn.textContent = "Продолжить";
    openModalBtn.id = "openModalBtn";
    document.body.appendChild(openModalBtn);
    
    openModalBtn.addEventListener("click", function () {
        modalContent.innerHTML = ""; // Очистка содержимого
        
        const selectedCubes = document.querySelectorAll(".cube.selected");
        
        if (selectedCubes.length === 0) {
            modalContent.innerHTML = "<p>Выберите хотя бы один вариант!</p>";
        } else {
            modalContent.innerHTML = "<h2>Теперь нужно заполнить некоторые данные!🤓🥹</h2>";
            modalContent.innerHTML += `<div class="input-container">
                                            <h4>Выберите папку с проектом:</h4>
                                            <label for="folderInput" class="custom-file-button">Выбрать папку</label>
                                            <span id="folderName">Файлы не выбраны!</span>
                                            <input type="file" id="folderInput" webkitdirectory directory multiple>
                                        </div>`;
            
            console.log(document.getElementById("folderInput")?.hasAttribute("webkitdirectory"));

            // загрузка файла
            document.addEventListener("change", function (event) {
                if (event.target && event.target.id === "folderInput") {
                    let files = event.target.files; // Получает загруженные файлы
                    console.log("Файлы загружены:", files);

                    let checkFiles = document.getElementById("folderName");

                    if (files.length > 0) {
                        // checkFiles.textContent = `Выбрано файлов: ${files.length}`;
                        checkFiles.textContent = `Файлы загружены!`;
                    } else {
                        checkFiles.textContent = "Файлы не выбраны!";
                    }
            
                    let fileMap = {
                        "domain.yml": null, 
                        "data/rules.yml": null, 
                        "data/stories.yml": null,
                        "data/nlu.yml": null,
                        "actions/actions.py": null
                    };
            
                    let formData = new FormData();
                    let folderName = "";
            
                    for (let file of files) { 
                        let pathParts = file.webkitRelativePath.split("/"); 
                        if (!folderName) {
                            folderName = pathParts[0]; 
                            formData.append("folderName", folderName);
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
            
                        fetch('/upload', { 
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
                }
                checkContinueButton();
            });
            
            selectedCubes.forEach(cube => {
                if (cube.id === "csv") {
                    modalContent.innerHTML += `<div class="input-container"><h4>Введите название листа предзаписи для создание CSV:</h4><input type='text' id='modalCsvInput' placeholder="для вытаскивание название аудио из этого листа"></div>`;
                } else if (cube.id === "testList") {
                    modalContent.innerHTML += `<div class="input-container"><h4>Введите название для листа тестирование:</h4><input type='text' id='modalTestListInput' placeholder="что-бы создать лист с таким названием"></div>`;
                } else if (cube.id === "preRecording") {
                    modalContent.innerHTML += `<div>
                        <div class="gender-container">
                            <h4>Выберите пол робота:</h4>
                            <button class='gender-button' data-gender='M'>Муж</button>
                            <button class='gender-button' data-gender='F'>Жен</button>
                        </div>
                                
                        <div class="input-container">
                            <h4>Введите название для аудио:</h4>
                            <input type='text' id='modalPreRecordingInput' placeholder="для заполнение поле название аудио">
                        </div>

                        <div class="input-container">
                            <h4>Введите название для листа предзаписи:</h4>
                            <input type='text' id='modalPreRecordingListName' placeholder="что-бы создать лист с таким названием">
                        </div>

                    </div>`;
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
                }
            });
            
            // Вешаем один обработчик событий на весь `document`
            document.addEventListener("click", function (event) {
                if (event.target.classList.contains("gender-button")) {
                    // Сброс выделения у всех кнопок
                    document.querySelectorAll('.gender-button').forEach(btn => btn.classList.remove('selected'));

                    // Добавление выделения только на выбранную кнопку
                    event.target.classList.add('selected');

                    // Сохранение выбора в локальное хранилище
                    let selectedGender = event.target.dataset.gender;
                    localStorage.setItem("selectedGender", selectedGender);
                    console.log("Выбранный пол:", selectedGender);
                }
            });

            // modalContent.innerHTML += `<button id='continueBtn' disabled>Создать</button>`;

            if (document.getElementById("firstContainer").querySelector(".selected")) {
                modalContent.innerHTML += `<button id='continueBtn1' disabled>Создать</button>`;
            } else if (document.getElementById("secondContainer").querySelector(".selected")) {
                modalContent.innerHTML += `<button id='continueBtn2' disabled>Создать</button>`;
            }
        }
        modal.style.display = "flex";
        modal.style.alignItems = "center";
        modal.style.justifyContent = "center";

        const scroll = document.getElementById("scroll-containers");
        scroll.style.overflow = "hidden"; // Блокируем фон
    });
    
    document.getElementById("close-modal").addEventListener("click", function () {
        modal.style.display = "none";
        const scroll = document.getElementById("scroll-containers");
        scroll.style.overflow = "hidden"; // Блокируем фон
    });
    
    window.addEventListener("click", function (event) {
        if (event.target === modal) {
            modal.style.display = "none";
        }
    });
});


// после кнопки продолжить срабатывает, опеределяет на какую функцию дальше отправить
function submitSelection() {
    let selectedCubes = document.querySelectorAll(".cube.selected");
    let selectedIds = Array.from(selectedCubes).map(cube => cube.id);

    
    let csvInputElem = document.getElementById('modalCsvInput');
    let csvInput = csvInputElem ? csvInputElem.value.trim() : "";

    
    let testListInputElem = document.getElementById('modalTestListInput');
    let testListInput = testListInputElem ? testListInputElem.value.trim() : "";
    

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

    let modalContent = document.getElementById("modal-content");
    modalContent.innerHTML = `<div class="loading-container">
    <div class="spinner"></div>
    <p>Загрузка данных...</p>
    </div>`;

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
    // Добавляем спиннер загрузки перед обработкой данных
    let data = { selected: selectedIds };
    // let preRecordingInput = document.getElementById('preRecordingInput').value.trim();
    // let preRecordingListName = document.getElementById('preRecordingListName').value.trim();
    // selectedGender = localStorage.getItem("selectedGender");


    // Проверяем, появились ли элементы в DOM
    let preRecordingInputElem = document.getElementById('modalPreRecordingInput');
    let preRecordingListNameElem = document.getElementById('modalPreRecordingListName');

    console.log(preRecordingInputElem)
    console.log(preRecordingListNameElem)

    let preRecordingInput = preRecordingInputElem ? preRecordingInputElem.value.trim() : "";
    let preRecordingListName = preRecordingListNameElem ? preRecordingListNameElem.value.trim() : "";
    let selectedGender = localStorage.getItem("selectedGender"); // Получаем из localStorage

    console.log(preRecordingInput)
    console.log(preRecordingListName)
    console.log(selectedGender)


    if (selectedIds.includes("csv") && csvInput) {
        data.csvInput = csvInput;
    } else if (selectedIds.includes("testList") && testListInput) {
        data.testListInput = testListInput;
    } else if (selectedIds.includes("preRecording") && preRecordingInput && preRecordingListName && selectedGender) {
        data.preRecordingInput = preRecordingInput;
        data.preRecordingListName = preRecordingListName;
        data.selectedGender = selectedGender;
    }

    console.log(data)

    let modalContent = document.getElementById("modal-content");
    modalContent.innerHTML = `<div class="loading-container">
    <div class="spinner"></div>
    <p>Загрузка данных...</p>
    </div>`;
    
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
                    title.innerText = "Создание таблицы тестирование:";
                    section.appendChild(title);
                } else if (key == "csv"){
                    title.innerText = "Создание CSV:";
                    section.appendChild(title);
                } else if (key == "audioProcessing"){
                    title.innerText = "Обработка аудио:";
                    section.appendChild(title);
                } else if (key == "preRecording"){
                    title.innerText = "Создание таблицы предзаписи:";
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
            // if (selectedIds.includes("csv")) {
            //     let csvDownload = document.createElement("a");
            //     csvDownload.href = "/download_csv";
            //     document.body.appendChild(csvDownload);
            //     csvDownload.click();
            //     document.body.removeChild(csvDownload);
            
            //     // Добавляем задержку перед скачиванием Excel
            //     setTimeout(() => {
            //         let excelDownload = document.createElement("a");
            //         excelDownload.href = "/download_excel";
            //         document.body.appendChild(excelDownload);
            //         excelDownload.click();
            //         document.body.removeChild(excelDownload);
            //     }, 1000); // 500 мс задержка (можно увеличить, если не срабатывает)
            // }
            
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
        <h2>Такой лист уже существует. Что делать?</h2>
        <div class="button-wrapper">
            <button id="overwriteListBtn" onclick="overwriteList()">Перезаписать</button>
        </div>

        <div class="input-wrapper">
            <input type="text" id="newTestListName" placeholder="Введите название">
            <button id="submitNewNameBtn" onclick="submitNewName()">Отправить</button>
        </div>
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



// Функция проверки кнопки "Продолжить"
function checkContinueButton() {
    let selectedCubes = document.querySelectorAll(".cube.selected").length > 0;
    let filesUploaded = document.getElementById("fileInfo").innerText === "Файлы загружены!";
    
    console.log("Выбраны кубы:", selectedCubes);
    console.log("Файлы загружены:", filesUploaded);

    let btn1 = document.getElementById("continueBtn1");
    let btn2 = document.getElementById("continueBtn2");
    if (selectedCubes && filesUploaded) {
        if (btn1) {
            btn1.removeAttribute("disabled");
            btn1.onclick = function () {
                console.log("Кнопка из firstContainer нажата!");
                // Здесь вызываем нужную функцию, например:
                submitSelection();
            };
        }
        
        if (btn2) {
            btn2.removeAttribute("disabled");
            btn2.onclick = function () {
                console.log("Кнопка из secondContainer нажата!");
                // Здесь вызываем другую функцию:
                submitSelection();
            };
        }
        // btn.removeAttribute("disabled"); // Убираем disabled
        // btn.onclick = submitSelection; // Назначаем обработчик клика
    } else {
        btn1.setAttribute("disabled", "true"); // Ставим обратно, если условия не выполнены
        btn2.setAttribute("disabled", "true"); // Ставим обратно, если условия не выполнены
        btn1.onclick = null; // Убираем обработчик клика
        btn2.onclick = null; // Убираем обработчик клика
    }
}
