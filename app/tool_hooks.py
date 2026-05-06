# app/tool_hooks.py
"""Pre/post tool-call hooks — transport-agnostic audit/instrumentation seam.

The MCP protocol does NOT define pre/post hooks for tool calls. This module
provides a documented seam so downstream consumers can audit, gate or
instrument every MCP tool invocation without forking ``app.core``.

Same hook fires for the same operation regardless of transport:
the FastAPI HTTP route ``/medicamento`` (operation_id ``obtener_medicamento``)
and the FastMCP stdio tool ``obtener_medicamento`` both run pre/post hooks
under the name ``obtener_medicamento``.

Contract
--------
* ``PreHookFn(tool_name, args) -> Awaitable[None]``. Raise ``OperationError``
  to abort the call — the transport translates it to its native error shape
  (HTTP: JSON 4xx; stdio: dict result).
* ``PostHookFn(tool_name, args, error, elapsed_s) -> Awaitable[None]``. Best
  effort: any exception raised by a post hook is logged and swallowed so it
  cannot mask the actual tool result. ``error`` is the exception raised by the
  tool, or ``None`` on success.
* ``args`` is a shallow dict of the parsed inputs as the transport sees them
  (HTTP: request.query_params; stdio: function kwargs). It is intentionally
  not a normalised schema — use ``tool_name`` for routing logic.

Hooks are stored on a ``HookSet`` instance owned by the FastAPI app
(``app.state.tool_hooks``) or the FastMCP server (closure in ``build_server``).
There is no module-global registry — each ``create_app``/``build_server`` call
gets its own set, which matters for test isolation.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Sequence

from app.core import OperationError

logger = logging.getLogger(__name__)

PreHookFn = Callable[[str, dict[str, Any]], Awaitable[None]]
PostHookFn = Callable[[str, dict[str, Any], Optional[BaseException], float], Awaitable[None]]


@dataclass(frozen=True)
class HookSet:
    """Per-app/server pre+post hook bundle."""

    pre: tuple[PreHookFn, ...] = field(default_factory=tuple)
    post: tuple[PostHookFn, ...] = field(default_factory=tuple)

    @classmethod
    def from_sequences(
        cls,
        pre: Sequence[PreHookFn] = (),
        post: Sequence[PostHookFn] = (),
    ) -> "HookSet":
        return cls(pre=tuple(pre), post=tuple(post))

    def is_empty(self) -> bool:
        return not self.pre and not self.post

    async def run_pre(self, tool_name: str, args: dict[str, Any]) -> None:
        """Fire all pre-hooks. ``OperationError`` propagates and aborts the call."""
        for hook in self.pre:
            await hook(tool_name, args)

    async def run_post(
        self,
        tool_name: str,
        args: dict[str, Any],
        error: BaseException | None,
        elapsed_s: float,
    ) -> None:
        """Fire all post-hooks. Exceptions are logged, never raised."""
        for hook in self.post:
            try:
                await hook(tool_name, args, error, elapsed_s)
            except Exception:
                logger.exception(
                    "post-tool hook %s failed for %s",
                    getattr(hook, "__name__", hook),
                    tool_name,
                )


EMPTY_HOOKS = HookSet()


def wrap_stdio_tool(
    hooks: HookSet,
    func: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
    """Wrap a FastMCP tool implementation with hooks + ``OperationError`` serialisation.

    Replaces the previous ``_serialize_errors`` helper. Pre-hook errors are
    serialised through the same path as core errors so the LLM gets one
    consistent payload shape.
    """
    import functools

    tool_name = func.__name__

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        if hooks.is_empty():
            try:
                return await func(*args, **kwargs)
            except OperationError as exc:
                return exc.to_dict()

        try:
            await hooks.run_pre(tool_name, dict(kwargs))
        except OperationError as exc:
            return exc.to_dict()

        started = time.perf_counter()
        err: BaseException | None = None
        try:
            result = await func(*args, **kwargs)
            return result
        except OperationError as exc:
            err = exc
            return exc.to_dict()
        except BaseException as exc:
            err = exc
            raise
        finally:
            elapsed = time.perf_counter() - started
            await hooks.run_post(tool_name, dict(kwargs), err, elapsed)

    return wrapper
