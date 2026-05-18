import time
from collections import deque
from fastapi.responses import HTMLResponse
import uvicorn
import logging
import pickle
import queue
import threading
import asyncio
from typing import Optional, Dict, Any

from fastapi import FastAPI, File, UploadFile, Header, HTTPException, Response, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from ml.config import Config

# Set up logging with DEBUG level
logger = logging.getLogger("rl_server")
logging.basicConfig(level=logging.INFO)


DEFAULT_PASSWORD = Config.AUTH_CODE
QUEUE_MAXSIZE = Config.QUEUE_MAX_SIZE


class StatusResponse(BaseModel):
    status: str
    rl_queue_size: int
    sl_queue_size: int
    learner_connected: bool
    actor_count: int
    weights_version: int
    rps: float
    avg_packet_size: float
    latest_weights_size: int


def verify_password(x_password: str = Header(..., alias="X-Password")):
    if x_password != DEFAULT_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


class RLServerState:
    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        with self._lock:
            self.rl_queue: queue.Queue = queue.Queue(maxsize=QUEUE_MAXSIZE)
            self.sl_queue: queue.Queue = queue.Queue(maxsize=QUEUE_MAXSIZE)
            self._latest_params: Optional[bytes] = None
            self.weights_version = 0
            self.learner_connected = False
            self.actor_counter = 0
            self.metrics = {
                "frame": 0,
                "loss": 0.0,
                "grad_norm": 0.0,
                "sl_loss": 0.0,
                "sl_grad_norm": 0.0,
                "replay_buffer_size": 0,
                "reservoir_size": 0
            }
            # Performance metrics
            self.request_times = deque(maxlen=1000)
            self.total_packet_size = 0
            self.packet_count = 0
            self.latest_weights_size = 0
            logger.info("Server state reset.")

    def register_actor(self) -> int:
        with self._lock:
            actor_id = self.actor_counter
            self.actor_counter += 1
            return actor_id

    def record_request(self):
        with self._lock:
            self.request_times.append(time.time())

    def record_packet(self, size: int):
        with self._lock:
            self.total_packet_size += size
            self.packet_count += 1

    def push_rl(self, item: Any) -> None:
        if self.rl_queue.full():
            logger.warning("RL queue full -> dropping batch")
            return
        self.rl_queue.put(item)

    def push_sl(self, item: Any) -> None:
        if self.sl_queue.full():
            logger.warning("SL queue full -> dropping transitions")
            return
        self.sl_queue.put(item)

    def pop_rl(self) -> Optional[Any]:
        if self.rl_queue.empty():
            return None
        return self.rl_queue.get()

    def pop_sl(self) -> Optional[Any]:
        if self.sl_queue.empty():
            return None
        return self.sl_queue.get()

    def set_params(self, data: bytes) -> None:
        with self._lock:
            self._latest_params = data
            self.latest_weights_size = len(data)
            self.weights_version += 1

    def get_params(self) -> Optional[bytes]:
        with self._lock:
            return self._latest_params

    def update_metrics(self, metrics: dict):
        with self._lock:
            self.metrics.update(metrics)

    def learner_disconnect(self) -> None:
        with self._lock:
            self.learner_connected = False
            logger.info(
                "Learner disconnected. State preserved for reconnection.")

    def status(self) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            # Calculate RPS over last 10 seconds
            recent_requests = [t for t in self.request_times if now - t <= 10]
            rps = len(recent_requests) / 10.0 if recent_requests else 0.0

            avg_packet_size = self.total_packet_size / \
                self.packet_count if self.packet_count > 0 else 0

            return {
                "rl_queue_size": self.rl_queue.qsize(),
                "sl_queue_size": self.sl_queue.qsize(),
                "learner_connected": self.learner_connected,
                "actor_count": self.actor_counter,
                "weights_version": self.weights_version,
                "rps": rps,
                "avg_packet_size": avg_packet_size,
                "latest_weights_size": self.latest_weights_size
            }


class RLService:
    def __init__(self, state: RLServerState):
        self.state = state

    async def ingest_rl_batch(self, file: UploadFile):
        try:
            raw = await file.read()
            self.state.record_packet(len(raw))
            data = pickle.loads(raw)
            self.state.push_rl(data)
            logger.debug(f"Ingested RL batch. Queue size: {
                         self.state.rl_queue.qsize()}")
        except Exception as e:
            logger.exception(f"Failed RL ingestion: {e}")

    async def ingest_sl_transitions(self, file: UploadFile):
        try:
            raw = await file.read()
            self.state.record_packet(len(raw))
            data = pickle.loads(raw)
            self.state.push_sl(data)
            logger.debug(f"Ingested SL transitions. Queue size: {
                         self.state.sl_queue.qsize()}")
        except Exception as e:
            logger.exception(f"Failed SL ingestion: {e}")

    def fetch_training_data(self) -> Optional[bytes]:
        data = {}

        rl = self.state.pop_rl()
        sl = self.state.pop_sl()

        if rl is not None:
            data["rl_batch"] = rl

        if sl is not None:
            data["sl_transitions"] = sl

        if not data:
            return None

        return pickle.dumps(data)

    def set_parameters(self, raw: bytes):
        self.state.set_params(raw)

    def get_parameters(self) -> Optional[bytes]:
        return self.state.get_params()


