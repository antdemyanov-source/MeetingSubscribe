# Создание саммари встречи

Пользователь передаёт путь к `transcript.md` (или папку встречи). Твоя задача — создать полное саммари, привязать встречу к активности (теме) и создать задачи.

## Шаги выполнения

### 1. Подготовка — читай обязательно

Прочитай **все три файла** до начала работы:
- `C:\AI\MeetingScribe\recordings\context.md` — люди, системы, компания, словарь транскрибации
- `transcript.md` — исходная транскрипция из указанной папки
- `meta.json` — метаданные (дата, длительность, тип: `work` / `personal` / `english`)

### 2. Определи тип встречи по `meeting_type` из meta.json и создай summary.md

---

#### Тип: `work` — рабочая встреча

**Язык:** русский.

```markdown
# Саммари — <тема встречи>

**Дата:** <день месяц год, напр. "3 июля 2026">
**Длительность:** ~<N> мин
**Участники:** <имена через запятую, роль/команда в скобках>
**Активность:** <название активности — заполнишь на шаге 3>

---

## 1. <Название темы>

- Пункты по существу
- **Проблема:** / **Решение:** / **Риск:** — выделяй жирным ключевые маркеры
- Подразделы через `### <Подтема>` при необходимости

---

## 2. <Следующая тема>

...

---

## Действия

| Кто | Что |
|-----|-----|
| Имя | Конкретное действие |
```

**Правила:**
- Колонку `| Срок |` добавляй **только** если срок явно озвучен на встрече
- Нумерованные разделы с `---` между ними
- Используй `context.md` для правильных имён и терминов
- Если участник не идентифицирован точно — `Имя (Фамилия?)`
- Если речь одного участника не записалась — укажи в примечании

---

#### Тип: `personal` — личная встреча (психолог и т.п.)

**Язык:** русский.

```markdown
# Саммари — <тема сессии>

**Дата:** <день месяц год>
**Длительность:** ~<N> мин

---

## 1. <Тема / блок сессии>

- Описание, инсайты, механизмы
- **Инсайт:** / **Механизм:** / **Паттерн:** — маркеры жирным
- Прямые цитаты в кавычках, если несут ключевой смысл

---

## <N>. Вопрос на следующий раз / Ключевые выводы

- Вопрос от терапевта или список ключевых выводов
```

**Правила:**
- **Нет** поля «Участники» — контекст всегда понятен
- **Нет** поля «Активность»
- **Нет** таблицы действий
- Тон: рефлексивный, интроспективный, используй терминологию если уместно
- Сохраняй метафоры и значимые цитаты

---

#### Тип: `english` — урок английского

**Язык:** английский. Русский **только** в колонке перевода таблицы лексики.

```markdown
# Summary — English Lesson: <topic list>

**Date:** <Month day, year>
**Duration:** ~<N> min

---

## Conversation Topics

### 1. <Topic>

- Key points discussed
- Interesting facts or examples

### 2. <Topic>

...

---

## Vocabulary

| English | Russian |
|---------|---------|
| word/phrase | перевод |
| ... | ... |
```

**Правила:**
- **Нет** таблицы действий
- Таблица лексики **обязательна** — извлекай все новые/интересные слова и фразы
- Если после урока запись продолжилась (фильм, фоновый шум) — не включай, только упомяни в примечании
- Раздел грамматики `## Grammar Notes` — только если грамматика реально обсуждалась

---

### 3. Заполни title в meta.json

Добавь или обнови поле `title` — краткое название встречи, до 100 символов.

### 4. Привяжи встречу к активности (теме)

Это критически важный шаг. Встреча должна быть привязана к **активности** в SQLite базе `C:\AI\MeetingScribe\data\meetingscribe.db`.

**Алгоритм:**

1. Получи список существующих активностей:
```python
import sqlite3
conn = sqlite3.connect(r'C:\AI\MeetingScribe\data\meetingscribe.db')
conn.row_factory = sqlite3.Row
rows = conn.execute('SELECT id, name FROM activities ORDER BY name').fetchall()
```

2. **Выбери подходящую** активность по смыслу встречи. Примеры соответствий:
   - Стендапы проекта → `project-standup`
   - Discovery / сейлзы → `discovery-client-name`
   - 1-on-1 с коллегой → `1-on-1-firstname-lastname`
   - HR тематика → `hr-topic`
   - Команда CRM → `team-crm`
   - и т.д.

3. Если **ни одна не подходит** — создай новую:
   - ID: kebab-case транслитерация (кириллица → латиница), до 50 символов
   - Примеры: `kapitalizatsiya-it-raskhodov`, `discovery-bot`
```python
conn.execute(
    "INSERT INTO activities (id, name, description) VALUES (?, ?, ?)",
    (act_id, name, description)
)
conn.commit()
```

4. **Привяжи встречу** к активности:
```python
import re
from pathlib import Path

folder = r'C:\AI\MeetingScribe\recordings\2026\MM\YYYY-MM-DD_HH-MM_<type>'  # полный путь к папке
existing = conn.execute("SELECT * FROM meetings WHERE folder = ?", (folder,)).fetchone()
if existing:
    conn.execute("UPDATE meetings SET activity_id = ? WHERE folder = ?", (act_id, folder))
else:
    # ВАЖНО: обязательно заполняй date, time, topic — иначе встреча не отобразится на вкладке «Активности»
    m = re.match(r"(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})_(.+)", Path(folder).name)
    date_val = m.group(1) if m else ""
    time_val = f"{m.group(2)}:{m.group(3)}" if m else ""
    topic_val = title  # title из meta.json (шаг 3)
    conn.execute(
        "INSERT INTO meetings (activity_id, date, time, topic, folder) VALUES (?, ?, ?, ?, ?)",
        (act_id, date_val, time_val, topic_val, folder)
    )
conn.commit()
```

5. Добавь поле `**Активность:**` в шапку summary.md (для work meetings).

**Для personal meetings и english lessons** — активность не привязывается, шаг пропускается.

### 5. Создай задачи из таблицы действий

Для каждой строки из таблицы `| Кто | Что |` в саммари — создай задачу в БД:

```python
from datetime import datetime

conn.execute(
    "INSERT INTO tasks (title, description, responsible, deadline, status, priority, source, created_at, meeting_id, activity_id) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    (
        what,           # title — текст из колонки "Что"
        "",             # description
        who,            # responsible — текст из колонки "Кто"
        deadline,       # deadline — из колонки "Срок" если есть, иначе ""
        "pending",      # status — "Новая", через 7 дней автоматически станет "Не начата"
        "medium",       # priority
        "meeting",      # source — всегда "meeting"
        datetime.now().strftime("%Y-%m-%d %H:%M"),  # created_at
        meeting_id,     # meeting_id — из таблицы meetings (по folder)
        activity_id     # activity_id — та же активность, что на шаге 4
    )
)
conn.commit()
```

Чтобы получить `meeting_id`:
```python
row = conn.execute("SELECT id FROM meetings WHERE folder = ?", (folder,)).fetchone()
meeting_id = row["id"] if row else None
```

**Для personal meetings и english lessons** — задачи не создаются, шаг пропускается.

---

## Ограничения

- **Не обновляй context.md автоматически.** Если встречается новый человек/система/термин — спроси пользователя.
- **Не обновляй tasks.md** — трекер устарел, используй SQLite.
- После `replace_all` в русском тексте — перечитай файл и проверь все формы склонений.
- Если сомневаешься в имени/фамилии — ставь `?` после: `Вася (Гладышев?)`.

## Аргумент

$ARGUMENTS — путь к transcript.md или к папке встречи. Если не указан — спроси у пользователя.
