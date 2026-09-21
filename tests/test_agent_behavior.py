import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from livekit import api

from livekit_flows import (
    ActionTrigger,
    ActionTriggerType,
    ConversationFlow,
    CustomAction,
    Edge,
    FlowAgent,
    FlowNode,
    HttpMethod,
)
from livekit_flows.agent.session import end_session


class FakeSession:
    def __init__(self):
        self.userdata: Any = None
        self.updated_agent: FlowAgent | None = None
        self.replies: list[str] = []
        self.said: list[str] = []
        self.speech_handle: Any = None

    def update_agent(self, agent):
        self.updated_agent = agent

    def generate_reply(self, instructions):
        self.replies.append(instructions)
        return self.speech_handle

    def say(self, text):
        self.said.append(text)
        return self.speech_handle


def attach_session(agent: FlowAgent, session: FakeSession | None = None) -> FakeSession:
    session = session or FakeSession()
    agent._activity = cast(Any, SimpleNamespace(session=session))
    return session


def tool_info(tool):
    info = getattr(tool, "info", None)
    if info is not None and hasattr(info, "name"):
        return info
    raw_info = getattr(tool, "__livekit_raw_tool_info", None)
    if raw_info is not None:
        return raw_info
    return tool.__livekit_tool_info


def tool_named(agent: FlowAgent, name: str):
    for tool in agent.tools:
        if tool_info(tool).name == name:
            return tool
    raise AssertionError(f"Tool {name} was not built")


def reservation_flow() -> ConversationFlow:
    return ConversationFlow(
        system_prompt="Take a reservation.",
        initial_node="welcome",
        environment_variables={"token": "secret"},
        actions=[
            CustomAction(
                id="save",
                name="Save",
                description="Save the reservation",
                method=HttpMethod.POST,
                url="http://unused",
                store_response_as="saved",
            )
        ],
        nodes=[
            FlowNode(
                id="welcome",
                name="Welcome",
                static_text="Hello {{ userdata.name | default('there') }}",
                edges=[
                    Edge(
                        id="to_details",
                        condition="Got name",
                        target_node_id="details",
                    ),
                    Edge(id="unused", condition="Nowhere"),
                ],
                actions=[
                    ActionTrigger(
                        trigger_type=ActionTriggerType.ON_EXIT,
                        action_id="save",
                    )
                ],
            ),
            FlowNode(
                id="details",
                name="Details",
                instruction="Ask {{ userdata.name }} for a time.",
                edges=[
                    Edge(
                        id="collect_details",
                        condition="Got party size",
                        target_node_id="done",
                        input_schema={
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Name"},
                                "party_size": {
                                    "type": "integer",
                                    "description": "Party size",
                                },
                            },
                            "required": ["name"],
                        },
                    )
                ],
            ),
            FlowNode(
                id="done",
                name="Done",
                static_text="Saved as {{ actions.saved.data.id }}",
                is_final=True,
                actions=[
                    ActionTrigger(
                        trigger_type=ActionTriggerType.ON_ENTER,
                        action_id="save",
                    )
                ],
            ),
        ],
    )


def test_agent_starts_on_initial_node_and_builds_only_usable_tools():
    agent = FlowAgent(flow=reservation_flow())

    assert agent._current_node.id == "welcome"
    assert [tool_info(tool).name for tool in agent.tools] == ["to_details"]
    assert (
        tool_info(tool_named(agent, "to_details")).description
        == "Transition to details when got name"
    )

    with pytest.raises(ValueError, match="Initial node missing not found in flow"):
        FlowAgent(
            flow=ConversationFlow(
                system_prompt="Test",
                initial_node="missing",
                nodes=[FlowNode(id="welcome", name="Welcome")],
            )
        )


def test_agent_can_start_on_an_explicit_node():
    flow = reservation_flow()
    agent = FlowAgent(flow=flow, current_node=flow.nodes[1])

    assert agent._current_node.id == "details"
    assert tool_info(agent.tools[0]).name == "collect_details"


@pytest.mark.asyncio
async def test_transition_tool_hands_off_to_the_target_node():
    flow = reservation_flow()
    agent = FlowAgent(flow=flow)
    session = attach_session(agent)

    await tool_named(agent, "to_details")(None)

    updated = session.updated_agent
    assert updated is not None
    assert updated._current_node.id == "details"
    assert updated._action_executor is agent._action_executor


@pytest.mark.asyncio
async def test_data_collection_stores_fields_and_still_moves_on_invalid_data():
    flow = reservation_flow()
    agent = FlowAgent(flow=flow, current_node=flow.nodes[1])
    session = attach_session(agent)

    await tool_named(agent, "collect_details")({"name": "Ada", "party_size": 4}, None)

    assert session.userdata.name == "Ada"
    assert session.userdata.party_size == 4
    updated = session.updated_agent
    assert updated is not None
    assert updated._current_node.id == "done"

    agent = FlowAgent(flow=flow, current_node=flow.nodes[1])
    session = attach_session(agent)
    await tool_named(agent, "collect_details")({"party_size": "many"}, None)

    assert session.userdata.party_size == "many"
    updated = session.updated_agent
    assert updated is not None
    assert updated._current_node.id == "done"


