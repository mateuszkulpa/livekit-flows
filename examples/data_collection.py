import logging

from dotenv import load_dotenv
from livekit.agents import (
    AgentSession,
    CloseEvent,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.plugins import cartesia, deepgram, openai, silero
from pydantic import BaseModel, Field

from livekit_flows import (
    ConversationFlow,
    Edge,
    FlowAgent,
    FlowNode,
)

logger = logging.getLogger(__name__)

load_dotenv()


class CustomerName(BaseModel):
    customer_name: str = Field(description="The customer's full name")


class PartySize(BaseModel):
    party_size: int = Field(description="Number of people for the reservation")


class ReservationDate(BaseModel):
    reservation_date: str = Field(description="Date and time for the reservation")


class PhoneNumber(BaseModel):
    phone_number: str = Field(description="Customer's phone number")


reservation_flow = ConversationFlow(
    system_prompt="You are a conversational voice agent that takes restaurant reservations. Be friendly and collect customer information.",
    initial_node="welcome",
    nodes=[
        FlowNode(
            id="welcome",
            name="Welcome",
            static_text="Hi! I'll help you make a reservation. What's your name?",
            edges=[
                Edge(
                    condition="Customer provided their name",
                    id="collect_name",
                    target_node_id="get_party_size",
                    input_schema=CustomerName,
                )
            ],
        ),
        FlowNode(
            id="get_party_size",
            name="Get Party Size",
            instruction="Ask about the party size",
            edges=[
                Edge(
                    condition="Customer provided party size",
                    id="collect_party_size",
                    target_node_id="get_date",
                    input_schema=PartySize,
                )
            ],
        ),
        FlowNode(
            id="get_date",
            name="Get Reservation Date",
            instruction="Ask about the preferred date and time for the reservation",
            edges=[
                Edge(
                    condition="Customer provided date and time",
                    id="collect_date",
                    target_node_id="get_phone",
                    input_schema=ReservationDate,
                )
            ],
        ),
        FlowNode(
            id="get_phone",
            name="Get Phone Number",
            instruction="Ask about the phone number",
            edges=[
                Edge(
                    condition="Customer provided phone number",
                    id="collect_phone",
                    target_node_id="confirm",
                    input_schema=PhoneNumber,
                )
            ],
        ),
        FlowNode(
            id="confirm",
            name="Confirm Details",
            instruction="Confirm all reservation details including name, party size, date, and phone number",
            edges=[
                Edge(condition="Yes", id="confirm_yes", target_node_id="done"),
                Edge(condition="No", id="confirm_no", target_node_id="welcome"),
            ],
        ),
        FlowNode(
            id="done",
            name="Done",
            static_text="Perfect! Your reservation is confirmed. We'll see you soon!",
            is_final=True,
        ),
    ],
)


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    agent = FlowAgent(flow=reservation_flow)
    session = AgentSession(
        vad=silero.VAD.load(),
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-4.1-mini"),
        tts=cartesia.TTS(),
    )

    @session.on("close")
    def on_close(ev: CloseEvent):
        logger.info("Collected userdata: %s", session.userdata)

    await session.start(agent=agent, room=ctx.room)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
