import logging

from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )
    return _client


SYSTEM_PROMPTS = {
    "ru": (
        "Ты профессиональный аналитик разговоров. "
        "Получаешь транскрипцию речи и должен:\n"
        "1. Сделать краткое САММАРИ (2-4 предложения)\n"
        "2. Дать конкретные РЕКОМЕНДАЦИИ по следующим шагам (3-5 пунктов)\n"
        "3. Придумать НАЗВАНИЕ записи — ровно 2-3 слова, суть разговора\n"
        "Отвечай строго в формате:\n"
        "САММАРИ:\n<текст>\n\nРЕКОМЕНДАЦИИ:\n<пункты>\n\nНАЗВАНИЕ:\n<слова>"
    ),
    "en": (
        "You are a professional conversation analyst. "
        "You receive a speech transcription and must:\n"
        "1. Write a concise SUMMARY (2-4 sentences)\n"
        "2. Give specific RECOMMENDATIONS for next steps (3-5 points)\n"
        "3. Create a TITLE for the recording — exactly 2-3 words capturing the essence\n"
        "Respond strictly in format:\n"
        "SUMMARY:\n<text>\n\nRECOMMENDATIONS:\n<points>\n\nTITLE:\n<words>"
    ),
    "zh": (
        "你是一名专业的对话分析师。"
        "你将收到语音转录文本，需要：\n"
        "1. 写一个简洁的摘要（2-4句话）\n"
        "2. 给出具体的后续步骤建议（3-5条）\n"
        "3. 为录音创建标题——恰好2-3个词，概括要点\n"
        "严格按以下格式回复：\n"
        "摘要：\n<文本>\n\n建议：\n<条目>\n\n标题：\n<词语>"
    ),
    "es": (
        "Eres un analista profesional de conversaciones. "
        "Recibes una transcripción de voz y debes:\n"
        "1. Escribir un RESUMEN conciso (2-4 oraciones)\n"
        "2. Dar RECOMENDACIONES específicas para los próximos pasos (3-5 puntos)\n"
        "3. Crear un TÍTULO para la grabación — exactamente 2-3 palabras que capturen la esencia\n"
        "Responde estrictamente en el formato:\n"
        "RESUMEN:\n<texto>\n\nRECOMENDACIONES:\n<puntos>\n\nTÍTULO:\n<palabras>"
    ),
}

# (summary_key, recommendations_key, title_key)
SPLIT_KEYS = {
    "ru": ("САММАРИ:", "РЕКОМЕНДАЦИИ:", "НАЗВАНИЕ:"),
    "en": ("SUMMARY:", "RECOMMENDATIONS:", "TITLE:"),
    "zh": ("摘要：", "建议：", "标题："),
    "es": ("RESUMEN:", "RECOMENDACIONES:", "TÍTULO:"),
}


async def analyze(transcription: str, language: str) -> tuple[str, str, str]:
    """Returns (summary, recommendations, title)."""
    client = get_client()
    system = SYSTEM_PROMPTS.get(language, SYSTEM_PROMPTS["en"])

    response = await client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": transcription},
        ],
        max_tokens=1024,
        temperature=0.5,
    )

    content = response.choices[0].message.content or ""
    return _parse_response(content, language)


def _parse_response(content: str, language: str) -> tuple[str, str, str]:
    summary_key, reco_key, title_key = SPLIT_KEYS.get(language, SPLIT_KEYS["en"])

    s_idx = content.find(summary_key)
    r_idx = content.find(reco_key)
    t_idx = content.find(title_key)

    summary = ""
    recommendations = ""
    title = ""

    if s_idx != -1 and r_idx != -1:
        summary = content[s_idx + len(summary_key):r_idx].strip()
    elif s_idx != -1:
        end = r_idx if r_idx != -1 else t_idx if t_idx != -1 else len(content)
        summary = content[s_idx + len(summary_key):end].strip()

    if r_idx != -1:
        end = t_idx if t_idx != -1 else len(content)
        recommendations = content[r_idx + len(reco_key):end].strip()

    if t_idx != -1:
        title = content[t_idx + len(title_key):].strip()
        # Keep only first line and max 60 chars
        title = title.split("\n")[0].strip()[:60]

    if not summary:
        summary = content.strip()

    if not title:
        # Fallback: first 3 words of summary
        words = summary.split()[:3]
        title = " ".join(words) if words else "Запись"

    return summary, recommendations, title