app = FastAPI()
state = RLServerState()
service = RLService(state)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    s = state.status()
    m = state.metrics
    return f"""
    <html>
        <head>
            <title>RL Hub Status</title>
            <meta http-equiv="refresh" content="3">
            <style>
                body {{ font-family: monospace; background: #111; color: #eee; padding: 20px; }}
                h3 {{ margin: 10px 0; }}
                .green {{ color: #0f0; }}
                .red {{ color: #f00; }}
            </style>
        </head>
        <body>
            <h1>RL Distributed Hub</h1>
            <h3>Learner Connected: <span class="{"green" if s['learner_connected'] else "red"}">{s['learner_connected']}</span></h3>
            <h3>Active Actors: {s['actor_count']}</h3>
            <h3>Weights Version: {s['weights_version']}</h3>
            <h3>Latest Weights Size: {s['latest_weights_size'] / 1024 / 1024:.2f} MB</h3>
            <hr>
            <h3>--- Performance Metrics ---</h3>
            <h3>Requests Per Second: {s['rps']:.2f}</h3>
            <h3>Avg Packet Size: {s['avg_packet_size'] / 1024:.2f} KB</h3>
            <hr>
            <h3>--- Training Metrics ---</h3>
            <h3>Iteration: {m['frame']}</h3>
            <h3>RL Loss: {m['loss']:.6f} (norm: {m['grad_norm']:.4f})</h3>
            <h3>SL Loss: {m['sl_loss']:.6f} (norm: {m['sl_grad_norm']:.4f})</h3>
            <h3>Replay Buffer: {m['replay_buffer_size']}</h3>
            <h3>Reservoir: {m['reservoir_size']}</h3>
            <hr>
            <h3>--- Queue Stats ---</h3>
            <h3>RL Batch Queue: {s['rl_queue_size']}</h3>
            <h3>SL Transition Queue: {s['sl_queue_size']}</h3>
        </body>
    </html>
    """


@app.post("/emit_data")
async def emit_data(
    rl_batch: Optional[UploadFile] = File(None),
    sl_transitions: Optional[UploadFile] = File(None),
    _: bool = Depends(verify_password),
):
    state.record_request()
    if rl_batch:
        await service.ingest_rl_batch(rl_batch)

    if sl_transitions:
        await service.ingest_sl_transitions(sl_transitions)

    params = service.get_parameters()

    headers = {
        "X-Learner-Connected": "True" if state.learner_connected else "False",
        "X-Weights-Version": str(state.weights_version)
    }

    if params:
        logger.debug(
            "Sending model parameters to actor in emit_data response.")
        return Response(content=params, media_type="application/octet-stream", headers=headers)

    return Response(content=pickle.dumps({"status": "received"}), headers=headers)


@app.get("/weights_info")
async def weights_info(_: bool = Depends(verify_password)):
    return {"version": state.weights_version}


@app.get("/fetch_params")
async def fetch_params(_: bool = Depends(verify_password)):
    params = service.get_parameters()
    if not params:
        raise HTTPException(status_code=404, detail="No parameters available")

    logger.debug("Sending model parameters to requester.")
    return Response(
        content=params,
        media_type="application/octet-stream",
        headers={"X-Weights-Version": str(state.weights_version)}
    )


@app.post("/push_params")
async def push_params(
    params: UploadFile = File(...),
    _: bool = Depends(verify_password),
):
    raw = await params.read()
    service.set_parameters(raw)
    logger.info(f"New model parameters received (v{state.weights_version}).")
    return {"status": "updated", "version": state.weights_version}


@app.post("/update_metrics")
async def update_metrics(
    metrics: dict,
    _: bool = Depends(verify_password),
):
    state.update_metrics(metrics)
    return {"status": "ok"}


@app.get("/status", response_model=StatusResponse)
async def status(_: bool = Depends(verify_password)):
    return StatusResponse(
        status="running",
        **state.status()
    )


@app.post("/register_actor")
async def register_actor(_: bool = Depends(verify_password)):
    actor_id = state.register_actor()
    logger.info(f"Registered new actor with ID: {actor_id}")
    return {"actor_id": actor_id}


@app.websocket("/learner_stream")
async def learner_stream(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if token != DEFAULT_PASSWORD:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    state.learner_connected = True
    state.active_learner_ws = websocket
    logger.info("Learner connected via WebSocket")

    try:
        while True:
            data = service.fetch_training_data()
            if data:
                logger.debug("Streaming data to learner via WebSocket.")
                await websocket.send_bytes(data)
            else:
                await asyncio.sleep(0.1)

            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=0.01)
            except asyncio.TimeoutError:
                pass
    except (WebSocketDisconnect, Exception) as e:
        logger.info(f"Learner disconnected: {e}")
    finally:
        state.learner_disconnect()
        if hasattr(state, "active_learner_ws"):
            state.active_learner_ws = None

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=Config.SERVER_PORT,
    )
