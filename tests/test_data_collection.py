import pytest
from livekit.agents import AgentSession
from livekit.plugins import openai
from pydantic import BaseModel, Field

from livekit_flows import (
    ConversationFlow,
    Edge,
    FlowAgent,
    FlowNode,
)


class NameInput(BaseModel):
    name: str = Field(description="The user's full name")


class AgeInput(BaseModel):
    age: int = Field(description="The user's age in years")


class EmailInput(BaseModel):
    email: str = Field(description="The user's email address")


survey_flow = ConversationFlow(
    system_prompt="You are a survey agent that collects user information. Be friendly and collect: name, age, email. Use the available tools to collect and store data.",
    initial_node="start",
    nodes=[
        FlowNode(
            id="start",
            name="Start Survey",
            static_text="Hi! I'd like to conduct a quick survey. What's your name?",
            edges=[
                Edge(
                    condition="User provided their name",
                    id="collect_name",
                    target_node_id="ask_age",
                    input_schema=NameInput,
                )
            ],
        ),
        FlowNode(
            id="ask_age",
            name="Ask Age",
            instruction="Thank you {{ userdata.name }}! How old are you?",
            edges=[
                Edge(
                    condition="User provided their age",
                    id="collect_age",
                    target_node_id="ask_email",
                    input_schema=AgeInput,
                )
            ],
        ),
        FlowNode(
            id="ask_email",
            name="Ask Email",
            instruction="Great! And what's your email address, {{ userdata.name }}?",
            edges=[
                Edge(
                    condition="User provided their email",
                    id="collect_email",
                    target_node_id="thank_you",
                    input_schema=EmailInput,
                )
            ],
        ),
        FlowNode(
            id="thank_you",
            name="Thank You",
            instruction="""
            Thank you for participating in our survey, {{ userdata.name }}!

            Here's what we collected:
            - Name: {{ userdata.name }}
            - Age: {{ userdata.age }}
            - Email: {{ userdata.email }}

            Have a great day!
            """,
            is_final=True,
        ),
    ],
)


@pytest.mark.requires_credentials
@pytest.mark.asyncio
async def test_data_collection_flow(mock_job_context):
    async with (
        openai.LLM(model="gpt-4o-mini") as llm,
        AgentSession(llm=llm) as session,
    ):
        agent = FlowAgent(flow=survey_flow)
        await session.start(agent)

        welcome_response = await session.run(user_input="Hello")
        welcome_response.expect.contains_message(role="assistant")

        await session.run(user_input="My name is John Doe")
        await session.run(user_input="I'm 30 years old")
        final_response = await session.run(user_input="My email is john@example.com")

        final_response.expect.contains_message(role="assistant")
        assert session.userdata.name == "John Doe"
        assert session.userdata.age == 30
        assert session.userdata.email == "john@example.com"
