import asyncio
from typing import AsyncGenerator, Optional


class AudioJitterBuffer:
    """
    Fixed-frame audio jitter buffer and packetizer.
    Accumulates variable-sized incoming audio chunks and yields fixed-size frames
    (e.g., 20ms = 160 bytes for G.711 mu-law, or 960 bytes for 24kHz PCM16).
    """

    def __init__(self, frame_size: int = 160):
        self.frame_size = frame_size
        self._buffer = bytearray()
        self._lock = asyncio.Lock()
        self.sequence_number = 0
        self.dropped_packets = 0

    async def push(self, chunk: bytes) -> None:
        """Pushes raw audio bytes into the buffer."""
        async with self._lock:
            self._buffer.extend(chunk)

    async def pop_frame(self) -> Optional[bytes]:
        """Pops a single complete frame if available; returns None otherwise."""
        async with self._lock:
            if len(self._buffer) >= self.frame_size:
                frame = bytes(self._buffer[:self.frame_size])
                del self._buffer[:self.frame_size]
                self.sequence_number += 1
                return frame
            return None

    async def pop_all_frames(self) -> list[bytes]:
        """Pops all complete frames currently available in the buffer."""
        frames = []
        async with self._lock:
            while len(self._buffer) >= self.frame_size:
                frame = bytes(self._buffer[:self.frame_size])
                del self._buffer[:self.frame_size]
                self.sequence_number += 1
                frames.append(frame)
        return frames

    async def clear(self) -> None:
        """Immediately flushes the buffer (used during user barge-in / interruption)."""
        async with self._lock:
            self._buffer.clear()

    @property
    def buffer_len(self) -> int:
        return len(self._buffer)
