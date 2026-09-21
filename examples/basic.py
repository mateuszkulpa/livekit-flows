from dotenv import load_dotenv
from livekit.agents import (
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.plugins import cartesia, deepgram, openai, silero

from livekit_flows import ConversationFlow, Edge, FlowAgent, FlowNode

load_dotenv()

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


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    agent = FlowAgent(flow=reservation_flow)
    session = AgentSession(
        vad=silero.VAD.load(),
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-4.1-mini"),
        tts=cartesia.TTS(),
    )

    await session.start(agent=agent, room=ctx.room)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
