import anthropic
from datetime import datetime
from pathlib import Path

PROMPTS = {
    "work": """Ты — профессиональный ассистент для ведения протоколов рабочих встреч. Проанализируй транскрипцию встречи и создай структурированное саммари на русском языке.

Сфокусируйся на:
- Принятых решениях
- Задачах (action items) с ответственными и дедлайнами
- Ключевых обсуждаемых вопросах
- Блокерах и рисках

Формат ответа:

# Встреча: [определи тему встречи]
**Дата:** {date}
**Длительность:** {duration}
**Язык:** {language}
**Тип:** Рабочая встреча

## Краткое содержание
2-3 предложения о сути встречи.

## Ключевые инсайты
- Инсайт 1
- Инсайт 2

## Решения и договорённости
- Что решили, кто отвечает

## Задачи (Action Items)
- [ ] Задача — ответственный — дедлайн

## Важные цитаты
> Дословные цитаты, которые важно запомнить

Транскрипция:

{transcript}""",

    "english": """Ты — профессиональный ассистент для анализа уроков английского языка. Проанализируй транскрипцию урока и создай структурированное саммари на русском языке.

Сфокусируйся на:
- Новой лексике и фразах
- Грамматических темах
- Ошибках ученика и исправлениях
- Рекомендациях преподавателя
- Домашнем задании
- Наблюдениях о прогрессе

Формат ответа:

# Урок английского: [определи тему урока]
**Дата:** {date}
**Длительность:** {duration}
**Язык:** {language}
**Тип:** Урок английского

## Краткое содержание
2-3 предложения о сути урока.

## Новая лексика и фразы
| Слово/фраза | Перевод | Пример использования |
|-------------|---------|---------------------|
| word | перевод | пример |

## Грамматика
- Тема 1: объяснение
- Тема 2: объяснение

## Ошибки и исправления
- Ошибка → Правильный вариант

## Рекомендации преподавателя
- Рекомендация 1

## Домашнее задание
- [ ] Задание 1

## Прогресс
Наблюдения о прогрессе ученика.

Транскрипция:

{transcript}""",

    "personal": """Ты — профессиональный ассистент для конспектирования личных встреч. Проанализируй транскрипцию встречи и создай структурированное саммари на русском языке. Будь уважителен и профессионален.

Сфокусируйся на:
- Ключевых личных инсайтах
- Рекомендациях и советах
- Обсуждаемых темах
- Направлениях для дальнейших действий

Формат ответа:

# Личная встреча: [определи основную тему]
**Дата:** {date}
**Длительность:** {duration}
**Язык:** {language}
**Тип:** Личная встреча

## Краткое содержание
2-3 предложения о сути встречи.

## Ключевые инсайты
- Инсайт 1
- Инсайт 2

## Рекомендации и советы
- Рекомендация 1
- Рекомендация 2

## Обсуждаемые темы
- Тема 1: краткое описание
- Тема 2: краткое описание

## Направления для дальнейших действий
- Направление 1
- Направление 2

## Важные цитаты
> Дословные цитаты, которые важно запомнить

## Задачи
- [ ] Задание 1

Транскрипция:

{transcript}""",
}

LANGUAGE_NAMES = {
    "ru": "Русский",
    "en": "English",
    "auto": "Авто",
}


def _format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0:
        return f"{h} ч {m} мин"
    return f"{m} мин"


def build_prompt(transcript: str, meeting_type: str, **kwargs) -> str:
    template = PROMPTS.get(meeting_type, PROMPTS["work"])
    return template.format(
        transcript=transcript,
        date=kwargs.get("date", datetime.now().strftime("%Y-%m-%d %H:%M")),
        duration=kwargs.get("duration", "N/A"),
        language=kwargs.get("language", "Русский"),
    )


def _summarize_claude(prompt: str, api_key: str, model: str) -> str:
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


CHUNK_SIZE = 6000

CHUNK_PROMPT = """Проанализируй этот фрагмент транскрипции встречи и выдели:
- Ключевые темы и обсуждения
- Принятые решения
- Задачи и ответственные
- Важные цитаты

Фрагмент {chunk_num} из {total_chunks}:

{chunk_text}"""

MERGE_PROMPT = """Ты получил промежуточные саммари частей одной встречи. Объедини их в единое структурированное саммари.

{format_instructions}

Промежуточные саммари:

{chunk_summaries}"""


def _split_into_chunks(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    lines = text.split("\n")
    chunks = []
    current_chunk: list[str] = []
    current_size = 0

    for line in lines:
        line_size = len(line) + 1
        if current_size + line_size > chunk_size and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_size = 0
        current_chunk.append(line)
        current_size += line_size

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


def summarize(
    transcript: str,
    output_path: Path,
    meeting_type: str,
    language: str,
    duration_seconds: int,
    api_key: str = "",
    model: str = "claude-sonnet-4-6",
) -> str | None:
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    duration_str = _format_duration(duration_seconds)
    lang_str = LANGUAGE_NAMES.get(language, language)

    if not api_key:
        raise RuntimeError("Не настроен API ключ Claude")

    try:
        if len(transcript) <= CHUNK_SIZE:
            prompt = build_prompt(
                transcript, meeting_type,
                date=date_str, duration=duration_str, language=lang_str,
            )
            summary_text = _summarize_claude(prompt, api_key, model)
        else:
            chunks = _split_into_chunks(transcript)
            chunk_summaries = []
            for i, chunk in enumerate(chunks):
                chunk_prompt = CHUNK_PROMPT.format(
                    chunk_num=i + 1, total_chunks=len(chunks), chunk_text=chunk,
                )
                chunk_summary = _summarize_claude(chunk_prompt, api_key, model)
                chunk_summaries.append(f"### Часть {i + 1}\n{chunk_summary}")

            template = PROMPTS.get(meeting_type, PROMPTS["work"])
            format_part = template.split("Транскрипция:")[0]
            format_instructions = format_part.format(
                date=date_str, duration=duration_str, language=lang_str,
                transcript="",
            )

            merge_prompt = MERGE_PROMPT.format(
                format_instructions=f"Используй этот формат:\n{format_instructions}",
                chunk_summaries="\n\n".join(chunk_summaries),
            )
            summary_text = _summarize_claude(merge_prompt, api_key, model)
    except Exception:
        return None

    output_path.write_text(summary_text, encoding="utf-8")
    return summary_text
