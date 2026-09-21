import pytest
from livekit.agents import AgentSession
from livekit.plugins import openai

from livekit_flows import ConversationFlow, Edge, FlowAgent, FlowNode

reservation_flow = ConversationFlow(
    system_prompt="You are a conversational voice agent that takes restaurant reservations. Be friendly and get: name, party size, date, time.",
    initial_node="welcome",
    nodes=[
        FlowNode(
            id="welcome",
            name="Welcome",
            static_text="Hi! I'll help you make a reservation. What's your name?",
            edges=[
                Edge(
                    condition="Got name",
                    id="welcome_to_get_details",
                    target_node_id="get_details",
                )
            ],
        ),
        FlowNode(
            id="get_details",
            name="Get Details",
            instruction="Ask about the party size, date, and time.",
            edges=[
                Edge(
                    condition="Got details",
                    id="get_details_to_confirm",
                    target_node_id="confirm",
                )
            ],
        ),
        FlowNode(
            id="confirm",
            name="Confirm",
            instruction="I have your reservation. Is everything correct?",
            edges=[
                Edge(condition="Yes", id="confirm_to_done", target_node_id="done"),
                Edge(
                    condition="No",
                    id="confirm_to_get_details",
                    target_node_id="get_details",
                ),
            ],
        ),
        FlowNode(
            id="done",
            name="Done",
            static_text="All set! See you then!",
            is_final=True,
        ),
    ],
)


@pytest.mark.asyncio
async def test_complete_reservation_flow(mock_job_context):
    """Test the complete reservation flow from start to finish."""
    async with (
        openai.LLM(model="gpt-4o-mini") as llm,
        AgentSession(llm=llm) as session,
    ):
        agent = FlowAgent(flow=reservation_flow)
        await session.start(agent)

        welcome_response = await session.run(user_input="Hello")
        welcome_response.expect.contains_message(role="assistant")

        name_response = await session.run(user_input="Hi, I'm Alice Johnson")
        name_response.expect.next_event().is_function_call(
            name="welcome_to_get_details"
        )

        details_response = await session.run(
            user_input="I need a table for 2 on Saturday at 8 PM"
        )
        details_response.expect.next_event().is_function_call(
            name="get_details_to_confirm"
        )

        confirmation_response = await session.run(user_input="Yes, that's perfect")
        confirmation_response.expect.next_event().is_function_call(
            name="confirm_to_done"
        )


@pytest.mark.asyncio
async def test_reservation_flow_with_corrections(mock_job_context):
    """Test the reservation flow when user wants to make corrections."""
    async with (
        openai.LLM(model="gpt-4o-mini") as llm,
        AgentSession(llm=llm) as session,
    ):
        agent = FlowAgent(flow=reservation_flow)
        await session.start(agent)

        await session.run(user_input="Hello")
        await session.run(user_input="My name is John Smith")
        await session.run(user_input="I need a table for 4 people on Friday at 7 PM")

        correction_response = await session.run(user_input="No, that's not correct")
        correction_response.expect.next_event().is_function_call(
            name="confirm_to_get_details"
        )


@pytest.mark.asyncio
async def test_flow_structure():
    """Test that the flow structure is correctly defined."""
    assert reservation_flow.initial_node == "welcome"
    assert len(reservation_flow.nodes) == 4

    agent = FlowAgent(flow=reservation_flow)
    assert agent._current_node.id == "welcome"
    assert len(agent.tools) == len(agent._current_node.edges)

    with pytest.raises(ValueError, match="Initial node nonexistent not found in flow"):
        FlowAgent(
            flow=ConversationFlow(
                system_prompt="Test flow",
                initial_node="nonexistent",
                nodes=[FlowNode(id="valid", name="Valid", static_text="Hello")],
            )
        )
