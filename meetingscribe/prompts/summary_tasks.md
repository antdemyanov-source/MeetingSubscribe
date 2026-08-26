## Создание задач из саммари (системная инструкция MeetingScribe)

Если основные правила саммари уже содержат шаг создания задач и ты его
выполнил — пропусти этот раздел, не дублируй действия.

Для каждой строки таблицы действий (`| Кто | Что |`) из summary.md создай задачу
в SQLite базе `data/meetingscribe.db` (путь — относительно рабочей директории).

```python
import sqlite3
from datetime import datetime

conn = sqlite3.connect("data/meetingscribe.db")
conn.row_factory = sqlite3.Row

# id встречи по абсолютному пути к папке (если строки нет и активность
# не привязывалась — создай встречу без активности, заполнив date/time/topic)
row = conn.execute("SELECT id, activity_id FROM meetings WHERE folder = ?", (folder,)).fetchone()
meeting_id = row["id"] if row else None
activity_id = row["activity_id"] if row else None

conn.execute(
    "INSERT INTO tasks (title, description, responsible, deadline, status, priority, "
    "source, created_at, meeting_id, activity_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    (
        what,          # текст из колонки «Что»
        "",
        who,           # текст из колонки «Кто»
        deadline,      # из колонки «Срок», если есть, иначе ""
        "pending",
        "medium",
        "meeting",
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        meeting_id,
        activity_id,
    ),
)
conn.commit()
```

Для личных встреч (personal) и уроков английского задачи не создаются.
