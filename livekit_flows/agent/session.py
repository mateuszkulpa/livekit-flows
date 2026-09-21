import logging

from livekit import api
from livekit.agents import get_job_context
from livekit.agents.voice import SpeechHandle

logger = logging.getLogger(__name__)


async def end_session(speech_handle: SpeechHandle | None):
    if speech_handle:
        await speech_handle

    ctx = get_job_context()
    if ctx is None:
        return

    await ctx.api.room.delete_room(
        api.DeleteRoomRequest(
            room=ctx.room.name,
        )
    )
