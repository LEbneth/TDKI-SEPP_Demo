import json
import subprocess
import asyncio
import requests
from pathlib import Path
from fastapi import FastAPI,Request
from fastapi.responses import HTMLResponse,StreamingResponse,JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

OLLAMA_URL="http://localhost:11434/api/chat"
#MODEL="qwen3:4b"
MODEL="qwen2.5:3b"
OLLAMA_KEEP_ALIVE="30m"
OLLAMA_OPTIONS={
    "num_predict":160,
    "temperature":0.2
}
BASE_DIR=Path(__file__).parent
PROMPTS_DIR=BASE_DIR/"prompts"

TOOLS={
    "lightbulb_off":BASE_DIR/"scripts"/"lightbulb_off.py",
    "lightbulb_on":BASE_DIR/"scripts"/"lightbulb_on.py",
    "lock_close":BASE_DIR/"scripts"/"lock_close.py",
    "lock_open":BASE_DIR/"scripts"/"lock_open.py",
    "lock_status":BASE_DIR/"scripts"/"lock_status.py",
    "network_scan":BASE_DIR/"scripts"/"network_scan.py",
}

app=FastAPI()
templates=Jinja2Templates(directory=BASE_DIR/"templates")

def load_context():
    return (BASE_DIR/"prompts"/"context.txt").read_text(encoding="utf-8")

def load_prompt(name,**kwargs):
    prompt=load_context()+(PROMPTS_DIR/f"{name}.txt").read_text(encoding="utf-8")
    for key,value in kwargs.items():
        prompt=prompt.replace("{"+key+"}",str(value))
    return prompt

def generate_introduction():
    prompt=load_prompt("0_introduction")
    response=requests.post(
        OLLAMA_URL,
        json={
            "model":MODEL,
            "messages":[
                {"role":"system","content":prompt}
            ],
            "stream":False,
            "keep_alive":OLLAMA_KEEP_ALIVE,
            "options":OLLAMA_OPTIONS
        },
        timeout=120
    )
    response.raise_for_status()
    return response.json()["message"]["content"].strip()

def execute_tool(tool_name):
    if tool_name not in TOOLS:
        return "Fehler: Ungültige Operation."
    try:
        result=subprocess.run(
            ["python",str(TOOLS[tool_name])],
            capture_output=True,
            text=True
        )
        if result.returncode!=0:
            return "Bei der Operation ist ein Fehler aufgetreten:\n\n"+result.stderr
        return result.stdout.strip()
    except Exception as e:
        return f"Die Operation konnte nicht ausgeführt werden: {e}"

def select_tool(user_message,scan_completed):
    prompt=load_prompt(
        "1_tool_selection",
        scan_completed="ja" if scan_completed else "nein"
    )
    response=requests.post(
        OLLAMA_URL,
        json={
            "model":MODEL,
            "messages":[
                {"role":"system","content":prompt},
                {"role":"user","content":user_message}
            ],
            "stream":False,
            "keep_alive":OLLAMA_KEEP_ALIVE,
            "options":{
                "num_predict":120,
                "temperature":0.1
            }
        },
        timeout=120
    )
    response.raise_for_status()
    content=response.json()["message"]["content"]
    content=content.replace("```json","").replace("```","").strip()
    try:
        decision=json.loads(content)
    except json.JSONDecodeError:
        print("[FEHLER] Ungültige Antwort bei der Operationsauswahl:")
        print(content)
        return {
            "action":"none",
            "answer":content or (
                "Die Anfrage konnte nicht verarbeitet werden. "
                "Bitte formuliere sie anders."
            )
        }
    action=decision.get("action","none")
    answer=decision.get("answer","")
    if action not in TOOLS:
        action="none"
    if not scan_completed and action not in ("none","network_scan"):
        action="none"
        answer=(
            "Bevor ein Gerät ausgewählt werden kann, muss zuerst der "
            "Netzwerk-Scan durchgeführt werden."
        )
    return {
        "action":action,
        "answer":answer
    }

