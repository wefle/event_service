import os
import json
import requests
from anthropic import Anthropic
from bs4 import BeautifulSoup

def html_to_clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)

client = Anthropic() 

WP_BASE = os.environ["WP_BASE_URL"] 
WP_AUTH = (os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"])

EXTRACTION_PROMPT = """Du bist ein Assistent der Event-Informationen aus Webseiten extrahiert.

Antworte NUR mit einem JSON-Objekt ohne Markdown-Backticks:
{{
  "name": "Eventname oder leer",
  "datum": "YYYY-MM-DD oder leer",
  "uhrzeit": "HH:MM oder leer",
  "ort": "Ortsname oder leer",
  "adresse": "Straße und Stadt oder leer",
  "beschreibung": "Vollständige Beschreibung des Events",
  "preis": "Preis oder leer",
  "veranstalter": "Veranstalter oder leer"
}}

Seiteninhalt:
{page_text}
"""

def extract_event_data(page_text: str) -> dict:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": EXTRACTION_PROMPT.format(page_text=page_text)
        }]
    )
    raw = response.content[0].text
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {}
    
def create_wp_draft(event_data: dict) -> dict:
    response = requests.post(
        f"{WP_BASE}/wp/v2/event",
        auth=WP_AUTH,
        json={
            "title": event_data.get("name") or "Unbenanntes Event",
            "status": "draft",
            "acf": {
                "event_datum": event_data.get("datum", ""),
                "event_uhrzeit": event_data.get("uhrzeit", ""),
                "event_ort": event_data.get("ort", ""),
                "event_adresse": event_data.get("adresse", ""),
                "event_beschreibung": event_data.get("beschreibung", ""),
                "event_preis": event_data.get("preis", ""),
                "event_veranstalter": event_data.get("veranstalter", ""),
            },
        },
    )
    response.raise_for_status()
    return response.json()