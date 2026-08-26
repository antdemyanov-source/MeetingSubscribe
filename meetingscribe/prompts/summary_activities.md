## Привязка встречи к активности (системная инструкция MeetingScribe)

Если основные правила саммари уже содержат шаг привязки к активности и ты его
выполнил — пропусти этот раздел, не дублируй действия.

После создания summary.md привяжи встречу к активности (теме) в SQLite базе
`data/meetingscribe.db` (путь — относительно рабочей директории).

1. Получи список активностей:

```python
import sqlite3
conn = sqlite3.connect("data/meetingscribe.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, name FROM activities ORDER BY name").fetchall()
```

2. Выбери подходящую по смыслу встречи. Если ни одна не подходит — создай новую:
   ID — kebab-case транслитерация названия (кириллица → латиница), до 50 символов.

```python
conn.execute("INSERT INTO activities (id, name, description) VALUES (?, ?, ?)",
             (act_id, name, description))
conn.commit()
```

3. Привяжи встречу (folder — АБСОЛЮТНЫЙ путь к папке встречи):

```python
import re
from pathlib import Path

existing = conn.execute("SELECT * FROM meetings WHERE folder = ?", (folder,)).fetchone()
if existing:
    conn.execute("UPDATE meetings SET activity_id = ? WHERE folder = ?", (act_id, folder))
else:
    # ВАЖНО: заполняй date, time, topic — иначе встреча не отобразится в приложении
    m = re.match(r"(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})_(.+)", Path(folder).name)
    date_val = m.group(1) if m else ""
    time_val = f"{m.group(2)}:{m.group(3)}" if m else ""
    conn.execute(
        "INSERT INTO meetings (activity_id, date, time, topic, folder) VALUES (?, ?, ?, ?, ?)",
        (act_id, date_val, time_val, title, folder))
conn.commit()
```

4. Добавь поле `**Активность:** <название>` в шапку summary.md.

Для личных встреч (personal) и уроков английского активность не привязывается.
