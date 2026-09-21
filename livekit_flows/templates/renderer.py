import logging
from typing import Any

from jinja2 import BaseLoader, Environment
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class TemplateRenderer:
    def __init__(self):
        self.jinja_env = Environment(loader=BaseLoader())

    def build_context(
        self,
        userdata: BaseModel | None = None,
        environment_vars: dict[str, str] | None = None,
        action_results: dict[str, Any] | None = None,
        custom_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = {
            "env": environment_vars or {},
            "actions": action_results or {},
            "userdata": userdata.model_dump() if userdata else {},
        }

        if custom_context:
            context.update(custom_context)

        return context

    def render(self, template_str: str, context: dict[str, Any]) -> str:
        try:
            template = self.jinja_env.from_string(template_str)
            return template.render(**context)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Template rendering error: {e}")
            return template_str

    def render_with_data(
        self,
        template_str: str,
        userdata: BaseModel | None = None,
        environment_vars: dict[str, str] | None = None,
        action_results: dict[str, Any] | None = None,
        custom_context: dict[str, Any] | None = None,
    ) -> str:
        context = self.build_context(
            userdata=userdata,
            environment_vars=environment_vars,
            action_results=action_results,
            custom_context=custom_context,
        )
        return self.render(template_str, context)
