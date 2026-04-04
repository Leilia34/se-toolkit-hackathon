# Expense Tracker

## One-line description
Веб-приложение для учёта личных доходов и расходов с отображением баланса.

## Demo
![Screenshot](screenshot.png)  <!-- потом добавите скриншот -->

## Product context
- **End users**: Люди, которые хотят контролировать свои финансы.
- **Problem**: Сложно отслеживать, куда уходят деньги, и быстро узнать текущий баланс.
- **Your solution**: Простой веб-интерфейс для добавления транзакций (доход/расход) и автоматического подсчёта баланса.

## Features
### Implemented
- [x] Добавление транзакции (сумма, описание, тип: доход/расход)
- [x] Отображение списка всех транзакций
- [x] Автоматический расчёт баланса

### Not yet implemented
- [ ] Категории расходов
- [ ] Фильтрация по дате
- [ ] Графики расходов
- [ ] Удаление/редактирование транзакций

## Usage
1. Откройте браузер и перейдите по адресу `http://<IP-вашей-ВМ>:5000`
2. Заполните форму "Add transaction" (сумма, описание, тип)
3. Нажмите "Add" – транзакция появится в таблице
4. Баланс обновляется автоматически

## Deployment
- **OS**: Ubuntu 24.04
- **Requirements**: Python 3.10+, pip, SQLite (встроен)

### Manual setup (without Docker)
```bash
git clone git@github.com:Leilia34/se-toolkit-hackathon.git
cd se-toolkit-hackathon
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app/main.py

