import webrtcvad
import wave
import os
import numpy as np

def create_silence(duration_ms, sample_rate, sample_width=2):
    """Создает тишину заданной длительности."""
    num_samples = int(sample_rate * duration_ms / 1000)
    return b'\x00' * num_samples * sample_width  # Пустые байты для тишины

def vad_segments_in_memory(audio_data, sample_rate, output_dir, frame_duration=20, silence_duration=5000):
    """Разделяет аудио на сегменты на основе VAD и сохраняет их в отдельные файлы."""
    vad = webrtcvad.Vad(2)  # Уровень агрессивности VAD (0-3)
    
    audio_bytes = (audio_data * (2**15 - 1)).astype(np.int16).tobytes()  # Преобразуем данные в байты для VAD

    frame_size = int(sample_rate * frame_duration / 1000 * 2)  # Размер кадра в байтах
    silence_threshold = int(silence_duration / frame_duration)  # Количество кадров тишины для паузы

    segments = []  # Список для сегментов речи
    current_segment = []  # Текущий сегмент
    silence_counter = 0  # Счётчик тишины

    # Проход по аудиофайлу с шагом в 20 миллисекунд
    for i in range(0, len(audio_bytes), frame_size):
        frame = audio_bytes[i:i + frame_size]

        # Если кадр неполный, пропускаем его
        if len(frame) < frame_size:
            continue

        # Проверяем, есть ли в кадре речь
        is_speech = vad.is_speech(frame, sample_rate)

        if is_speech:
            # Если есть речь, добавляем кадр к текущему сегменту и сбрасываем счётчик тишины
            current_segment.append(frame)
            silence_counter = 0
        else:
            # Если нет речи, увеличиваем счётчик тишины
            silence_counter += 1

            # Если накопили паузу больше, чем silence_duration, сохраняем текущий сегмент
            if silence_counter >= silence_threshold and current_segment:
                segments.append(current_segment)
                current_segment = []  # Очищаем для нового сегмента

    # Если последний сегмент не сохранён, сохраняем его
    if current_segment:
        segments.append(current_segment)

    # Добавление тишины и сохранение сегментов в отдельные файлы
    silence_start = create_silence(100, sample_rate)  # 0.1 сек тишины в начале
    silence_end = create_silence(200, sample_rate)    # 0.2 сек тишины в конце

    # Счётчик для названий файлов
    file_counter = 1

    for segment in segments:
        output_path = os.path.join(output_dir, f"{file_counter}.wav")  # Используем счётчик для имени файла
        with wave.open(output_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)

            wf.writeframes(silence_start + b''.join(segment) + silence_end)

        print(f"Сохранён сегмент: {output_path}")
        file_counter += 1  # Увеличиваем счётчик для следующего сегмента
