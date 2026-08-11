import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from actions.enterprise_nexus_command_deck.schemas import OrchestratorRequest
from actions.enterprise_nexus_command_deck.enterprise_nexus_command_deck import MultiLLMOrchestrator

app = FastAPI(title="Rob AI Studio - NEXUS Command Deck")
orchestrator = MultiLLMOrchestrator()

# Deep Tech UI: Pitch black, Neon poudarki, Monospace
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
        /* Scrollbar */
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #0a0a0a; }
        ::-webkit-scrollbar-thumb { background: #39ff14; }
        #dropzone.dragover { background-color: rgba(57, 255, 20, 0.1); border-color: #00ffff; }
    </style>
</head>
<body class="h-screen w-screen flex flex-col p-4 overflow-hidden" id="dropzone">
    
    <!-- HEADER -->
    <header class="flex justify-between items-center mb-4 border-b border-[#39ff14] pb-2">
        <h1 class="text-2xl font-bold neon-text tracking-widest">NEXUS // COMMAND DECK</h1>
        <div id="status" class="text-sm neon-cyan">WS: CONNECTING...</div>
    </header>

    <!-- TERMINAL OUTPUT -->
    <main id="terminal-output" class="flex-grow overflow-y-auto mb-4 neon-border p-4 bg-[#0a0a0a] flex flex-col gap-2">
        <div class="text-[#00ffff]">> Sistemski boot zaključen. Rob AI Studio pripravljen.</div>
        <div class="text-gray-400">> Vnesite ukaz, povlecite datoteko v to okno ali aktivirajte zvočni uplink.</div>
    </main>

    <!-- INPUT AREA -->
    <footer class="flex gap-2">
        <button id="btn-voice" class="neon-border px-4 py-2 hover:bg-[#39ff14] hover:text-black transition-colors font-bold" title="Voice Uplink">
            🎤 [MIC_OFF]
        </button>
        <input type="text" id="cli-input" class="flex-grow bg-[#0a0a0a] neon-border p-2 outline-none text-[#39ff14] placeholder-gray-600 focus:border-[#00ffff] focus:shadow-[0_0_10px_rgba(0,255,255,0.3)]" placeholder="> Vnesite direktivo tukaj..." autocomplete="off">
    </footer>

    <script>
        const ws = new WebSocket(`ws://${window.location.host}/ws/nexus`);
        const output = document.getElementById('terminal-output');
        const input = document.getElementById('cli-input');
        const status = document.getElementById('status');
        const btnVoice = document.getElementById('btn-voice');
        const dropzone = document.getElementById('dropzone');

        let mediaRecorder;
        let audioChunks = [];

        function appendLog(text, isUser = false, meta = null) {
            const div = document.createElement('div');
            if (isUser) {
                div.innerHTML = `<span class="text-white">USR ></span> ${text}`;
            } else {
                let metaStr = meta ? `<span class="text-xs text-gray-500 ml-2">[Provider: ${meta.provider} | Latency: ${meta.latency_ms}ms${meta.is_fallback ? ' | FALLBACK' : ''}]</span>` : '';
                div.innerHTML = `<span class="neon-cyan">SYS ></span> ${text} ${metaStr}`;
            }
            output.appendChild(div);
            output.scrollTop = output.scrollHeight;
        }

        ws.onopen = () => { status.textContent = "WS: SECURE_LINK_ACTIVE"; };
        ws.onclose = () => { status.textContent = "WS: LINK_SEVERED"; status.classList.replace('neon-cyan', 'text-red-500'); };
        
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                appendLog(data.content, false, data);
            } catch {
                appendLog(event.data, false);
            }
        };

        // Text Input
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && input.value.trim() !== '') {
                const text = input.value;
                appendLog(text, true);
                ws.send(JSON.stringify({ content: text, content_type: 'text' }));
                input.value = '';
            }
        });

        // Drag & Drop
        dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
        dropzone.addEventListener('dragleave', () => { dropzone.classList.remove('dragover'); });
        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                const file = e.dataTransfer.files[0];
                appendLog(`[Nalaganje binarne datoteke: ${file.name}]`, true);
                ws.send(JSON.stringify({ content: file.name, content_type: 'file' }));
            }
        });

        // Web Audio API
        btnVoice.addEventListener('click', async () => {
            if (!mediaRecorder || mediaRecorder.state === 'inactive') {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    mediaRecorder = new MediaRecorder(stream);
                    mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
                    mediaRecorder.onstop = () => {
                        appendLog(`[Glasovni paket poslan (dolžina: ${audioChunks.length} chunks)]`, true);
                        ws.send(JSON.stringify({ content: "Audio stream data", content_type: 'audio' }));
                        audioChunks = [];
                    };
                    mediaRecorder.start();
                    btnVoice.textContent = '🛑 [RECORDING]';
                    btnVoice.classList.add('bg-red-500', 'text-white', 'border-red-500');
                } catch (err) {
                    appendLog(`[AUDIO ERROR: ${err.message}]`, false);
                }
            } else {
                mediaRecorder.stop();
                btnVoice.textContent = '🎤 [MIC_OFF]';
                btnVoice.classList.remove('bg-red-500', 'text-white', 'border-red-500');
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
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                req = OrchestratorRequest(**payload)
                
                # Simuliramo stream delay
                await websocket.send_text(json.dumps({"content": "[...] Obdelujem poizvedbo...", "provider": "SYS", "latency_ms": 0, "is_fallback": False}))
                
                # Orkestracija (usmerjanje in failover)
                response = await orchestrator.process(req)
                
                # Vrnemo polni rezultat
                await websocket.send_text(response.model_dump_json())
            except Exception as e:
                await websocket.send_text(json.dumps({"content": f"SYS_ERROR: {str(e)}", "provider": "SYS", "latency_ms": 0, "is_fallback": False}))
    except WebSocketDisconnect:
        pass
