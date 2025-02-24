function toggleSelection(element) {
    element.classList.toggle("selected");
    // checkContinueButton();
}

function submitSelection() {
    let selectedCubes = document.querySelectorAll(".cube.selected");
    let selectedIds = Array.from(selectedCubes).map(cube => cube.id);

    if (selectedIds.length > 0) {
        fetch('/submit', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ selected: selectedIds })
        })
        .then(response => response.json())
        .then(data => {
            let modalContent = document.getElementById("modal-content");
            modalContent.innerHTML = ""; // Очищаем старые данные

            Object.values(data.responses).forEach(text => {
                let p = document.createElement("p");
                p.innerHTML = text; // используем innerHTML, чтобы вставить ссылку
                modalContent.appendChild(p);
            });

            // Если выбран CSV, показываем кнопку скачивания
            if (selectedIds.includes("csv")) {
                let downloadBtn = document.createElement("a");
                downloadBtn.href = "/download_csv";
                downloadBtn.download = "data.xlsx";
                downloadBtn.innerText = "Скачать файл";
                downloadBtn.style.display = "block";
                downloadBtn.style.marginTop = "10px";
                downloadBtn.style.padding = "5px 10px";
                downloadBtn.style.backgroundColor = "#007bff";
                downloadBtn.style.color = "white";
                downloadBtn.style.textDecoration = "none";
                downloadBtn.style.borderRadius = "5px";
                modalContent.appendChild(downloadBtn);
                
                // Автоматическое скачивание
                downloadBtn.click();
            }

            showModal(); // Функция для отображения модального окна
        });
    } else {
        alert("Выберите хотя бы один вариант!");
    }
}

// Функция для отображения модального окна
function showModal() {
    let modal = document.getElementById("modal");
    modal.style.display = "block";
}

// Закрытие модального окна
document.getElementById("close-modal").addEventListener("click", function() {
    document.getElementById("modal").style.display = "none";
    location.reload();
});

document.getElementById('folderInput').addEventListener('change', function(event) {
    let files = event.target.files;
    let fileMap = { 
        "domain.yml": null, 
        "data/rules.yml": null, 
        "data/stories.yml": null 
    };

    let formData = new FormData();
    
    for (let file of files) {
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

        // Отправляем файлы на сервер Flask
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
