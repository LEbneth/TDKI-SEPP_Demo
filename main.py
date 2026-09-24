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

def get_knowledge_answer(user_message):
    message=user_message.lower()
    asks_about_weakness=any(
        phrase in message
        for phrase in (
            "schwachstelle",
            "sicherheitslücke",
            "warum ist",
            "warum hat",
            "wie funktioniert der angriff",
        )
    )
    if not asks_about_weakness:
        return None

    if "glühbirne" in message or "gluhbirne" in message or "lampe" in message:
        return (
            "Die Glühbirne nimmt Steuerbefehle unverschlüsselt und ohne "
            "Anmeldung über Telnet an. Ein Angreifer kann die Befehle "
            "dadurch mitlesen und erneut senden."
        )

    if "schloss" in message or "tür" in message or "tur" in message:
        return (
            "Das Türschloss überträgt die benötigten Zugangsdaten "
            "unverschlüsselt über MQTT. Wer den Netzwerkverkehr mitliest, "
            "kann die Zugangsdaten verwenden und das Schloss steuern."
        )

    return None

def select_tool(user_message,scan_completed):
    knowledge_answer=get_knowledge_answer(user_message)
    if knowledge_answer is not None:
        return {
            "action":"none",
            "response_type":"answer",
            "status_message":"",
            "answer":knowledge_answer
        }

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
            "response_type":"status",
            "status_message":"Ich konnte leider nicht bestimmen, wie ich diese Anfrage bearbeiten soll.",
            "answer":""
        }
    action=decision.get("action","none")
    response_type=decision.get("response_type","status")
    status_message=decision.get("status_message","")
    answer=decision.get("answer","")
    if action not in TOOLS:
        action="none"
    if not scan_completed and action not in ("none","network_scan"):
        action="none"
        response_type="status"
        answer=""
        status_message=(
            "Zuerst muss eine Reconnaissance des Zielnetzes erfolgen. "
            "Starte den Netzwerk-Scan, um die verfügbaren Ziele zu erfassen."
        )
    return {
        "action":action,
        "response_type":response_type,
        "status_message":status_message,
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

def build_fast_result_answer(action,tool_output):
    if any(
        marker in tool_output.lower()
        for marker in ("fehler", "error", "failed", "timeout", "konnte nicht")
    ):
        return tool_output

    if action=="lightbulb_on":
        return (
            "*Glühbirne wurde erfolgreich eingeschaltet.*\n\n"
            "Einfach erklärt: Die Glühbirne nimmt Steuerbefehle über eine "
            "ungeschützte Verbindung an. Deshalb kann ein Angreifer den "
            "Befehl ohne Anmeldung erneut senden."
        )
    if action=="lightbulb_off":
        return (
            "*Glühbirne wurde erfolgreich ausgeschaltet.*\n\n"
            "Einfach erklärt: Die Glühbirne nimmt Steuerbefehle über eine "
            "ungeschützte Verbindung an. Deshalb kann ein Angreifer den "
            "Befehl ohne Anmeldung erneut senden."
        )
    if action=="lock_open":
        return (
            "*Türschloss wurde erfolgreich geöffnet.*\n\n"
            "Einfach erklärt: Die Zugangsdaten des Schlosses werden "
            "unverschlüsselt übertragen und können mitgelesen werden."
        )
    if action=="lock_close":
        return (
            "*Türschloss wurde erfolgreich geschlossen.*\n\n"
            "Einfach erklärt: Die Zugangsdaten des Schlosses werden "
            "unverschlüsselt übertragen und können mitgelesen werden."
        )
    if action=="lock_status":
        return f"*Schlossstatus abgefragt.*\n\n{tool_output}"
    return None

def analyze_result_stream(user_message,action,tool_output):
    prompt=load_prompt("3_analysis",user_message=user_message,action=action,tool_output=tool_output)
    response=requests.post(
        OLLAMA_URL,
        json={
            "model":MODEL,
            "messages":[{"role":"system","content":prompt}],
            "stream":True,
            "keep_alive":OLLAMA_KEEP_ALIVE,
            "options":{
                "num_predict":220,
                "temperature":0.2
            }
        },
        stream=True,
        timeout=120
    )
    response.raise_for_status()
    for line in response.iter_lines():
        if not line:
            continue
        try:
            data=json.loads(line)
        except json.JSONDecodeError:
            continue
        if data.get("done"):
            break
        token=data.get("message",{}).get("content","")
        if token:
            yield token

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
        status_message=decision["status_message"]

        if action=="none":
            if decision["response_type"]=="answer" and decision["answer"]:
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
            yield "data: "+json.dumps({
                "type":"status",
                "text":status_message
            },ensure_ascii=False)+"\n\n"
            return

        yield "data: "+json.dumps({
            "type":"status",
            "text":status_message
        },ensure_ascii=False)+"\n\n"
        await asyncio.sleep(0.1)

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

        yield "data: "+json.dumps({
            "type":"completed",
            "text":"Die Operation wurde erfolgreich ausgeführt. Ich analysiere jetzt die Ergebnisse.",
            "action":action,
            "success":not tool_output.startswith("Bei der Operation ist ein Fehler aufgetreten:")
        },ensure_ascii=False)+"\n\n"
        await asyncio.sleep(0.1)

        fast_answer=build_fast_result_answer(action,tool_output)
        if fast_answer is not None:
            yield "data: "+json.dumps({
                "type":"answer_start"
            },ensure_ascii=False)+"\n\n"
            yield "data: "+json.dumps({
                "type":"token",
                "text":fast_answer
            },ensure_ascii=False)+"\n\n"
            yield "data: "+json.dumps({
                "type":"answer_end"
            },ensure_ascii=False)+"\n\n"
            return

        yield "data: "+json.dumps({
            "type":"answer_start"
        },ensure_ascii=False)+"\n\n"

        queue=asyncio.Queue()
        loop=asyncio.get_running_loop()

        def stream_worker():
            try:
                for token in analyze_result_stream(
                    user_message,
                    action,
                    tool_output
                ):
                    asyncio.run_coroutine_threadsafe(
                        queue.put(token),
                        loop
                    )
            except Exception as e:
                asyncio.run_coroutine_threadsafe(
                    queue.put(
                        f"\n\nBei der Analyse der Ergebnisse ist ein Fehler aufgetreten: {e}"
                    ),
                    loop
                )
            finally:
                asyncio.run_coroutine_threadsafe(
                    queue.put(None),
                    loop
                )

        asyncio.create_task(
            asyncio.to_thread(stream_worker)
        )

        while True:
            token=await queue.get()
            if token is None:
                break
            yield "data: "+json.dumps({
                "type":"token",
                "text":token
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