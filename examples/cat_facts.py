import logging

from dotenv import load_dotenv
from livekit.agents import (
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.plugins import cartesia, deepgram, openai, silero

from livekit_flows import (
    ConversationFlow,
    FlowAgent,
)

load_dotenv()
logger = logging.getLogger(__name__)

cat_facts_flow = ConversationFlow.from_yaml_file("examples/cat_facts_flow.yaml")


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    agent = FlowAgent(flow=cat_facts_flow)
    session = AgentSession(
        vad=silero.VAD.load(),
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-4.1-mini"),
        tts=cartesia.TTS(),
    )

    await session.start(agent=agent, room=ctx.room)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
