import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.calls import CallTranscript

logger = logging.getLogger("agents.transcription_logger")


class TranscriptEntry:
    def __init__(
        self,
        speaker_role: str,
        content: str,
        start_time_ms: int = 0,
        end_time_ms: int = 0,
        speech_confidence: Optional[float] = 1.0,
        is_interrupted: bool = False,
    ):
        self.speaker_role = speaker_role
        self.content = content
        self.start_time_ms = start_time_ms
        self.end_time_ms = end_time_ms
        self.speech_confidence = speech_confidence
        self.is_interrupted = is_interrupted
        self.timestamp = datetime.now(timezone.utc)


class CallTranscriptionLogger:
    """
    Records turn-by-turn conversational utterances, speaker diarization,
    and timestamps, persisting them to PostgreSQL.
    """

    def __init__(self, call_id: str, session_maker=None):
        self.call_id = call_id
        self.session_maker = session_maker or AsyncSessionLocal
        self.entries: List[TranscriptEntry] = []
        self._lock = asyncio.Lock()

    async def log_utterance(
        self,
        speaker_role: str,
        content: str,
        start_time_ms: int = 0,
        end_time_ms: int = 0,
        speech_confidence: Optional[float] = 1.0,
        is_interrupted: bool = False,
    ) -> TranscriptEntry:
        """Appends and persists a single speaker turn."""
        entry = TranscriptEntry(
            speaker_role=speaker_role,
            content=content,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            speech_confidence=speech_confidence,
            is_interrupted=is_interrupted,
        )

        async with self._lock:
            self.entries.append(entry)

        # Persist to database asynchronously
        try:
            async with self.session_maker() as db:
                record = CallTranscript(
                    call_id=self.call_id,
                    speaker_role=speaker_role,
                    content=content,
                    start_time_ms=start_time_ms,
                    end_time_ms=end_time_ms,
                    speech_confidence=speech_confidence,
                    is_interrupted=is_interrupted,
                )
                db.add(record)
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to persist transcript for call {self.call_id}: {e}")

        return entry

    def mark_last_assistant_turn_interrupted(self) -> None:
        """Flags the most recent assistant turn as interrupted by user barge-in."""
        for entry in reversed(self.entries):
            if entry.speaker_role == "assistant":
                entry.is_interrupted = True
                break

    def get_full_formatted_transcript(self) -> str:
        """Returns clean chronological transcript text suitable for LLM analysis."""
        lines = []
        for entry in self.entries:
            role = entry.speaker_role.capitalize()
            flag = " [Interrupted]" if entry.is_interrupted else ""
            lines.append(f"{role}: {entry.content}{flag}")
        return "\n".join(lines)
