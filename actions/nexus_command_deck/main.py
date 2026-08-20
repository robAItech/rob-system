import json
import asyncio
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from actions.nexus_command_deck.schemas import OrchestratorRequest
from actions.nexus_command_deck.nexus_command_deck import MultiLLMOrchestrator

app = FastAPI(title="Rob AI Studio - NEXUS Command Deck")
orchestrator = MultiLLMOrchestrator()

NEXUS_HTML = """
<!DOCTYPE html>
<html lang="sl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NEXUS | Command Deck</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
        body { font-family: 'JetBrains Mono', monospace; background-color: #050505; color: #39ff14; }
        .neon-border { border: 1px solid #39ff14; box-shadow: 0 0 10px rgba(57, 255, 20, 0.3); }
        .neon-text { text-shadow: 0 0 5px rgba(57, 255, 20, 0.5); }
        .neon-cyan { color: #00ffff; text-shadow: 0 0 5px rgba(0, 255, 255, 0.5); }
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #0a0a0a; }
        ::-webkit-scrollbar-thumb { background: #39ff14; }
    </style>
</head>
<body class="h-screen w-screen flex flex-col p-4 overflow-hidden">
    <header class="flex justify-between items-center mb-4 border-b border-[#39ff14] pb-2">
        <h1 class="text-2xl font-bold neon-text tracking-widest">NEXUS // COMMAND DECK</h1>
        <div id="status" class="text-sm neon-cyan">WS: CONNECTING...</div>
    </header>
    <main id="terminal-output" class="flex-grow overflow-y-auto mb-4 neon-border p-4 bg-[#0a0a0a] flex flex-col gap-2 whitespace-pre-wrap font-mono text-sm">
        <div class="text-[#00ffff]">> Sistemski boot zaključen. Rob AI Studio pripravljen.</div>
    </main>
    <footer class="flex gap-2">
        <input type="text" id="cli-input" class="flex-grow bg-[#0a0a0a] neon-border p-2 outline-none text-[#39ff14]" placeholder="> Vnesite direktivo (npr. ./rob review)..." autocomplete="off" autofocus>
    </footer>

    <script>
        const output = document.getElementById('terminal-output');
        const input = document.getElementById('cli-input');
        const status = document.getElementById('status');
        let ws;

        function appendLog(text, isUser = false, meta = null) {
            if (!isUser && text.trim() === '') return;
            const div = document.createElement('div');
            if (isUser) {
                div.innerHTML = `<span class="text-white">USR ></span> ${text}`;
            } else if (meta && meta.provider === "TERMINAL") {
                // Surov terminalski izpis (brez prefixa)
                div.innerHTML = `<span class="text-gray-300">${text}</span>`;
            } else {
                div.innerHTML = `<span class="neon-cyan">SYS ></span> ${text}`;
            }
            output.appendChild(div);
            output.scrollTop = output.scrollHeight;
        }

        function connectWebSocket() {
            ws = new WebSocket(`ws://${window.location.host}/ws/nexus`);
            ws.onopen = () => { 
                status.textContent = "WS: SECURE_LINK_ACTIVE"; 
                status.className = "text-sm neon-cyan";
            };
            ws.onclose = () => { 
                status.textContent = "WS: LINK_SEVERED_RECONNECTING..."; 
                status.className = "text-sm text-yellow-500";
                setTimeout(connectWebSocket, 2000);
            };
            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    appendLog(data.content, false, data);
                } catch {
                    appendLog(event.data, false);
                }
            };
        }
        connectWebSocket();

        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && input.value.trim() !== '') {
                if(ws.readyState === WebSocket.OPEN) {
                    const text = input.value;
                    appendLog(text, true);
                    ws.send(JSON.stringify({ content: text, content_type: 'text' }));
                    input.value = '';
                } else {
                    appendLog("SYS_ERROR: Povezava prekinjena...", false);
                }
            }
        });
    </script>
</body>
</html>
"""

@app.get("/")
async def get_command_deck():
    return HTMLResponse(NEXUS_HTML)

@app.websocket("/ws/nexus")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_process = None
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                req = OrchestratorRequest(**payload)
                command = req.content.strip()
                
                if command.startswith("./rob ") or command.startswith("python3 "):
                    await websocket.send_text(json.dumps({"content": f"🚀 [SYS_EXEC] Zaganjam proces: {command}", "provider": "SYS"}))
                    
                    # NASILNO IZKLOPI PYTHON BUFFERING! TO REŠI PROBLEM S TIŠINO.
                    env = os.environ.copy()
                    env["PYTHONUNBUFFERED"] = "1"
                    env["PYTHONIOENCODING"] = "utf-8"
                    
                    active_process = await asyncio.create_subprocess_shell(
                        command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,
                        cwd="/mnt/c/Rob AI Studio",
                        env=env
                    )
                    
                    # ASINHRONO BRANJE, DA NE BLOKIRAMO WEBSOCKET ZANKE
                    async def stream_output(proc, ws):
                        while True:
                            line = await proc.stdout.readline()
                            if not line:
                                break
                            text_line = line.decode('utf-8', errors='replace').rstrip()
                            if text_line:
                                await ws.send_text(json.dumps({"content": text_line, "provider": "TERMINAL"}))
                        
                        await proc.wait()
                        await ws.send_text(json.dumps({"content": f"✅ [SYS_DONE] Ukaz zaključen (Izhod: {proc.returncode})", "provider": "SYS"}))
                        
                    asyncio.create_task(stream_output(active_process, websocket))
                    
                else:
                    await websocket.send_text(json.dumps({"content": "[...] Obdelujem...", "provider": "SYS"}))
                    response = await orchestrator.process(req)
                    await websocket.send_text(response.model_dump_json())
                    
            except Exception as e:
                await websocket.send_text(json.dumps({"content": f"SYS_ERROR: {str(e)}", "provider": "SYS"}))
                
    except WebSocketDisconnect:
        # Če zaprete brskalnik, v ozadju varno ugasnemo skripto, da ne porablja LLM ključev
        if active_process and active_process.returncode is None:
            try:
                active_process.terminate()
            except:
                pass
