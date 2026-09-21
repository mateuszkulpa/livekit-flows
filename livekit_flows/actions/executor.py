import json
import logging
from typing import Any

import aiohttp
from pydantic import BaseModel

from ..core import CustomAction
from ..templates import TemplateRenderer

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Executes HTTP actions with template rendering support"""

    def __init__(
        self,
        actions: list[CustomAction],
        environment_vars: dict[str, str] | None = None,
    ):
        self.actions = {action.id: action for action in actions}
        self.environment_vars = environment_vars or {}
        self.action_results: dict[str, Any] = {}
        self._http_session: aiohttp.ClientSession | None = None
        self.template_renderer = TemplateRenderer()

    async def __aenter__(self):
        self._http_session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._http_session:
            await self._http_session.close()

    async def execute_action(
        self, action_id: str, userdata: BaseModel | None = None
    ) -> dict[str, Any]:
        if action_id not in self.actions:
            logger.error(f"Action {action_id} not found")
            return {}

        action = self.actions[action_id]
        context = self.template_renderer.build_context(
            userdata=userdata,
            environment_vars=self.environment_vars,
            action_results=self.action_results,
        )

        try:
            url = self.template_renderer.render(action.url, context)

            headers = {}
            for key, value in action.headers.items():
                headers[key] = self.template_renderer.render(value, context)

            body = None
            if action.body_template:
                body_str = self.template_renderer.render(action.body_template, context)
                try:
                    body = json.loads(body_str)
                except json.JSONDecodeError:
                    body = body_str

            logger.info(f"Executing action {action_id}: {action.method} {url}")

            if not self._http_session:
                raise RuntimeError(
                    "HTTP session not initialized. Use async context manager."
                )

            async with self._http_session.request(
                method=action.method.value,
                url=url,
                headers=headers,
                json=body if isinstance(body, dict) else None,
                data=body if isinstance(body, str) else None,
                timeout=aiohttp.ClientTimeout(total=action.timeout),
            ) as response:
                response_data = {
                    "status": response.status,
                    "headers": dict(response.headers),
                    "success": response.status < 400,
                }

                try:
                    response_data["data"] = await response.json()
                except (aiohttp.ContentTypeError, json.JSONDecodeError):
                    response_data["data"] = await response.text()

                if action.store_response_as:
                    self.action_results[action.store_response_as] = response_data

                logger.info(
                    f"Action {action_id} completed with status {response.status}"
                )
                return response_data

        except Exception as e:  # noqa: BLE001
            logger.error(f"Action {action_id} failed: {e}")
            error_result = {"success": False, "error": str(e), "status": 500}

            if action.store_response_as:
                self.action_results[action.store_response_as] = error_result

            return error_result