@pytest.mark.asyncio
async def test_data_collection_without_target_does_not_transition():
    flow = reservation_flow()
    flow.nodes[1].edges[0].target_node_id = None
    agent = FlowAgent(flow=flow, current_node=flow.nodes[1])
    session = attach_session(agent)

    await tool_named(agent, "collect_details")({"name": "Ada"}, None)

    assert session.userdata.name == "Ada"
    assert session.updated_agent is None


@pytest.mark.asyncio
async def test_transition_to_unknown_node_raises():
    agent = FlowAgent(flow=reservation_flow())
    attach_session(agent)

    with pytest.raises(ValueError, match="Target node missing not found"):
        await agent._transition_to_node("missing")


@pytest.mark.asyncio
async def test_on_enter_renders_instruction_and_static_text():
    flow = reservation_flow()
    agent = FlowAgent(flow=flow)
    session = attach_session(agent)
    session.userdata = agent._userdata_class(name="Ada")

    await agent.on_enter()

    assert session.said == ["Hello Ada"]

    details = FlowAgent(flow=flow, current_node=flow.nodes[1])
    details_session = attach_session(details)
    details_session.userdata = agent._userdata_class(name="Ada")

    await details.on_enter()

    assert details_session.replies == ["Ask Ada for a time."]


@pytest.mark.asyncio
async def test_on_enter_creates_userdata_when_session_has_none_yet():
    class UnsetUserData:
        def __init__(self):
            self.replies = []
            self.said = []
            self._userdata = None
            self._ready = False

        @property
        def userdata(self):
            if not self._ready:
                raise ValueError("userdata is not set")
            return self._userdata

        @userdata.setter
        def userdata(self, value):
            self._ready = True
            self._userdata = value

        def generate_reply(self, instructions):
            self.replies.append(instructions)

        def say(self, text):
            self.said.append(text)

    flow = reservation_flow()
    agent = FlowAgent(flow=flow, current_node=flow.nodes[1])
    session = UnsetUserData()
    agent._activity = cast(Any, SimpleNamespace(session=session))

    await agent.on_enter()

    assert "name" not in session.userdata.model_fields_set
    assert session.replies == ["Ask  for a time."]


@pytest.mark.asyncio
async def test_node_actions_run_for_their_trigger_and_feed_the_reply(aiohttp_server):
    from aiohttp.web import Application, json_response

    async def save(request):
        return json_response({"id": "res-9"}, status=201)

    app = Application()
    app.router.add_post("/reservations", save)
    server = await aiohttp_server(app)

    flow = reservation_flow()
    flow.actions[0].url = f"http://{server.host}:{server.port}/reservations"
    agent = FlowAgent(flow=flow, current_node=flow.nodes[2])
    session = attach_session(agent)

    with patch("livekit_flows.agent.session.get_job_context", return_value=None):
        await agent.on_enter()

    assert session.said == ["Saved as res-9"]
    assert agent._action_executor.action_results["saved"]["data"]["id"] == "res-9"

    welcome = FlowAgent(
        flow=flow,
        current_node=flow.nodes[0],
        action_executor=agent._action_executor,
    )
    attach_session(welcome)
    async with welcome._action_executor:
        await welcome.on_exit()

    assert welcome._action_executor.action_results["saved"]["status"] == 201


@pytest.mark.asyncio
async def test_end_session_waits_for_speech_and_deletes_the_room():
    awaited = False

    class Handle:
        def __await__(self):
            async def _inner():
                nonlocal awaited
                awaited = True

            return _inner().__await__()

    delete_room = AsyncMock()
    context = SimpleNamespace(
        room=SimpleNamespace(name="room-1"),
        api=SimpleNamespace(room=SimpleNamespace(delete_room=delete_room)),
    )

    with patch("livekit_flows.agent.session.get_job_context", return_value=None):
        await end_session(None)

    with patch("livekit_flows.agent.session.get_job_context", return_value=context):
        await end_session(cast(Any, Handle()))

    assert awaited is True
    request = delete_room.await_args.args[0]
    assert isinstance(request, api.DeleteRoomRequest)
    assert request.room == "room-1"


@pytest.mark.asyncio
async def test_final_node_ends_the_session_after_speech():
    flow = reservation_flow()
    flow.nodes[2].actions = []
    flow.nodes[2].static_text = "All set"
    agent = FlowAgent(flow=flow, current_node=flow.nodes[2])
    session = attach_session(agent)
    finished = asyncio.get_running_loop().create_future()
    finished.set_result(None)
    session.speech_handle = finished

    with (
        patch("livekit_flows.agent.session.get_job_context", return_value=None),
        patch(
            "livekit_flows.agent.flow_agent.end_session",
            wraps=end_session,
        ) as wrapped,
    ):
        await agent.on_enter()

    assert session.said == ["All set"]
    wrapped.assert_awaited_once()
