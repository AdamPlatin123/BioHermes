"""BioHermes API Server."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import config
from ..tools.mineru_parser import MinerUParser
from ..agent.core import BioHermesAgent
from .sse import SSEManager
from .routes_task import router as task_router, init as task_init
from .routes_document import router as doc_router

# Global state
active_sessions: dict = {}
sse_manager = SSEManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(
    title="BioHermes Data Agent API",
    description="MinerU-Powered Data Agent — Judge→Select→Execute→Verify",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Initialize routes
task_init(active_sessions, sse_manager, None)
app.include_router(task_router)
app.include_router(doc_router)


@app.get("/api/health")
async def health():
    parser = MinerUParser(config.MINERU_API_URL)
    mineru_status = parser.health_check()
    return {
        "status": "ok",
        "agent": "BioHermes v2.0.0",
        "architecture": "Judge→Select→Execute→Verify",
        "mineru": mineru_status,
        "active_sessions": sse_manager.active_sessions(),
        "tools": list(BioHermesAgent.__module__ and ["mineru_parse", "table_extract", "structure_extract", "data_clean", "report_generate"]),
    }


@app.get("/api/tools")
async def list_tools():
    from ..tools import TOOL_REGISTRY
    return {name: {"description": cls.description} for name, cls in TOOL_REGISTRY.items()}


def main():
    import uvicorn
    uvicorn.run(app, host=config.SERVER_HOST, port=config.SERVER_PORT)


if __name__ == "__main__":
    main()
