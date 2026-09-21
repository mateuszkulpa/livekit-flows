import asyncio
import logging

from livekit.agents import Agent, ChatContext
from livekit.agents.voice import SpeechHandle

from ..actions import ActionExecutor
from ..core import ActionTriggerType, ConversationFlow, FlowNode
from ..templates import TemplateRenderer
from ..utils import generate_userdata_class, validate_against_schema
from .session import end_session
from .tools import ToolFactory

logger = logging.getLogger(__name__)


class FlowAgent(Agent):
    def __init__(
        self,
        flow: ConversationFlow,
        current_node: FlowNode | None = None,
        chat_ctx: ChatContext | None = None,
        action_executor: ActionExecutor | None = None,
    ):
        self._flow = flow
        self._current_node = self._get_initial_node(current_node)
        self._userdata_class = generate_userdata_class(flow)

        self._action_executor = action_executor or ActionExecutor(
            actions=flow.actions, environment_vars=flow.environment_variables
        )
        self._template_renderer = TemplateRenderer()

        async def handle_transition(target_node_id: str, edge_id: str | None):
            await self._transition_to_node(target_node_id, edge_id)

        async def handle_data_collection(
            collected_data: dict, target_node_id: str | None, edge_id: str | None
        ):
            edge = None
            for e in self._current_node.edges:
                if e.id == edge_id:
                    edge = e
                    break

            if edge and edge.input_schema:
                is_valid, error_msg = validate_against_schema(
                    collected_data, edge.input_schema
                )
                if not is_valid:
                    logger.warning(
                        f"Data collection validation failed for edge {edge_id}: {error_msg}"
                    )
                    # Continue despite validation error (non-blocking)

            if not hasattr(self.session, "userdata") or self.session.userdata is None:
                self.session.userdata = self._userdata_class.model_construct()

            for key, value in collected_data.items():
                setattr(self.session.userdata, key, value)

            if target_node_id:
                await self._transition_to_node(target_node_id, edge_id)

        def get_edge_description(edge_id: str) -> str:
            for edge in self._current_node.edges:
                if edge.id == edge_id:
                    if edge.target_node_id:
                        return f"Transition to {edge.target_node_id} when {edge.condition.lower()}"
                    else:
                        return edge.condition or f"Transition via {edge_id}"
            return f"Transition via {edge_id}"

        self._tool_factory = ToolFactory(
            handle_transition, handle_data_collection, get_edge_description
        )
        tools = self._tool_factory.build_tools_for_node(self._current_node)

        super().__init__(
            instructions=flow.system_prompt,
            tools=tools,
            chat_ctx=chat_ctx,
        )

    def _get_initial_node(self, current_node: FlowNode | None) -> FlowNode:
        if current_node is not None:
            return current_node

        initial_node_id = self._flow.initial_node
        initial_node = next(
            (node for node in self._flow.nodes if node.id == initial_node_id), None
        )

        if not initial_node:
            raise ValueError(f"Initial node {initial_node_id} not found in flow")

        return initial_node

    def _get_edge_condition(self, edge_id: str) -> str:
        for edge in self._current_node.edges:
            if edge.id == edge_id:
                return edge.condition
        return f"Edge {edge_id}"

    async def _execute_node_actions(self, trigger_type: ActionTriggerType):
        actions_to_execute = [
            action
            for action in self._current_node.actions
            if action.trigger_type == trigger_type
        ]

        if not actions_to_execute:
            return

        logger.info(
            f"Executing {len(actions_to_execute)} node actions for trigger {trigger_type}"
        )

        tasks = []
        for action in actions_to_execute:
            task = self._action_executor.execute_action(
                action.action_id, self.session.userdata
            )
            tasks.append(task)

        if tasks:
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as e:  # noqa: BLE001
                logger.error(f"Error executing node actions: {e}")

    def _render_instruction(self, instruction: str) -> str:
        try:
            userdata = self.session.userdata
        except ValueError:
            self.session.userdata = self._userdata_class.model_construct()
            userdata = self.session.userdata

        return self._template_renderer.render_with_data(
            instruction,
            userdata=userdata,
            environment_vars=self._flow.environment_variables,
            action_results=self._action_executor.action_results,
        )

    async def _transition_to_node(
        self, target_node_id: str, edge_id: str | None = None
    ):
        target_node = next(
            (node for node in self._flow.nodes if node.id == target_node_id), None
        )
        if not target_node:
            raise ValueError(f"Target node {target_node_id} not found in flow")

        new_agent = FlowAgent(
            self._flow, target_node, self.chat_ctx, self._action_executor
        )
        self.session.update_agent(new_agent)

    async def on_enter(self):
        async with self._action_executor:
            await self._execute_node_actions(ActionTriggerType.ON_ENTER)

        speech_handle: SpeechHandle | None = None

        if self._current_node.instruction:
            rendered_instruction = self._render_instruction(
                self._current_node.instruction
            )
            speech_handle = self.session.generate_reply(
                instructions=rendered_instruction
            )
        elif self._current_node.static_text:
            rendered_text = self._render_instruction(self._current_node.static_text)
            speech_handle = self.session.say(rendered_text)

        if self._current_node.is_final:
            await end_session(speech_handle)

    async def on_exit(self):
        await self._execute_node_actions(ActionTriggerType.ON_EXIT)
