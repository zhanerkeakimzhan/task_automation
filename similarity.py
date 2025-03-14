import re
import pymorphy2
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import asyncio



# Инициализация лемматизатора
morph = pymorphy2.MorphAnalyzer()

def lemmatize_text(text):
    print("lemmatize_text")
    words = text.split()
    lemmatized_words = [morph.parse(word)[0].normal_form for word in words]
    return ' '.join(lemmatized_words)

def clean_and_lemmatize_text(text):
    print("clean_and_lemmatize_text")
    # Преобразуем текст в нижний регистр
    text = text.lower()
    # Убираем все знаки препинания, оставляем только буквы и пробелы
    text = re.sub(r'[^\w\s]', '', text)
    # Лемматизируем текст
    text = lemmatize_text(text)
    return text

def compare_texts_cosine(text1, text2):
    # Векторизация текста с использованием биграмм (2-грамм)
    vectorizer = TfidfVectorizer(ngram_range=(1, 2)).fit_transform([text1, text2])
    # Вычисление косинусного сходства
    similarity_matrix = cosine_similarity(vectorizer)
    return round(similarity_matrix[0][1] * 100, 2)


