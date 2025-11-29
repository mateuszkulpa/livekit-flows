from __future__ import annotations

from livekit.agents import function_tool, RunContext
from ..core import Edge, FlowNode


class ToolFactory:
    def __init__(self, on_transition, on_collect_data, get_description=None):
        self._on_transition = on_transition
        self._on_collect_data = on_collect_data
        self._get_description = get_description or (
            lambda edge_id: f"Transition via {edge_id}"
        )

    def build_data_collection_tool(self, edge: Edge):
        """Build a tool from JSON Schema"""
        if not edge.input_schema:
            raise ValueError(f"Edge {edge.id} has no input_schema defined")

        # Build the raw schema for the function tool
        raw_schema = {
            "type": "function",
            "name": edge.id,
            "description": edge.condition,
            "parameters": edge.input_schema,
        }

        async def data_collection_func(
            raw_arguments: dict[str, object], context: RunContext
        ):
            # Collect all data from the arguments
            collected_data = dict(raw_arguments)
            await self._on_collect_data(collected_data, edge.target_node_id, edge.id)

        return function_tool(data_collection_func, raw_schema=raw_schema)

    def build_transition_tool(self, edge_id: str, target_node_id: str):
        async def transition_func(context: RunContext):
            await self._on_transition(target_node_id, edge_id)

        return function_tool(
            transition_func,
            name=edge_id,
            description=self._get_description(edge_id),
        )

    def build_tools_for_node(self, node: FlowNode):
        tools = []

        for edge in node.edges:
            if edge.input_schema:
                tools.append(self.build_data_collection_tool(edge))
            elif edge.target_node_id:
                tools.append(self.build_transition_tool(edge.id, edge.target_node_id))

        return tools
