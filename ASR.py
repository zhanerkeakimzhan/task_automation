import aiohttp
from aiohttp import ClientTimeout
import asyncio

async def transcribe_audio(tmp_audio_path, audio_filename, asr_url="http://10.1.0.5/asr", asr_request_timeout=120):
    print("transcribe_audio")
    # Устанавливаем таймаут
    timeout = ClientTimeout(total=asr_request_timeout)

    # Полный путь к аудиофайлу
    full_audio_path = f"{tmp_audio_path}/{audio_filename}"

    # Открываем сессию для отправки запроса
    async with aiohttp.ClientSession() as session:
        try:
            # Открываем аудиофайл для чтения
            with open(full_audio_path, 'rb') as audio_file:
                # Отправляем POST-запрос на сервер, передавая аудиофайл как часть данных
                async with session.post(asr_url, data={'audio': audio_file}, timeout=timeout) as result_asr:
                    # Проверяем статус ответа
                    if result_asr.status == 200:
                        transcription = await result_asr.text()
                        return transcription  # Возвращаем текст расшифровки
                    else:
                        print(f"Ошибка: {result_asr.status} - {await result_asr.text()}")
                        return None
        except Exception as e:
            print(f"Произошла ошибка: {e}")
            return None

# # Запускаем асинхронную функцию с передачей пути к аудиофайлу
# if __name__ == "__main__":
#     # Путь к директории, где находится аудиофайл
#     tmp_audio_path = 'C:/Users/Lenovo v15/Desktop/Hotelki_Aruzhan/TableFetcher/segments_audio'
    
#     # Название аудиофайла
#     audio_filename = '4_halyk_depozit_M_R.wav'
    
#     # Запускаем асинхронную функцию и выводим результат
#     transcription_text = asyncio.run(transcribe_audio(tmp_audio_path, audio_filename))
    
#     if transcription_text:
#         print("Transcription:", transcription_text)
