from dotenv import load_dotenv
load_dotenv()

import uuid
from threading import Lock
from fastapi import FastAPI, BackgroundTasks
from event_crawler import init_db, crawl_domain, get_event_html_code, get_stored_html
from extraction import html_to_clean_text, extract_event_data, create_wp_draft

JOBS: dict[str, dict] = {}
JOBS_LOCK = Lock()

def new_job(domains: list[str]) -> str:
    job_id = str(uuid.uuid4())
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running",
            "domains": {d: {"status": "queued", "events_found": 0} for d in domains},
            "events": [],
        }
    return job_id

def crawl_and_extract_links(domain: str) -> list[dict]:
    conn = init_db()
    crawl_domain(conn, domain)
    conn.close()
    return get_event_html_code(domain)

app = FastAPI()

@app.post("/crawl/start")
def start_crawl(payload: dict, background_tasks: BackgroundTasks):
    domains = payload.get("domains", [])
    job_id = new_job(domains)
    background_tasks.add_task(run_crawl_job, job_id, domains)
    return {"job_id": job_id}

def run_crawl_job(job_id: str, domains: list[str]):
    for domain in domains:
        JOBS[job_id]["domains"][domain]["status"] = "crawling"
        try:
            # euer bestehender crawl_domain()-Aufruf, pro Domain statt Batch,
            # damit der Status zwischendrin aktualisiert werden kann
            events = crawl_and_extract_links(domain)
            JOBS[job_id]["domains"][domain]["status"] = "done"
            JOBS[job_id]["domains"][domain]["events_found"] = len(events)
            JOBS[job_id]["events"].extend(events)
        except Exception as exc:
            JOBS[job_id]["domains"][domain]["status"] = "error"
    JOBS[job_id]["status"] = "done"

@app.get("/crawl/status")
def crawl_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return {"status": "error", "error": "job_id nicht gefunden"}
    return {
        "status": job["status"],
        "domains": [{"domain": d, **info} for d, info in job["domains"].items()],
        "events": job["events"],
    }

@app.post("/crawl/create-draft")
def create_draft(payload: dict):
    event_url = payload.get("event_url")
    if not event_url:
        return {"message": "event_url fehlt"}

    html = get_stored_html(event_url)
    if not html:
        return {"message": f"Kein gespeichertes HTML für {event_url} gefunden"}

    text = html_to_clean_text(html)
    event_data = extract_event_data(text)
    if not event_data:
        return {"message": "Extraktion fehlgeschlagen, Claude-Antwort war kein gültiges JSON"}

    try:
        wp_post = create_wp_draft(event_data)
    except requests.RequestException as exc:
        return {"message": f"WordPress-Fehler: {exc}"}

    return {"post_id": wp_post["id"]}