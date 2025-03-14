import noisereduce as nr
from scipy.io import wavfile
import numpy as np
import os
from pydub import AudioSegment

def reduce_noise_in_audio(input_filepath, output_dir, prop_decrease=0.4):
    """
    Функция для удаления шума и нормализации аудиофайла с использованием pydub.
    
    :param input_filepath: Путь к исходному аудиофайлу.
    :param output_dir: Директория для сохранения обработанного файла.
    :param prop_decrease: Параметр уменьшения шума (чем меньше, тем мягче подавление).
    :return: Путь к файлу с уменьшенным шумом и нормализованным аудио.
    """
    # Чтение аудиофайла
    rate, data = wavfile.read(input_filepath)
    
    # Применение подавления шума
    reduced_noise = nr.reduce_noise(y=data, sr=rate, prop_decrease=prop_decrease)
    
    # Сохранение временного файла для обработки в pydub
    temp_output_filepath = os.path.join(output_dir, "temp_processed.wav")
    wavfile.write(temp_output_filepath, rate, reduced_noise.astype(np.int16))
    
    # Нормализация аудио с использованием pydub
    audio = AudioSegment.from_wav(temp_output_filepath)
    normalized_audio = audio.normalize()
    
    # Сохранение нормализованного аудио
    final_output_filepath = os.path.join(output_dir, f"processed_{os.path.basename(input_filepath)}")
    normalized_audio.export(final_output_filepath, format="wav")
    
    # Удаление временного файла
    os.remove(temp_output_filepath)
    
    return final_output_filepath