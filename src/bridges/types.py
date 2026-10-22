"""
Bridge Registry + Bridges para ALBRA.

ZAI SDK Bridge (priority) + Python Bridge (fallback).
Si ZAI cae, Python toma el relevo.
"""
from __future__ import annotations

import json
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class BridgeResult:
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    source: str = "unknown"


@dataclass
class BridgeHealth:
    available: bool
    latency: Optional[float] = None
    details: Optional[Dict[str, Any]] = None


class IBridge(ABC):
    """Interfaz que todo bridge debe implementar."""

    @property
    @abstractmethod
    def type(self) -> str: ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def is_available(self) -> bool: ...

    @abstractmethod
    async def execute(self, operation: str, params: Dict[str, Any]) -> BridgeResult: ...

    @abstractmethod
    async def health_check(self) -> BridgeHealth: ...


    async def startup(self) -> None: ...
    async def shutdown(self) -> None: ...


class ZaiSdkBridge(IBridge):
    """ZAI SDK Bridge — bridge primario con prioridad.

    Usa z-ai-web-dev-sdk para chat, image generation, TTS, web search.
    Si el SDK no está disponible, cae al siguiente bridge.
    """

    @property
    def type(self) -> str:
        return "zai-sdk"

    @property
    def name(self) -> str:
        return "ZAI SDK Bridge"

    def __init__(self) -> None:
        self._sdk: Any = None

    async def is_available(self) -> bool:
        try:
            # Try to import ZAI SDK
            import importlib
            mod = importlib.import_module("z_ai_web_dev_sdk")
            self._sdk = mod
            return True
        except ImportError:
            return False

    async def execute(self, operation: str, params: Dict[str, Any]) -> BridgeResult:
        if not self._sdk:
            available = await self.is_available()
            if not available:
                return BridgeResult(
                    success=False,
                    error="ZAI SDK not available",
                    source=self.type,
                )

        try:
            if operation == "chat":
                messages = params.get("messages", [])
                # Use ZAI SDK chat completions
                result = await self._sdk.chat.completions.create(
                    model=params.get("model", "default"),
                    messages=messages,
                )
                return BridgeResult(success=True, data=result, source=self.type)

            elif operation == "image.generate":
                result = await self._sdk.images.generate(
                    prompt=params.get("prompt", ""),
                    size=params.get("size", "1024x1024"),
                )
                return BridgeResult(success=True, data=result, source=self.type)

            elif operation == "voice.tts":
                result = await self._sdk.audio.speech.create(
                    text=params.get("text", ""),
                    voice=params.get("voice", "default"),
                )
                return BridgeResult(success=True, data=result, source=self.type)

            elif operation == "web.search":
                result = await self._sdk.functions.invoke(
                    "web_search",
                    {"query": params.get("query", ""), "num": params.get("num", 10)},
                )
                return BridgeResult(success=True, data=result, source=self.type)

            else:
                return BridgeResult(
                    success=False,
                    error=f"Unknown operation: {operation}",
                    source=self.type,
                )
        except Exception as e:
            return BridgeResult(success=False, error=str(e), source=self.type)

    async def health_check(self) -> BridgeHealth:
        available = await self.is_available()
        return BridgeHealth(available=available, details={"type": self.type})


class PythonBridge(IBridge):
    """Python Bridge — bridge de fallback.

    Ejecuta scripts Python para operaciones que ZAI SDK no puede manejar.
    """

    @property
    def type(self) -> str:
        return "python"

    @property
    def name(self) -> str:
        return self._name

    def __init__(self, name: str = "Python Bridge", python_path: str = "python3", script_dir: str = "./scripts") -> None:
        self._name = name
        self._python_path = python_path
        self._script_dir = script_dir

    async def is_available(self) -> bool:
        try:
            result = subprocess.run(
                [self._python_path, "--version"],
                capture_output=True, timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    async def execute(self, operation: str, params: Dict[str, Any]) -> BridgeResult:
        try:
            script_path = f"{self._script_dir}/{operation}.py"
            args_json = json.dumps(params)
            result = subprocess.run(
                [self._python_path, script_path, args_json],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return BridgeResult(success=True, data=data, source=self.type)
            else:
                return BridgeResult(success=False, error=result.stderr, source=self.type)
        except Exception as e:
            return BridgeResult(success=False, error=str(e), source=self.type)

    async def health_check(self) -> BridgeHealth:
        available = await self.is_available()
        return BridgeHealth(
            available=available,
            details={"type": self.type, "python": self._python_path},
        )


class BridgeRegistry:
    """Registry de bridges con prioridad y fallback."""

    def __init__(self) -> None:
        self._bridges: Dict[str, IBridge] = {}
        self._priority: List[str] = []

    def register(self, bridge: IBridge, is_priority: bool = False) -> None:
        self._bridges[bridge.type] = bridge
        if is_priority:
            self._priority = [bridge.type] + [t for t in self._priority if t != bridge.type]

    async def execute(self, operation: str, params: Dict[str, Any]) -> BridgeResult:
        order = self._priority + [t for t in self._bridges if t not in self._priority]
        for bridge_type in order:
            bridge = self._bridges.get(bridge_type)
            if not bridge:
                continue
            available = await bridge.is_available()
            if not available:
                continue
            try:
                result = await bridge.execute(operation, params)
                if result.success:
                    return result
            except Exception:
                continue
        return BridgeResult(success=False, error="No bridge available", source="none")

    def list(self) -> List[Dict[str, str]]:
        return [{"type": t, "name": b.name} for t, b in self._bridges.items()]

    async def startup(self) -> None:
        for bridge in self._bridges.values():
            await bridge.startup()

    async def shutdown(self) -> None:
        for bridge in self._bridges.values():
            await bridge.shutdown()
