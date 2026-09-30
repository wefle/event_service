const API_BASE = 'http://localhost:8000';
const INTERVAL_MS = 3000;
let timer = null;

const API_KEY = 'f637730c996e027df97fe8d6946907034d34027027419d8daa587c29c2517d4a';

function handleEventScraping(event) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const domainVal = data.get("domain");
    const pattern = /([0-9a-zA-Z]+)\.([a-z]{2,3})/
    if(domainVal.match(pattern)){
        document.querySelector('#msg').innerHTML="";
        //start server
        //startCrawl
        startCrawl(domainVal);
        //results
        //card - entwürfe
    }
    else{
        document.querySelector('#msg').innerHTML="Die angegebene Domain ist nicht korrekt!";
    }
}

async function startCrawl(domain) {

  const status = document.querySelector('.status-window .status')
  status.innerHTML = 'Suche läuft...';

  try {
    const res = await fetch(`${API_BASE}/crawl/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Api-Key': API_KEY },
      body: JSON.stringify({ domains: [domain] })
    });
    if (!res.ok) throw new Error('Server antwortete mit ' + res.status);
    const data = await res.json();
    timer = setInterval(() => showCurrResult(data.job_id), INTERVAL_MS);

  } catch (e) {
    status.innerHTML='Fehler beim Start: ' + e.message;
  }
}

async function showCurrResult(jobId) {
  if (!jobId) return;
  const status = document.querySelector('.status-window .status');
  const resultBtn = document.querySelector('.status-window .result-btn');
  try {
    const res = await fetch(`${API_BASE}/crawl/status?job_id=${encodeURIComponent(jobId)}`);
    const data = await res.json();

    if (data.status === 'done') {
        clearInterval(timer);
        const totalEvents = (data.events || []).length;
        status.innerHTML = `${totalEvents} mögliche Event-Seite(n) gefunden.`;
        resultBtn.style.display = 'block';
        resultBtn.addEventListener('click', () => createDraft(jobId, data.events));
    } else if (data.status === 'error') {
        clearInterval(timer);
        status.innerHTML ='Fehler beim Crawlen: ' + (data.error || 'unbekannt');
    }
  } catch (e) {
    console.error('Status-Anzeige fehlgeschlagen', e);
  }
}

async function createDraft(jobId, events) {
  const cardContainer = document.querySelector('.status-window .card-container');
  for(const event of events) {
    const div = document.createElement("div");
    const h3 = document.createElement("h3");
    const btn1 = document.createElement("button");
    const btn2 = document.createElement("button");
    const p = document.createElement("p");

    div.appendChild(h3);
    div.appendChild(btn1);
    div.appendChild(btn2);
    div.appendChild(p);

    h3.innerHTML = event.url;
    btn1.innerHTML = "Entwurf erstellen";
    btn2.innerHTML = "Löschen";

    div.className = "card";

    cardContainer.appendChild(div);

    btn1.addEventListener('click', async function(){
      try {
        const res = await fetch(`${API_BASE}/crawl/create-draft`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Api-Key': API_KEY },
          body: JSON.stringify({ job_id: jobId, event_url: event.url })
        });
        const data = await res.json();

        if (res.ok && data.post_id) {
          p.innerHTML = "Entwurf ist erfolgreich angelegt worden."
        } else {
          p.innerHTML = "Entwurf konnte nicht angelegt werden."
        }
      } catch (e) {
        console.log(e)
      }
    });

    btn2.addEventListener('click', function(){
      cardContainer.removeChild(div);
    });
  }
}