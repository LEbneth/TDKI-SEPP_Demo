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
BASE_DIR=Path(__file__).parent
PROMPTS_DIR=BASE_DIR/"prompts"

TOOLS={
    "lightbulb_off":BASE_DIR/"scripts"/"lightbulb_off.py",
    "lightbulb_on":BASE_DIR/"scripts"/"lightbulb_on.py",
    "lock_close":BASE_DIR/"scripts"/"lock_close.py",
    "lock_open":BASE_DIR/"scripts"/"lock_open.py",
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
            "stream":False
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

def select_tool(user_message):
    prompt=load_prompt("1_tool_selection")
    response=requests.post(
        OLLAMA_URL,
        json={
            "model":MODEL,
            "messages":[
                {"role":"system","content":prompt},
                {"role":"user","content":user_message}
            ],
            "stream":False
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
            "status_message":"Ich konnte leider nicht bestimmen, wie ich diese Anfrage bearbeiten soll."
        }
    action=decision.get("action","none")
    status_message=decision.get("status_message","")
    if action not in TOOLS:
        action="none"
    return {
        "action":action,
        "status_message":status_message
    }

def generate_progress_message(user_message,action):
    prompt=load_prompt("2_progress",user_message=user_message,action=action)
    response=requests.post(
        OLLAMA_URL,
        json={
            "model":MODEL,
            "messages":[{"role":"system","content":prompt}],
            "stream":False
        },
        timeout=120
    )
    response.raise_for_status()
    return response.json()["message"]["content"].strip()

def analyze_result_stream(user_message,action,tool_output):
    prompt=load_prompt("3_analysis",user_message=user_message,action=action,tool_output=tool_output)
    response=requests.post(
        OLLAMA_URL,
        json={
            "model":MODEL,
            "messages":[{"role":"system","content":prompt}],
            "stream":True
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
            decision=await asyncio.to_thread(select_tool,user_message)
        except Exception as e:
            yield "data: "+json.dumps({
                "type":"status",
                "text":f"Bei der Verarbeitung deiner Anfrage ist ein Fehler aufgetreten: {e}"
            },ensure_ascii=False)+"\n\n"
            return

        action=decision["action"]
        status_message=decision["status_message"]

        if action=="none":
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

        try:
            progress_message=await asyncio.to_thread(
                generate_progress_message,
                user_message,
                action
            )
        except Exception:
            progress_message="Bei der Erstellung der Fortschrittsmeldung ist ein Fehler aufgetreten."

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
            "text":"Die Operation wurde erfolgreich ausgeführt. Ich analysiere jetzt die Ergebnisse."
        },ensure_ascii=False)+"\n\n"
        await asyncio.sleep(0.1)

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