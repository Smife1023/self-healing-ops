# -*- coding: utf-8 -*-
"""
MCP Agent Server -- Base class for MCP-compliant agent services.

Each agent runs as an independent FastAPI microservice exposing MCP-like
endpoints (tools/list, tools/call) with:
  - Anthropic-compatible LLM integration via MIMO API
  - Structured JSON extraction from LLM responses
  - Retry logic with exponential backoff
  - Request/response logging with trace IDs
  - Health check and readiness probes
"""

import json
import logging
import re
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class ToolCallRequest(BaseModel):
    """Standard MCP tool invocation request."""
    arguments: dict[str, Any] = {}
    request_id: str = ""


class ToolCallResponse(BaseModel):
    """Standard MCP tool invocation response."""
    result: Any
    request_id: str = ""
    elapsed_ms: float = 0
    agent: str = ""


class MCPAgentServer(ABC):
    """
    Base class for MCP Agent servers.

    Exposes a FastAPI app with:
      GET  /health              -- liveness probe
      GET  /ready               -- readiness probe (checks LLM connectivity)
      GET  /tools               -- list available tools (MCP tools/list)
      POST /tools/{name}/invoke -- invoke a tool (MCP tools/call)
      GET  /metrics             -- basic request metrics
    """

    def __init__(self, name: str, port: int, api_key: str, model: str, base_url: str):
        self.name = name
        self.port = port
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.logger = logging.getLogger(name)
        self.app = FastAPI(
            title=f"MCP Agent: {name}",
            description=f"Self-Healing Ops -- {name} MCP Server",
            version="2.0.0",
        )
        self._request_count = 0
        self._error_count = 0
        self._total_latency_ms = 0.0
        self._setup_middleware()
        self._setup_routes()

    def _setup_middleware(self):
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @self.app.middleware("http")
        async def logging_middleware(request: Request, call_next):
            trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4())[:8])
            start = time.time()
            response = await call_next(request)
            elapsed = (time.time() - start) * 1000
            self.logger.debug(
                f"[{trace_id}] {request.method} {request.url.path} "
                f"-> {response.status_code} ({elapsed:.0f}ms)"
            )
            return response

    def _setup_routes(self):
        @self.app.get("/health")
        async def health():
            return {
                "status": "ok",
                "agent": self.name,
                "model": self.model,
                "request_count": self._request_count,
                "error_count": self._error_count,
                "avg_latency_ms": round(
                    self._total_latency_ms / max(self._request_count, 1), 1
                ),
            }

        @self.app.get("/ready")
        async def ready():
            """Readiness probe -- checks if LLM is reachable."""
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(f"{self.base_url}/v1/models", headers={
                        "x-api-key": self.api_key,
                    })
                    if resp.status_code in (200, 404, 405):  # 404/405 = API alive
                        return {"ready": True, "llm": "reachable"}
                    return {"ready": False, "llm": f"HTTP {resp.status_code}"}
            except Exception as e:
                return {"ready": False, "llm": f"unreachable: {e}"}

        @self.app.get("/tools")
        async def list_tools():
            """MCP tools/list endpoint."""
            return {
                "tools": self.get_tool_definitions(),
                "agent": self.name,
                "count": len(self.get_tool_definitions()),
            }

        @self.app.post("/tools/{tool_name}/invoke")
        async def invoke_tool(tool_name: str, request: ToolCallRequest):
            """MCP tools/call endpoint."""
            trace_id = request.request_id or str(uuid.uuid4())[:8]
            start = time.time()
            self._request_count += 1

            try:
                self.logger.info(f"[{trace_id}] Invoking tool: {tool_name}")
                result = await self.execute_tool(tool_name, request.arguments)
                elapsed = (time.time() - start) * 1000
                self._total_latency_ms += elapsed

                self.logger.info(
                    f"[{trace_id}] Tool {tool_name} completed ({elapsed:.0f}ms, "
                    f"{len(str(result))} chars)"
                )
                return {
                    "result": result,
                    "request_id": trace_id,
                    "elapsed_ms": round(elapsed, 1),
                    "agent": self.name,
                }
            except Exception as e:
                self._error_count += 1
                elapsed = (time.time() - start) * 1000
                self.logger.error(f"[{trace_id}] Tool {tool_name} failed: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": str(e),
                        "tool": tool_name,
                        "request_id": trace_id,
                        "elapsed_ms": round(elapsed, 1),
                    },
                )

        @self.app.get("/metrics")
        async def metrics():
            return {
                "agent": self.name,
                "total_requests": self._request_count,
                "total_errors": self._error_count,
                "error_rate": round(
                    self._error_count / max(self._request_count, 1), 4
                ),
                "avg_latency_ms": round(
                    self._total_latency_ms / max(self._request_count, 1), 1
                ),
            }

    @abstractmethod
    def get_tool_definitions(self) -> list[dict]:
        """Return MCP tool definitions for this agent."""
        ...

    @abstractmethod
    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool and return the result."""
        ...

    async def call_llm(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.1,
        max_retries: int = 2,
    ) -> str:
        """
        Call MIMO LLM (Anthropic-compatible API) with retry logic.

        Args:
            system_prompt: System-level instructions for the LLM.
            user_message: User message with context data.
            temperature: LLM temperature (low for deterministic output).
            max_retries: Maximum retry attempts on transient failures.

        Returns:
            Extracted JSON string or raw LLM response.
        """
        url = f"{self.base_url}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        }

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=90.0) as client:
                    start = time.time()
                    response = await client.post(url, json=payload, headers=headers)
                    elapsed = (time.time() - start) * 1000

                    if response.status_code == 429:
                        # Rate limited -- back off and retry
                        wait = min(2 ** attempt * 2, 30)
                        self.logger.warning(
                            f"Rate limited (429), retrying in {wait}s "
                            f"(attempt {attempt + 1}/{max_retries + 1})"
                        )
                        time.sleep(wait)
                        continue

                    response.raise_for_status()
                    data = response.json()

                    self.logger.info(
                        f"LLM response: {elapsed:.0f}ms, "
                        f"tokens: {data.get('usage', {}).get('output_tokens', '?')} out / "
                        f"{data.get('usage', {}).get('input_tokens', '?')} in"
                    )

                    # Extract text from content blocks
                    content_blocks = data.get("content", [])
                    text_parts = []
                    for block in content_blocks:
                        if block.get("type") == "text":
                            text_parts.append(block["text"])
                        elif block.get("type") == "thinking":
                            # Some models return reasoning in thinking blocks
                            thinking = block.get("thinking", "")
                            if thinking:
                                text_parts.append(thinking)

                    if text_parts:
                        combined = "\n".join(text_parts)
                        return self._extract_json_from_text(combined)
                    return str(data)

            except httpx.TimeoutException:
                last_error = "LLM request timed out"
                self.logger.warning(
                    f"LLM timeout (attempt {attempt + 1}/{max_retries + 1})"
                )
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue

            except httpx.HTTPStatusError as e:
                last_error = f"HTTP {e.response.status_code}"
                self.logger.error(
                    f"LLM API error: {e.response.status_code} -- "
                    f"{e.response.text[:200]}"
                )
                if e.response.status_code >= 500 and attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                break

            except Exception as e:
                last_error = str(e)
                self.logger.error(f"LLM call failed: {e}")
                break

        return json.dumps({
            "error": f"[LLM ERROR] {last_error}",
            "retries_exhausted": True,
            "agent": self.name,
        }, ensure_ascii=False)

    def _extract_json_from_text(self, text: str) -> str:
        """
        Extract the most relevant JSON object from LLM response text.

        Strategy:
          1. Find all balanced {...} blocks
          2. Try to parse each as JSON
          3. Return the largest valid JSON object (most likely the main output)
          4. If no JSON found, return raw text wrapped in a JSON envelope
        """
        # Find all balanced brace blocks
        json_candidates = []
        depth = 0
        start = -1
        in_string = False
        escape_next = False

        for i, ch in enumerate(text):
            if escape_next:
                escape_next = False
                continue
            if ch == '\\':
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue

            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start >= 0:
                    candidate = text[start:i + 1]
                    json_candidates.append(candidate)
                    start = -1

        # Try each candidate, prefer the largest valid one
        valid_candidates = []
        for candidate in json_candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict) and len(parsed) > 0:
                    valid_candidates.append((len(candidate), parsed))
            except json.JSONDecodeError:
                continue

        if valid_candidates:
            # Return the largest valid JSON object
            valid_candidates.sort(key=lambda x: x[0], reverse=True)
            return json.dumps(valid_candidates[0][1], ensure_ascii=False, indent=2)

        # No valid JSON found -- wrap raw text in a response envelope
        return json.dumps({
            "raw_response": text[:3000],
            "note": "LLM did not return valid JSON, raw response included",
        }, ensure_ascii=False, indent=2)

    def run(self):
        """Start the agent server (blocking)."""
        import uvicorn
        self.logger.info(
            f"Starting MCP Agent '{self.name}' on port {self.port} "
            f"(model={self.model})"
        )
        uvicorn.run(
            self.app,
            host="127.0.0.1",
            port=self.port,
            log_level="warning",
            access_log=False,
        )