PROGRESS_MESSAGES={
    "network_scan":"Reconnaissance läuft: Zielnetz wird nach erreichbaren Geräten und offenen Diensten durchsucht.",
    "lightbulb_on":"Exploit-Vektor wird vorbereitet: Steuerkanal der IoT-Glühbirne wird geprüft.",
    "lightbulb_off":"Exploit-Vektor wird vorbereitet: Steuerkanal der IoT-Glühbirne wird geprüft.",
    "lock_open":"MQTT-Angriffsfläche wird analysiert: Öffnungsbefehl wird vorbereitet.",
    "lock_close":"MQTT-Angriffsfläche wird analysiert: Schließbefehl wird vorbereitet.",
    "lock_status":"Schloss-Telemetrie wird abgefragt: aktueller Status wird ermittelt."
}

def generate_progress_message(action):
    return PROGRESS_MESSAGES.get(
        action,
        "Sicherheitsprüfung läuft: Zielkommunikation wird analysiert."
    )

@app.get("/",response_class=HTMLResponse)
async def index(request:Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )

@app.get("/introduction")
async def introduction():
    try:
        text=await asyncio.to_thread(generate_introduction)
        return JSONResponse({"text":text})
    except Exception as e:
        print("[FEHLER] Einführung konnte nicht generiert werden:",e)
        return JSONResponse(
            {"text":"Hallo! Ich bin SenpAI, dein lokaler IoT-Sicherheitsassistent. Wie kann ich dir helfen?"},
            status_code=200
        )

class ChatRequest(BaseModel):
    message:str
    scan_completed:bool=False

@app.post("/chat")
async def chat(request:ChatRequest):
    async def event_stream():
        user_message=request.message.strip()

        yield "data: "+json.dumps({
            "type":"thinking",
            "text":"Ich überlege, wie ich deine Anfrage am besten bearbeiten kann."
        },ensure_ascii=False)+"\n\n"
        await asyncio.sleep(0.05)

        try:
            decision=await asyncio.to_thread(
                select_tool,
                user_message,
                request.scan_completed
            )
        except Exception as e:
            yield "data: "+json.dumps({
                "type":"status",
                "text":f"Bei der Verarbeitung deiner Anfrage ist ein Fehler aufgetreten: {e}"
            },ensure_ascii=False)+"\n\n"
            return

        action=decision["action"]

        if action=="none":
            yield "data: "+json.dumps({
                "type":"answer_start"
            },ensure_ascii=False)+"\n\n"
            yield "data: "+json.dumps({
                "type":"token",
                "text":decision["answer"]
            },ensure_ascii=False)+"\n\n"
            yield "data: "+json.dumps({
                "type":"answer_end"
            },ensure_ascii=False)+"\n\n"
            return

        progress_message=generate_progress_message(action)

        yield "data: "+json.dumps({
            "type":"progress",
            "text":progress_message
        },ensure_ascii=False)+"\n\n"
        await asyncio.sleep(0.1)

        tool_output=await asyncio.to_thread(
            execute_tool,
            action
        )

        completed_text=(
            "Scan abgeschlossen. Rohdaten werden direkt angezeigt."
            if action=="network_scan"
            else "Operation abgeschlossen. Skriptausgabe wird direkt angezeigt."
        )
        yield "data: "+json.dumps({
            "type":"completed",
            "text":completed_text,
            "action":action,
            "success":not tool_output.startswith("Bei der Operation ist ein Fehler aufgetreten:")
        },ensure_ascii=False)+"\n\n"
        await asyncio.sleep(0.1)

        yield "data: "+json.dumps({
            "type":"answer_start"
        },ensure_ascii=False)+"\n\n"
        yield "data: "+json.dumps({
            "type":"token",
            "text":tool_output
        },ensure_ascii=False)+"\n\n"
        yield "data: "+json.dumps({
            "type":"answer_end"
        },ensure_ascii=False)+"\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":"no-cache",
            "Connection":"keep-alive"
        }
    )

if __name__=="__main__":
    import uvicorn
    print("======================================")
    print("               SenpAI")
    print("======================================")
    print("Browser: http://127.0.0.1:8000")
    print("Zum Beenden STRG+C drücken.")
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000
    )