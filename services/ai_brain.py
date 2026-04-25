import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

client = AsyncOpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1",
)

SYSTEM_PROMPT = """You are Helios, a specialized AI that designs solar energy systems.
Your ONLY job is to assist with:
- Solar panel layout and system design
- Electrical engineering (NEC code compliance)
- Financial analysis of solar projects
- Answering questions about solar energy

You do NOT answer any questions unrelated to solar energy. If asked something off-topic, politely refuse.
You can call tools to fetch roof data, optimize layouts, and run calculations.
For now, if you need to call a tool, simply say "TOOL: <tool_name>" and the system will handle it.
"""

async def run_helios_chat(user_message: str, project_id: str | None = None) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    response = await client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=0.3,
        max_tokens=1000,
    )
    return response.choices[0].message.content
