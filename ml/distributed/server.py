import uvicorn
import logging
import pickle
import queue
import threading
from typing import Optional, Dict, Any

from fastapi import FastAPI, File, UploadFile, Header, HTTPException, Response, Depends
from pydantic import BaseModel
from ml.config import Config

logger = logging.getLogger("rl_server")
logging.basicConfig(level=logging.INFO)


DEFAULT_PASSWORD = Config.AUTH_CODE
QUEUE_MAXSIZE = Config.QUEUE_MAX_SIZE


class StatusResponse(BaseModel):
    status: str
    rl_queue_size: int
    sl_queue_size: int


def verify_password(x_password: str = Header(..., alias="X-Password")):
    if x_password != DEFAULT_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


class RLServerState:
    def __init__(self):
        self.rl_queue: queue.Queue = queue.Queue(maxsize=QUEUE_MAXSIZE)
        self.sl_queue: queue.Queue = queue.Queue(maxsize=QUEUE_MAXSIZE)

        self._params_lock = threading.Lock()
        self._latest_params: Optional[bytes] = None

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
        with self._params_lock:
            self._latest_params = data

    def get_params(self) -> Optional[bytes]:
        with self._params_lock:
            return self._latest_params

    def status(self) -> Dict[str, Any]:
        return {
            "rl_queue_size": self.rl_queue.qsize(),
            "sl_queue_size": self.sl_queue.qsize(),
        }


class RLService:
    def __init__(self, state: RLServerState):
        self.state = state

    async def ingest_rl_batch(self, file: UploadFile):
        try:
            raw = await file.read()
            data = pickle.loads(raw)
            self.state.push_rl(data)
        except Exception as e:
            logger.exception(f"Failed RL ingestion: {e}")

    async def ingest_sl_transitions(self, file: UploadFile):
        try:
            raw = await file.read()
            data = pickle.loads(raw)
            self.state.push_sl(data)
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


@app.get("/")
async def health():
    return {"status": "ok"}


@app.post("/emit_data")
async def emit_data(
    rl_batch: Optional[UploadFile] = File(None),
    sl_transitions: Optional[UploadFile] = File(None),
    _: bool = Depends(verify_password),
):
    if rl_batch:
        await service.ingest_rl_batch(rl_batch)

    if sl_transitions:
        await service.ingest_sl_transitions(sl_transitions)

    params = service.get_parameters()
    if params:
        return Response(content=params, media_type="application/octet-stream")

    return {"status": "received"}


@app.get("/fetch_params")
async def fetch_params(_: bool = Depends(verify_password)):
    params = service.get_parameters()
    if not params:
        raise HTTPException(status_code=404, detail="No parameters available")

    return Response(content=params, media_type="application/octet-stream")


@app.get("/get_data")
async def get_data(_: bool = Depends(verify_password)):
    data = service.fetch_training_data()

    if data is None:
        return Response(status_code=204)

    # Returning raw binary data for weight
    return Response(content=data, media_type="application/octet-stream")


@app.post("/push_params")
async def push_params(
    params: UploadFile = File(...),
    _: bool = Depends(verify_password),
):
    raw = await params.read()
    service.set_parameters(raw)
    return {"status": "updated"}


@app.get("/status", response_model=StatusResponse)
async def status(_: bool = Depends(verify_password)):
    return StatusResponse(
        status="running",
        **state.status()
    )

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=Config.SERVER_PORT,
    )
