## 📢 Telegram канал с новостями
Следи за обновлениями здесь:  
👉 https://t.me/kanalnieuslugi

# 🧠 Science News Agent (Telegram)

Автоматизированная система сбора, анализа и публикации новостей о науке и технологиях в Telegram-канал.

Система работает как полный data pipeline: от получения RSS-источников до LLM-обработки, фильтрации, переписывания текста и публикации.

---

## ⚙️ Что делает система

- собирает новости из RSS-источников (наука, технологии, AI, Big Tech, EV, энергетика)
- нормализует и очищает ссылки (удаление tracking-параметров)
- выполняет дедупликацию:
  - по URL (hash)
  - по смыслу (embeddings)
- предварительно фильтрует новости (pre-score)
- анализирует новости через LLM (OpenRouter):
  - оценивает важность (score)
  - определяет тему (topic)
- выбирает наиболее релевантные новости с балансировкой тем
- переписывает текст для Telegram с помощью LLM (Claude Haiku), делая его читаемым и адаптированным под новостной формат
- публикует результат в Telegram-канал
- ведёт лог всех запусков и обработанных данных

---

## 🧠 Архитектура (pipeline)

RSS → сбор → очистка URL → дедупликация → pre-score → LLM scoring → ranking → topic balancing → rewrite (Claude Haiku) → Telegram publish → logging

---

## 📁 Структура проекта

pycache/ # кеш Python (игнорируется)
.env # переменные окружения (не коммитится)
.gitignore # правила игнорирования файлов
news_agent.py # основной pipeline системы
test_news_agent.py # тестовый запуск / отладка
news_log.json # журнал запусков и обработанных новостей
posted_news.json # база уже опубликованных новостей (антидубликаты)

## 🧩 Ключевые механики

### Дедупликация
- удаление UTM и tracking параметров из URL
- защита от повторной публикации одинаковых новостей
- семантическое сравнение через embeddings

### LLM-анализ
- батч-обработка новостей через OpenRouter
- оценка важности (score)
- определение темы (topic)

### Балансировка ленты
- ограничение повторяющихся тем подряд
- поддержание разнообразия контента

### Переписывание текста
- используется LLM (Claude Haiku)
- адаптация новостей под формат Telegram
- упрощение и повышение читаемости текста

### Telegram публикация
- retry-механизм (до 2 попыток)
- timeout защита от зависаний (VPN/сеть)
- контроль статуса отправки (новость не считается опубликованной при ошибке)

### Логирование
- JSON-лог всех запусков (`news_log.json`)
- фиксация обработанных и опубликованных новостей

---

## 🛠 Технологии

Python 3.10+  
RSS (feedparser / requests)  
OpenRouter API (LLM scoring)  
Claude Haiku (text rewriting)  
sentence-transformers (embeddings)  
Telegram Bot API  
JSON logging  

---

## 🔐 Переменные окружения

TELEGRAM_TOKEN=your_token_here  
CHANNEL_ID=your_channel_id  
ADMIN_CHAT_ID=your_admin_chat_id  
OPENROUTER_KEY=your_openrouter_key 

---
## 📦 Зависимости (один раз при настройке)

pip install -r requirements.txt

## 🚀 Запуск

Скрипт запускается автоматически через Windows Task Scheduler.

При необходимости ручного запуска:

python news_agent.py

---

## Editorial Notes

See `EDITORIAL_GUIDELINES.md` for the rules around company context, when to use bullets, and when a short paragraph or mixed format is better for a news post.
