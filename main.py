import os
import requests
from google import genai
import msal
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
TENANT_ID = os.getenv("TENANT_ID")
DATASET_ID = os.getenv("DATASET_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TABLE_NAME = os.getenv("TABLE_NAME")

SCOPES = ["https://analysis.windows.net/powerbi/api/Dataset.Read.All",
          "https://analysis.windows.net/powerbi/api/Report.Read.All"]


def get_token():
    """Логин через браузер — не нужен админ, не нужен redirect URI"""
    app = msal.PublicClientApplication(
        client_id=CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}"
    )

    # Сначала пробуем кэш
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            print("✅ Токен получен из кэша")
            return result["access_token"]

    # Device code flow — самый простой способ без redirect URI
    flow = app.initiate_device_flow(scopes=SCOPES)
    print("\n" + "="*50)
    print("🔐 АВТОРИЗАЦИЯ НУЖНА")
    print("="*50)
    print(flow["message"])
    print("="*50 + "\n")

    result = app.acquire_token_by_device_flow(flow)

    if "access_token" in result:
        print("✅ Авторизация успешна!")
        return result["access_token"]
    else:
        raise Exception(f"Ошибка авторизации: {result.get('error_description')}")


def get_powerbi_data(token):
    """Получаем данные из Power BI датасета"""
    url = f"https://api.powerbi.com/v1.0/myorg/datasets/{DATASET_ID}/executeQueries"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    first_table = TABLE_NAME
    tables = [first_table]
    print(f"\n🔍 Запрашиваем данные из таблицы: '{first_table}'")

    body = {
        "queries": [{"query": f"EVALUATE TOPN(100, '{first_table}')"}],
        "serializerSettings": {"includeNulls": True}
    }

    response = requests.post(url, headers=headers, json=body)

    if response.status_code != 200:
        raise Exception(f"Ошибка запроса данных: {response.text}")

    rows = response.json()["results"][0]["tables"][0].get("rows", [])
    print(f"✅ Получено строк: {len(rows)}")

    return rows, first_table, tables


def format_data_for_ai(rows, table_name, all_tables):
    """Форматируем данные в текст для Claude"""
    if not rows:
        return "Данных нет"

    # Получаем колонки из первой строки
    columns = list(rows[0].keys())

    text = f"ДАННЫЕ ИЗ POWER BI\n"
    text += f"Дата отчёта: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
    text += f"Датасет ID: {DATASET_ID}\n"
    text += f"Таблиц в датасете: {len(all_tables)}\n"
    text += f"Анализируемая таблица: {table_name}\n"
    text += f"Количество записей: {len(rows)}\n\n"

    text += f"КОЛОНКИ: {', '.join(columns)}\n\n"
    text += "ДАННЫЕ (первые 50 строк):\n"

    for i, row in enumerate(rows[:50]):
        row_text = " | ".join([f"{k.split('[')[-1].rstrip(']')}: {v}" for k, v in row.items()])
        text += f"{i+1}. {row_text}\n"

    return text


def generate_report(data_text):
    """Генерируем аналитический отчёт через Gemini"""
    client = genai.Client(api_key=GEMINI_API_KEY)

    print("\n🤖 Генерируем отчёт через Gemini AI...")

    prompt = f"""Ты профессиональный аналитик данных. Проанализируй данные из Power BI и составь подробный аналитический отчёт на русском языке.

{data_text}

Составь отчёт со следующими разделами:

## 📊 КРАТКОЕ РЕЗЮМЕ
(2-3 предложения о том что представляют эти данные)

## 🔍 ОСНОВНЫЕ ПОКАЗАТЕЛИ
(ключевые числа, метрики, статистика)

## 📈 ОСНОВНЫЕ ВЫВОДЫ
(что интересного/важного видно в данных, минимум 3 вывода)

## ⚠️ ПРОБЛЕМНЫЕ ОБЛАСТИ
(что требует внимания, аномалии, выбросы)

## 💡 РЕКОМЕНДАЦИИ
(конкретные действия на основе данных, минимум 3 рекомендации)

## 📅 СЛЕДУЮЩИЕ ШАГИ
(что нужно сделать в первую очередь)

Будь конкретным, используй цифры из данных. Отчёт должен быть полезным для руководителя."""

    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=prompt
    )
    return response.text


def save_report(report_text):
    """Сохраняем отчёт в файл"""
    filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(report_text)
    return filename


def main():
    print("🚀 Power BI → AI Аналитический Отчёт")
    print("="*50)

    # 1. Авторизация
    print("\n📡 Шаг 1: Авторизация в Microsoft...")
    token = get_token()

    # 2. Получение данных
    print("\n📊 Шаг 2: Получение данных из Power BI...")
    rows, table_name, all_tables = get_powerbi_data(token)

    # 3. Форматирование
    print("\n📝 Шаг 3: Подготовка данных...")
    data_text = format_data_for_ai(rows, table_name, all_tables)

    # 4. Генерация отчёта
    report = generate_report(data_text)

    # 5. Сохранение
    filename = save_report(report)

    print("\n" + "="*50)
    print("✅ ОТЧЁТ ГОТОВ!")
    print("="*50)
    print(report)
    print(f"\n💾 Отчёт сохранён в файл: {filename}")


if __name__ == "__main__":
    main()
