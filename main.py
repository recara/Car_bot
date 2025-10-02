#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import telebot
from telebot import types
import requests
import json
import xmltodict
import re
import os
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === КОНФИГУРАЦИЯ ===
TELEGRAM_TOKEN = "8258338909:AAFDh6F71h7izvOd7USnUtQgyPEUQR_rhKs"
YANDEX_FOLDER_ID = "b1ga94okgf6e5d8edu0u" 
YANDEX_API_KEY = "AQVN11NisODlVimxoBFrYhs2suVgJ-WzW54BuEEw"
XML_FILE_PATH = "farpost-export-atcNew.xml"  # ⬅️ ПУТЬ К ФАЙЛУ - положите XML рядом с bot.py

class SimpleSearchEngine:
    def __init__(self, xml_file_path):
        self.xml_file_path = xml_file_path
        self.products = []
        self.load_data()
        logger.info(f"✅ Загружено товаров: {len(self.products)}")
    
    def load_data(self):
        """Загружает XML файл"""
        try:
            with open(self.xml_file_path, 'r', encoding='utf-8') as file:
                xml_content = file.read()
            data = xmltodict.parse(xml_content)
            self.extract_products(data)
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки XML: {e}")
    
    def extract_products(self, data):
        """Извлекает товары из XML"""
        def extract_items(obj):
            if isinstance(obj, dict):
                product = {}
                # Ищем основные поля
                for key, value in obj.items():
                    key_lower = key.lower()
                    if any(term in key_lower for term in ['name', 'title', 'product']):
                        product['name'] = str(value)
                    elif any(term in key_lower for term in ['articul', 'article', 'code']):
                        product['article'] = str(value)
                    elif any(term in key_lower for term in ['brand', 'mark']):
                        product['brand'] = str(value)
                    elif any(term in key_lower for term in ['price', 'cost']):
                        price = self.extract_price(value)
                        if price:
                            product['price'] = price
                    elif any(term in key_lower for term in ['model', 'car']):
                        product['car_model'] = str(value)
                
                if product and len(product) >= 2:
                    self.products.append(product)
                
                for key, value in obj.items():
                    extract_items(value)
            
            elif isinstance(obj, list):
                for item in obj:
                    extract_items(item)
        
        extract_items(data)
    
    def extract_price(self, value):
        """Извлекает цену"""
        if not value:
            return None
        text = str(value)
        matches = re.findall(r'(\d{1,10})', text)
        for match in matches:
            if match.isdigit():
                price = int(match)
                if 10 <= price <= 1000000:
                    return price
        return None
    
    def search(self, query):
        """Простой поиск"""
        query_lower = query.lower()
        results = []
        
        for product in self.products:
            # Собираем весь текст для поиска
            search_text = ""
            if 'name' in product:
                search_text += product['name'].lower() + " "
            if 'brand' in product:
                search_text += product['brand'].lower() + " "
            if 'car_model' in product:
                search_text += product['car_model'].lower() + " "
            if 'article' in product:
                search_text += product['article'].lower() + " "
            
            # Простой поиск по вхождению
            if query_lower in search_text:
                results.append(product)
        
        return results[:8]  # Возвращаем первые 8 результатов

