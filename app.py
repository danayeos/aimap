import os
import io
import base64
import markdown
import pandas as pd
from flask import Flask, render_template, request
from flask_session import Session
from markupsafe import Markup
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime
from playwright.sync_api import sync_playwright

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecretkey123")
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = "./flask_session_cache"
Session(app)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

REPORT_PROMPT = """Ты профессиональный аналитик данных. Составь подробный аналитический отчёт на русском языке.

## 📊 КРАТКОЕ РЕЗЮМЕ
(О чём эти данные — 2-3 предложения)

## 🔍 ОСНОВНЫЕ ПОКАЗАТЕЛИ
(Количество, суммы, средние значения, ключевые числа)

## 📈 ГРУППЫ И КАТЕГОРИИ
(Количество групп, темы, языки, категории)

## 📋 ОСНОВНЫЕ ВЫВОДЫ
(Что интересного видно в данных — минимум 3 вывода)

## ⚠️ ПРОБЛЕМНЫЕ ОБЛАСТИ
(Что требует внимания, аномалии, выбросы)

## 💡 РЕКОМЕНДАЦИИ
(Конкретные действия на основе данных — минимум 3 рекомендации)

## 📅 СЛЕДУЮЩИЕ ШАГИ
(Что нужно сделать в первую очередь)

Будь конкретным, используй цифры из данных. Отчёт для руководителя."""


def take_screenshot(url: str) -> bytes:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(url, timeout=60000)
        page.wait_for_timeout(6000)
        screenshot = page.screenshot(full_page=False)
        browser.close()
    return screenshot


def generate_report_from_screenshot(screenshot_bytes: bytes) -> str:
    client = OpenAI(api_key=OPENAI_API_KEY)
    b64 = base64.b64encode(screenshot_bytes).decode()

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text", "text": "Внимательно изучи скриншот отчёта Power BI и " + REPORT_PROMPT}
            ]
        }],
        max_tokens=2000
    )
    return response.choices[0].message.content


def generate_report_from_data(data_text: str) -> str:
    client = OpenAI(api_key=OPENAI_API_KEY)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": f"Проанализируй следующие данные из файла:\n\n{data_text}\n\n{REPORT_PROMPT}"
        }],
        max_tokens=2000
    )
    return response.choices[0].message.content


def parse_file(file) -> str:
    filename = file.filename.lower()
    if filename.endswith(".csv"):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)

    text = f"Файл: {file.filename}\n"
    text += f"Строк: {len(df)}, Столбцов: {len(df.columns)}\n"
    text += f"Столбцы: {', '.join(df.columns.tolist())}\n\n"

    text += "Первые 100 строк:\n"
    text += df.head(100).to_string(index=False)

    text += "\n\nСтатистика:\n"
    text += df.describe(include='all').to_string()

    return text


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    url = request.form.get("powerbi_url", "").strip()

    if not url:
        return render_template("index.html", error="Введите ссылку на Power BI отчёт!")

    if "powerbi.com" not in url:
        return render_template("index.html", error="Принимаются только ссылки app.powerbi.com")

    try:
        screenshot_bytes = take_screenshot(url)
        report_text = generate_report_from_screenshot(screenshot_bytes)
        report_html = Markup(markdown.markdown(report_text))
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode()
        generated_at = datetime.now().strftime("%d.%m.%Y %H:%M")

        return render_template("report.html",
                               report=report_html,
                               screenshot=screenshot_b64,
                               source="Публичная ссылка Power BI",
                               generated_at=generated_at)
    except Exception as e:
        return render_template("index.html", error=f"Ошибка: {str(e)}")


@app.route("/analyze-file", methods=["POST"])
def analyze_file():
    file = request.files.get("datafile")

    if not file or file.filename == "":
        return render_template("index.html", error="Выберите файл!")

    allowed = (".xlsx", ".xls", ".csv")
    if not file.filename.lower().endswith(allowed):
        return render_template("index.html", error="Поддерживаются только .xlsx, .xls, .csv файлы")

    try:
        data_text = parse_file(file)
        report_text = generate_report_from_data(data_text)
        report_html = Markup(markdown.markdown(report_text))
        generated_at = datetime.now().strftime("%d.%m.%Y %H:%M")

        return render_template("report.html",
                               report=report_html,
                               screenshot=None,
                               source=f"Файл: {file.filename}",
                               generated_at=generated_at)
    except Exception as e:
        return render_template("index.html", error=f"Ошибка: {str(e)}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
