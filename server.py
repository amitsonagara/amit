import asyncio
import base64
import json
import secrets
from datetime import datetime
from pathlib import Path

from aiohttp import web, WSMsgType
import psutil

HOST = "0.0.0.0"
PORT = 8000
PASSWORD = "1234"
MAX_USERS = 50
MAX_FILE_MB = 10

UPLOAD_DIR = Path("netchat_uploads")
HISTORY_FILE = Path("netchat_history.json")
UPLOAD_DIR.mkdir(exist_ok=True)

CLIENTS = {}
USERS = {}
HISTORY = []


def current_time():
    return datetime.now().strftime("%H:%M")


def load_history():
    global HISTORY
    try:
        if HISTORY_FILE.exists():
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                HISTORY = data[-300:]
    except Exception:
        HISTORY = []


def save_history():
    try:
        HISTORY_FILE.write_text(
            json.dumps(HISTORY[-300:], ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception:
        pass


def user_list():
    return [{"id": uid, "name": data["name"]} for uid, data in USERS.items()]


async def send_json(ws, data):
    if not ws.closed:
        await ws.send_str(json.dumps(data, ensure_ascii=False))


async def send_to_user(uid, data):
    ws = CLIENTS.get(uid)
    if ws:
        await send_json(ws, data)


async def broadcast(data, skip=None):
    for uid, ws in list(CLIENTS.items()):
        if ws is not skip:
            try:
                await send_json(ws, data)
            except Exception:
                pass


async def monitor_task():
    while True:
        await asyncio.sleep(2)
        net = psutil.net_io_counters()
        await broadcast({
            "type": "stats",
            "cpu": psutil.cpu_percent(),
            "ram": psutil.virtual_memory().percent,
            "sent": net.bytes_sent,
            "recv": net.bytes_recv,
            "users": len(USERS),
            "max": MAX_USERS
        })


HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>NetChat Pro</title>
<style>
*{box-sizing:border-box}
:root{--accent:#20d5aa;--bg1:#07121f;--bg2:#172d4a}
body{margin:0;height:100vh;font-family:Arial,sans-serif;color:#eefaff;background:linear-gradient(135deg,var(--bg1),var(--bg2),#25193d);background-size:300% 300%;animation:bg 12s ease infinite}
@keyframes bg{50%{background-position:100% 50%}}
.app{width:96%;height:94vh;margin:3vh auto;display:grid;grid-template-columns:220px 1fr 190px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.15);border-radius:22px;overflow:hidden;backdrop-filter:blur(18px)}
aside{padding:16px;background:rgba(0,0,0,.28)}
.main{display:flex;flex-direction:column;min-width:0}
.head{padding:15px 18px;border-bottom:1px solid rgba(255,255,255,.1);display:flex;justify-content:space-between;gap:10px}
.chat{flex:1;overflow:auto;padding:18px}
.msg{max-width:72%;padding:10px 13px;margin:8px 0;border-radius:15px;background:rgba(255,255,255,.08);word-wrap:break-word}
.mine{margin-left:auto;background:rgba(32,213,170,.25)}
.name{font-size:12px;color:var(--accent);font-weight:bold;margin-bottom:4px}
.time{font-size:10px;color:#9ab;float:right;margin:6px 0 0 10px}
.users{margin-top:12px}
.user{padding:10px;border-radius:10px;cursor:pointer}
.user:hover,.active{background:rgba(32,213,170,.18)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#4dff9b;margin-right:6px}
.composer{padding:12px;border-top:1px solid rgba(255,255,255,.1)}
.input,.search{border:1px solid rgba(255,255,255,.15);background:rgba(255,255,255,.07);color:white;border-radius:12px;padding:11px;outline:none}
.input{width:100%}
.row{display:flex;gap:7px;margin-top:7px}
.row .input{flex:1}
button{border:0;border-radius:12px;padding:10px 13px;background:var(--accent);color:#07121f;font-weight:bold;cursor:pointer}
.login{position:fixed;inset:0;background:rgba(2,7,17,.96);display:flex;align-items:center;justify-content:center;z-index:10}
.box{width:320px;padding:25px;border-radius:20px;background:#102032;border:1px solid rgba(255,255,255,.12)}
.box .input{margin:10px 0}
.preview{max-width:240px;max-height:200px;border-radius:12px;display:block;margin-top:7px}
.file{display:block;color:#a9efff;margin-top:7px}
.bar{height:6px;background:rgba(255,255,255,.1);border-radius:9px;margin-top:5px}
.fill{height:100%;background:var(--accent);width:0%;border-radius:9px}
.small{font-size:12px;color:#a9bdc9}
.theme{display:flex;gap:5px;flex-wrap:wrap;margin-top:8px}
.settings-btn{width:100%;margin-top:7px;background:rgba(255,255,255,.10);color:#eefaff;border:1px solid rgba(255,255,255,.12)}
.settings-btn:hover{background:rgba(32,213,170,.22)}
.danger-btn{background:rgba(255,80,100,.16);color:#ffd8dd}
.profile-card{display:flex;align-items:center;gap:10px;padding:10px;border-radius:14px;background:rgba(255,255,255,.07);margin-bottom:8px}
.profile-avatar{width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:rgba(32,213,170,.20)}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.70);display:none;align-items:center;justify-content:center;z-index:20;padding:18px}
.modal-card{width:min(420px,95vw);background:#102032;border:1px solid rgba(255,255,255,.15);border-radius:20px;padding:20px;box-shadow:0 20px 70px rgba(0,0,0,.45)}
.modal-row{display:flex;gap:8px;margin-top:10px}
.modal-row button{flex:1}
.close-btn{background:rgba(255,255,255,.10);color:#fff}
#bgLayer{position:fixed;inset:0;background-position:center;background-size:cover;background-repeat:no-repeat;opacity:.30;pointer-events:none;z-index:-1}

.theme button{font-size:11px;padding:7px}
@media(max-width:850px){
 .app{width:100%;height:100vh;margin:0;border-radius:0;grid-template-columns:1fr}
 aside{display:none}.msg{max-width:86%}
 .composer{padding-bottom:calc(12px + env(safe-area-inset-bottom))}
}
</style>
</head>
<body>

<div id="login" class="login">
 <div class="box">
  <h2>🔐 NetChat Pro</h2>
  <div class="small">Private LAN chat server</div>
  <input id="pass" class="input" type="password" placeholder="Server password">
  <input id="loginName" class="input" placeholder="Your name">
  <button onclick="login()">Connect</button>
  <p id="err"></p>
 </div>
</div>


<div id="bgLayer"></div>

<div id="settingsModal" class="modal">
 <div class="modal-card">
  <h2>⚙️ Settings</h2>

  <label class="small">Profile name</label>
  <input id="settingsName" class="input" placeholder="Your name">

  <label class="small">Server password</label>
  <input id="settingsPassword" class="input" type="password" value="1234" readonly>

  <div class="modal-row">
   <button onclick="saveProfile()">💾 Save Name</button>
   <button class="close-btn" onclick="closeSettings()">Close</button>
  </div>

  <hr>

  <button class="settings-btn danger-btn" onclick="clearChat()">🗑️ Clear Chat</button>
  <button class="settings-btn" onclick="removeBackground()">↩️ Remove Background</button>
 </div>
</div>

<div class="app">
 <aside>
  <h2>💬 Chats</h2>
  <input id="search" class="search" placeholder="Search users" oninput="filterUsers()">
  <div id="users" class="users"></div>
 </aside>

 <section class="main">
  <header class="head">
   <div>
    <b>NetChat Pro</b>
    <div id="status" class="small">Disconnected</div>
   </div>
   <span id="island">● OFFLINE</span>
  </header>

  <div id="chat" class="chat">
   <p style="text-align:center;opacity:.7">✨ Welcome to NetChat Pro</p>
  </div>

  <div id="typing" style="height:20px;padding:0 18px;color:var(--accent);font-size:12px"></div>

  <div class="composer">
   <div class="row">
    <button onclick="emoji('😀')">😀</button>
    <button onclick="emoji('❤️')">❤️</button>
    <button onclick="pickFile()">📎</button>
    <input id="input" class="input" placeholder="Type a message" onkeydown="key(event)" oninput="typing()">
    <button onclick="send()">➤</button>
   </div>
   <input id="file" type="file" hidden onchange="sendFile()">
  </div>
 </section>

 <aside>
  <h3>⚙️ Settings</h3>

  <div class="profile-card">
   <div class="profile-avatar">👤</div>
   <div>
    <b id="profileName">Guest</b>
    <div class="small">Connected profile</div>
   </div>
  </div>

  <button class="settings-btn" onclick="openSettings()">⚙️ Open Settings</button>
  <button class="settings-btn danger-btn" onclick="clearChat()">🗑️ Clear Chat</button>

  <hr>

  <b>🎨 Themes</b>
  <div class="theme">
   <button onclick="theme('#07121f','#172d4a','#20d5aa')">Ocean</button>
   <button onclick="theme('#180b20','#43205a','#d66cff')">Purple</button>
   <button onclick="theme('#15100a','#49351b','#ffb02e')">Gold</button>
   <button onclick="theme('#071a14','#123d2c','#55e39a')">Emerald</button>
   <button onclick="theme('#160d0d','#4b2020','#ff6b6b')">Ruby</button>
   <button onclick="theme('#08111f','#16385c','#55aaff')">Sky</button>
   <button onclick="theme('#17100a','#4b2e12','#ff9d3d')">Sunset</button>
   <button onclick="theme('#0b0b0b','#252525','#eeeeee')">Mono</button>
  </div>

  <hr>

  <b>🖼️ Background</b>
  <div class="small">Choose a photo from this device.</div>
  <input id="bgFile" type="file" accept="image/*" hidden onchange="setBackground(event)">
  <button class="settings-btn" onclick="document.getElementById('bgFile').click()">🖼️ Choose Photo</button>
  <button class="settings-btn" onclick="removeBackground()">↩️ Remove Photo</button>

  <hr>

  <div class="small">
   Online users: <b id="uc">0 / 50</b>
  </div>
 </aside>
</div>

<script>
let ws=null, me="", selected=null, timer=null, reconnectTimer=null;

function login(){
  const p=document.getElementById("pass").value.trim();
  const n=document.getElementById("loginName").value.trim() || "Guest";
  if(!p){document.getElementById("err").textContent="Enter password";return;}
  localStorage.setItem("netpass",p);
  localStorage.setItem("netname",n);
  document.getElementById("profileName").textContent=n;
  connect(p,n);
}

function connect(p,n){
  const proto=location.protocol==="https:"?"wss":"ws";
  ws=new WebSocket(proto+"://"+location.host+"/ws?password="+encodeURIComponent(p)+"&name="+encodeURIComponent(n));

  ws.onopen=()=>{
    document.getElementById("login").style.display="none";
    document.getElementById("status").textContent="Live • LAN connected";
    document.getElementById("island").textContent="● ONLINE";
  };

  ws.onmessage=e=>{
    try{handle(JSON.parse(e.data));}catch(err){}
  };

  ws.onclose=()=>{
    document.getElementById("status").textContent="Reconnecting...";
    document.getElementById("island").textContent="● OFFLINE";
    clearTimeout(reconnectTimer);
    reconnectTimer=setTimeout(()=>{
      connect(localStorage.getItem("netpass")||"",localStorage.getItem("netname")||"Guest");
    },2000);
  };

  ws.onerror=()=>{
    document.getElementById("err").textContent="Wrong password or server unavailable";
  };
}

function handle(d){
  if(d.type==="init"){
    me=d.id;
    renderUsers(d.users);
    d.history.forEach(addMessage);
  }
  if(d.type==="users") renderUsers(d.users);
  if(d.type==="message") addMessage(d);
  if(d.type==="file") addFile(d);
  if(d.type==="typing"){
    document.getElementById("typing").textContent=d.name+" is typing...";
  }
  if(d.type==="typingOff"){
    document.getElementById("typing").textContent="";
  }
  if(d.type==="system") addSystem(d.text);
  if(d.type==="stats"){
    document.getElementById("cpu").textContent=Math.round(d.cpu)+"%";
    document.getElementById("ram").textContent=Math.round(d.ram)+"%";
    document.getElementById("uc").textContent=d.users+" / "+d.max;
    document.getElementById("cb").style.width=Math.min(100,d.cpu)+"%";
    document.getElementById("rb").style.width=Math.min(100,d.ram)+"%";
    document.getElementById("net").textContent=Math.round(d.recv/1048576)+" MB ↓ / "+Math.round(d.sent/1048576)+" MB ↑";
  }
  if(d.type==="error") alert(d.text);
}

function renderUsers(list){
  const box=document.getElementById("users");
  box.innerHTML="";
  list.forEach(u=>{
    if(u.id===me)return;
    const x=document.createElement("div");
    x.className="user";
    x.dataset.name=u.name;
    x.innerHTML='<span class="dot"></span>'+safe(u.name);
    x.onclick=()=>{
      selected=u.id;
      document.querySelectorAll(".user").forEach(a=>a.classList.remove("active"));
      x.classList.add("active");
      document.getElementById("status").textContent="Private chat • "+u.name;
    };
    box.appendChild(x);
  });
}

function addMessage(m){
  if(m.to && m.to!==me && m.from!==me)return;
  const x=document.createElement("div");
  x.className="msg "+(m.from===me?"mine":"");
  x.innerHTML='<div class="name">'+safe(m.name)+'</div>'+safe(m.text)+' <span class="time">'+safe(m.time)+'</span>';
  document.getElementById("chat").appendChild(x);
  scrollChat();
}

function addFile(m){
  if(m.to && m.to!==me && m.from!==me)return;
  const x=document.createElement("div");
  x.className="msg "+(m.from===me?"mine":"");
  let media="";
  if((m.mime||"").startsWith("image/")) media='<img class="preview" src="'+m.url+'" alt="image">';
  x.innerHTML='<div class="name">'+safe(m.name)+'</div>'+media+'<a class="file" href="'+m.url+'" target="_blank">📎 '+safe(m.filename)+'</a>';
  document.getElementById("chat").appendChild(x);
  scrollChat();
}

function addSystem(t){
  const x=document.createElement("div");
  x.style.cssText="text-align:center;color:#9ab;font-size:12px;margin:8px";
  x.textContent=t;
  document.getElementById("chat").appendChild(x);
  scrollChat();
}

function send(){
  const t=document.getElementById("input").value.trim();
  if(!t||!ws||ws.readyState!==1)return;
  ws.send(JSON.stringify({type:"message",text:t,to:selected}));
  document.getElementById("input").value="";
  typingOff();
}

function key(e){
  if(e.key==="Enter"){e.preventDefault();send();}
}

function emoji(s){
  const i=document.getElementById("input");
  i.value+=s;
  i.focus();
}

function pickFile(){document.getElementById("file").click();}

function sendFile(){
  const f=document.getElementById("file").files[0];
  if(!f||!ws||ws.readyState!==1)return;
  if(f.size>10*1024*1024){alert("Maximum file size is 10 MB");return;}
  const r=new FileReader();
  r.onload=()=>ws.send(JSON.stringify({
    type:"file",name:f.name,mime:f.type||"application/octet-stream",
    data:r.result,to:selected
  }));
  r.readAsDataURL(f);
}

function typing(){
  if(!ws||ws.readyState!==1)return;
  ws.send(JSON.stringify({type:"typing"}));
  clearTimeout(timer);
  timer=setTimeout(typingOff,1000);
}

function typingOff(){
  if(ws&&ws.readyState===1)ws.send(JSON.stringify({type:"typingOff"}));
  clearTimeout(timer);
}

function filterUsers(){
  const q=document.getElementById("search").value.toLowerCase();
  document.querySelectorAll(".user").forEach(x=>{
    x.style.display=x.dataset.name.toLowerCase().includes(q)?"block":"none";
  });
}

function scrollChat(){
  const c=document.getElementById("chat");
  c.scrollTop=c.scrollHeight;
}

function safe(t){
  const d=document.createElement("div");
  d.textContent=t==null?"":String(t);
  return d.innerHTML;
}


function openSettings(){
  document.getElementById("settingsName").value =
    localStorage.getItem("netname") || "Guest";
  document.getElementById("settingsModal").style.display="flex";
}

function closeSettings(){
  document.getElementById("settingsModal").style.display="none";
}

function saveProfile(){
  const n=document.getElementById("settingsName").value.trim() || "Guest";
  localStorage.setItem("netname",n);
  document.getElementById("profileName").textContent=n;

  if(ws && ws.readyState===1){
    ws.send(JSON.stringify({type:"name",name:n}));
  }

  closeSettings();
}

function clearChat(){
  if(!confirm("Clear all chat messages from this screen?")) return;
  const c=document.getElementById("chat");
  c.innerHTML='<p style="text-align:center;opacity:.7">✨ Chat cleared</p>';
}

function setBackground(event){
  const file=event.target.files && event.target.files[0];
  if(!file) return;
  if(!file.type.startsWith("image/")){
    alert("Please choose an image file.");
    return;
  }

  const reader=new FileReader();
  reader.onload=()=>{
    try{
      localStorage.setItem("netchatBackground",reader.result);
      applyBackground(reader.result);
    }catch(e){
      alert("This photo is too large for browser storage. Please choose a smaller image.");
    }
  };
  reader.readAsDataURL(file);
}

function applyBackground(data){
  const layer=document.getElementById("bgLayer");
  if(data){
    layer.style.backgroundImage='url("'+data+'")';
    document.body.style.backgroundImage="linear-gradient(rgba(4,10,20,.58),rgba(4,10,20,.58))";
  }else{
    layer.style.backgroundImage="none";
    document.body.style.backgroundImage="";
  }
}

function removeBackground(){
  localStorage.removeItem("netchatBackground");
  applyBackground("");
  const f=document.getElementById("bgFile");
  if(f) f.value="";
}

function theme(a,b,c){
  document.documentElement.style.setProperty("--bg1",a);
  document.documentElement.style.setProperty("--bg2",b);
  document.documentElement.style.setProperty("--accent",c);
  localStorage.setItem("netchatTheme",JSON.stringify({a:a,b:b,c:c}));
}

const savedPass=localStorage.getItem("netpass");
const savedName=localStorage.getItem("netname") || "Guest";
document.getElementById("profileName").textContent=savedName;

const savedTheme=localStorage.getItem("netchatTheme");
if(savedTheme){
  try{
    const t=JSON.parse(savedTheme);
    theme(t.a,t.b,t.c);
  }catch(e){}
}

const savedBackground=localStorage.getItem("netchatBackground");
if(savedBackground) applyBackground(savedBackground);

if(savedPass){
  document.getElementById("pass").value=savedPass;
  document.getElementById("loginName").value=savedName;
  connect(savedPass,savedName);
}else{
  document.getElementById("pass").focus();
}
</script>
</body>
</html>"""


async def index(request):
    return web.Response(text=HTML, content_type="text/html")


async def upload_file(request):
    name = Path(request.match_info["name"]).name
    path = UPLOAD_DIR / name
    if not path.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(path)


async def websocket_handler(request):
    password = request.query.get("password", "")
    name = request.query.get("name", "Guest").strip()[:30] or "Guest"

    if password != PASSWORD:
        return web.Response(status=401, text="Wrong password")

    if len(USERS) >= MAX_USERS:
        return web.Response(status=503, text="Server is full")

    ws = web.WebSocketResponse(
        heartbeat=20,
        max_msg_size=MAX_FILE_MB * 1024 * 1024 + 2 * 1024 * 1024
    )
    await ws.prepare(request)

    uid = secrets.token_hex(6)
    USERS[uid] = {"name": name}
    CLIENTS[uid] = ws

    await send_json(ws, {
        "type": "init",
        "id": uid,
        "users": user_list(),
        "history": HISTORY[-200:]
    })
    await broadcast({"type": "users", "users": user_list()})

    try:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue

            try:
                data = json.loads(msg.data)
            except Exception:
                continue

            kind = data.get("type")

            if kind == "name":
                new_name = str(data.get("name", "")).strip()[:30]
                if new_name:
                    USERS[uid]["name"] = new_name
                    await broadcast({"type": "users", "users": user_list()})

            elif kind == "typing":
                await broadcast({
                    "type": "typing",
                    "id": uid,
                    "name": USERS[uid]["name"]
                }, skip=ws)

            elif kind == "typingOff":
                await broadcast({"type": "typingOff", "id": uid}, skip=ws)

            elif kind == "message":
                text_value = str(data.get("text", "")).strip()[:2000]
                if not text_value:
                    continue

                target = data.get("to") or None
                message = {
                    "type": "message",
                    "id": secrets.token_hex(8),
                    "from": uid,
                    "name": USERS[uid]["name"],
                    "to": target,
                    "text": text_value,
                    "time": current_time()
                }

                if target and target in CLIENTS and target != uid:
                    await send_to_user(target, message)
                    await send_json(ws, message)
                else:
                    HISTORY.append(message)
                    save_history()
                    await broadcast(message)

            elif kind == "file":
                encoded = str(data.get("data", ""))
                if "," not in encoded:
                    await send_json(ws, {"type": "error", "text": "Invalid file"})
                    continue

                try:
                    raw = base64.b64decode(encoded.split(",", 1)[1], validate=True)
                except Exception:
                    await send_json(ws, {"type": "error", "text": "Invalid file data"})
                    continue

                if len(raw) > MAX_FILE_MB * 1024 * 1024:
                    await send_json(ws, {"type": "error", "text": "Maximum file size is 10 MB"})
                    continue

                filename = Path(str(data.get("name", "file"))).name[:100]
                stored = secrets.token_hex(8) + "_" + filename
                (UPLOAD_DIR / stored).write_bytes(raw)

                message = {
                    "type": "file",
                    "id": secrets.token_hex(8),
                    "from": uid,
                    "name": USERS[uid]["name"],
                    "to": data.get("to") or None,
                    "filename": filename,
                    "mime": str(data.get("mime", "application/octet-stream")),
                    "url": "/uploads/" + stored,
                    "time": current_time()
                }

                target = message["to"]
                if target and target in CLIENTS and target != uid:
                    await send_to_user(target, message)
                    await send_json(ws, message)
                else:
                    await broadcast(message)

    finally:
        old_name = USERS.get(uid, {}).get("name", "A user")
        USERS.pop(uid, None)
        CLIENTS.pop(uid, None)
        await broadcast({"type": "users", "users": user_list()})
        await broadcast({"type": "system", "text": old_name + " left the chat."})

    return ws


async def on_startup(app):
    load_history()
    app["monitor_task"] = asyncio.create_task(monitor_task())


async def on_cleanup(app):
    task = app.get("monitor_task")
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def main():
    app = web.Application(
        client_max_size=MAX_FILE_MB * 1024 * 1024 + 2 * 1024 * 1024
    )
    app.router.add_get("/", index)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_get("/uploads/{name}", upload_file)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    print("=" * 55)
    print("NETCHAT PRO SERVER")
    print("=" * 55)
    print("Password : 1234")
    print("Local    : http://localhost:8000")
    print("LAN      : http://YOUR-PC-IP:8000")
    print("Users    : 50")
    print("File max : 10 MB")
    print("=" * 55)

    web.run_app(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