class SimpleAI:
    def __init__(self, folder_id, api_key):
        self.folder_id = folder_id
        self.api_key = api_key
        self.url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {api_key}",
            "x-folder-id": folder_id
        }
    
    def get_response(self, query, products):
        """Получает ответ от AI"""
        if not products:
            return "🔍 По вашему запросу ничего не найдено.\n\n💡 Попробуйте изменить формулировку."
        
        # Формируем данные для AI
        products_text = "Найденные товары:\n"
        for i, product in enumerate(products, 1):
            products_text += f"{i}. "
            if 'name' in product:
                products_text += f"{product['name']} "
            if 'article' in product:
                products_text += f"(арт: {product['article']}) "
            if 'price' in product:
                products_text += f"- {product['price']} руб"
            products_text += "\n"
        
        prompt = f"""Ты консультант по автозапчастям. Используй эти данные:

{products_text}

Запрос пользователя: {query}

Дай краткий полезный ответ:"""
        
        data = {
            "modelUri": f"gpt://{self.folder_id}/yandexgpt-lite/latest",
            "completionOptions": {
                "stream": False,
                "temperature": 0.3,
                "maxTokens": 1000
            },
            "messages": [{"role": "user", "text": prompt}]
        }
        
        try:
            response = requests.post(self.url, headers=self.headers, json=data, timeout=20)
            response.raise_for_status()
            result = response.json()
            return result['result']['alternatives'][0]['message']['text']
        except Exception as e:
            logger.error(f"AI ошибка: {e}")
            # Возвращаем простой ответ если AI недоступен
            return self.get_simple_response(products)
    
    def get_simple_response(self, products):
        """Простой ответ без AI"""
        response = "🎯 Найдены товары:\n\n"
        for i, product in enumerate(products, 1):
            response += f"{i}. "
            if 'name' in product:
                response += f"**{product['name']}** "
            if 'article' in product:
                response += f"(арт: {product['article']}) "
            if 'price' in product:
                response += f"- {product['price']} руб"
            response += "\n"
        return response

class SimpleBot:
    def __init__(self):
        logger.info("🚀 Запуск простого бота...")
        
        # Проверяем наличие XML файла
        if not os.path.exists(XML_FILE_PATH):
            logger.error(f"❌ XML файл не найден: {XML_FILE_PATH}")
            logger.info("💡 Положите XML файл в ту же папку что и bot.py")
            return
        
        self.bot = telebot.TeleBot(TELEGRAM_TOKEN)
        self.search_engine = SimpleSearchEngine(XML_FILE_PATH)
        self.ai = SimpleAI(YANDEX_FOLDER_ID, YANDEX_API_KEY)
        
        logger.info("✅ Бот готов к работе!")
        self.setup_handlers()
    
    def setup_handlers(self):
        @self.bot.message_handler(commands=['start'])
        def start(message):
            self.send_welcome(message)
        
        @self.bot.message_handler(func=lambda message: True)
        def handle_message(message):
            self.handle_search(message)
    
    def send_welcome(self, message):
        """Приветственное сообщение"""
        welcome_text = """
🤖 <b>AI-консультант автозапчастей</b>

Просто напишите что вам нужно:

• Название запчасти
• Марка автомобиля  
• Артикул детали
• Описание проблемы

💡 <b>Примеры:</b>
• Тормозные колодки
• Запчасти на Toyota
• Масляный фильтр
• ABC123456

🎯 <b>Я найду и проконсультирую!</b>
        """
        
        self.bot.send_message(
            message.chat.id, 
            welcome_text, 
            parse_mode='HTML'
        )
    
    def handle_search(self, message):
        """Обрабатывает поисковые запросы"""
        user_id = message.chat.id
        query = message.text
        
        logger.info(f"🔍 Поиск: {query}")
        
        # Показываем что бот "думает"
        self.bot.send_chat_action(user_id, 'typing')
        
        # Выполняем поиск
        results = self.search_engine.search(query)
        
        # Получаем ответ
        ai_response = self.ai.get_response(query, results)
        
        # Форматируем ответ
        if results:
            response = f"""
🔍 <b>По запросу:</b> <code>{query}</code>

{ai_response}

📊 <b>Найдено товаров:</b> {len(results)}
            """
        else:
            response = f"""
🔍 <b>По запросу:</b> <code>{query}</code>

{ai_response}

💡 <i>Попробуйте изменить запрос</i>
            """
        
        self.bot.send_message(
            user_id,
            response,
            parse_mode='HTML'
        )
    
    def start(self):
        """Запускает бота"""
        try:
            logger.info("📱 Бот запущен! Ищите в Telegram...")
            self.bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            logger.info("🔄 Перезапуск через 10 секунд...")
            import time
            time.sleep(10)
            self.start()

# 🚀 ЗАПУСК ПРОГРАММЫ
if __name__ == "__main__":
    bot = SimpleBot()
    bot.start()