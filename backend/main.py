from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import uuid
import json

# 新增导入
from fastapi.responses import FileResponse
import os

app = FastAPI()

# 允许跨域，方便前端本地开发
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 用于存储所有连接的 websocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        user_id = str(uuid.uuid4())
        self.active_connections[user_id] = websocket
        return user_id

    def disconnect(self, user_id: str):
        self.active_connections.pop(user_id, None)

    async def broadcast(self, message: dict):
        disconnected = []
        for user_id, connection in self.active_connections.items():
            try:
                await connection.send_text(json.dumps(message))
            except Exception:
                disconnected.append(user_id)
        for user_id in disconnected:
            self.disconnect(user_id)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    import sys
    user_id = await manager.connect(websocket)
    print(f"[WS] connect: {user_id}", file=sys.stderr)
    try:
        while True:
            data = await websocket.receive_text()
            print(f"[WS] recv from {user_id}: {data}", file=sys.stderr)
            message = json.loads(data)
            await manager.broadcast(message)
            print(f"[WS] broadcast: {message}", file=sys.stderr)
    except WebSocketDisconnect:
        print(f"[WS] disconnect: {user_id}", file=sys.stderr)
        manager.disconnect(user_id)

# 静态文件服务（图片/视频上传后可访问）
app.mount("/static", StaticFiles(directory="./backend/static"), name="static")

# 文件上传接口（图片/视频）
from fastapi import HTTPException
import threading
import time

MAX_FILE_SIZE = 30 * 1024 * 1024  # 30MB
CLEAN_INTERVAL = 1800  # 30分钟
KEEP_SECONDS = 3600  # 只保留1小时内的文件

# 自动清理 static 目录

def clean_static_dir():
    while True:
        now = time.time()
        static_dir = "backend/static"
        for fname in os.listdir(static_dir):
            fpath = os.path.join(static_dir, fname)
            if os.path.isfile(fpath):
                if now - os.path.getmtime(fpath) > KEEP_SECONDS:
                    try:
                        os.remove(fpath)
                        print(f"[CLEAN] removed {fpath}")
                    except Exception as e:
                        print(f"[CLEAN ERROR] {e}")
        time.sleep(CLEAN_INTERVAL)

threading.Thread(target=clean_static_dir, daemon=True).start()

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    import sys
    ext = file.filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    save_path = f"backend/static/{filename}"
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件过大，最大30MB")
    try:
        print(f"[UPLOAD] filename={file.filename}, save_path={save_path}", file=sys.stderr)
        with open(save_path, "wb") as f:
            f.write(content)
        print(f"[UPLOAD] saved successfully", file=sys.stderr)
        return {"url": f"/static/{filename}"}
    except Exception as e:
        print(f"[UPLOAD ERROR] {e}", file=sys.stderr)
        return {"error": str(e)}

# 新增：主页直接返回聊天室页面
@app.get("/")
def get_index():
    frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    return FileResponse(frontend_path)

if __name__ == "__main__":
    import os
    os.makedirs("static", exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=8000)
