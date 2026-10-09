import time
import pytest
from backend.app.telephony.jitter_buffer import AudioJitterBuffer
from backend.app.telephony.transcoder import (
    mulaw_8k_to_pcm16_24k,
    mulaw_to_pcm16_8k,
    pcm16_24k_to_mulaw_8k,
    pcm16_8k_to_mulaw,
    resample_24k_to_8k,
    resample_8k_to_24k,
)


def test_mulaw_and_pcm16_translation_sizes():
    # 20ms frame of G.711 mu-law is 160 bytes (8000 Hz * 0.02s * 1 byte/sample)
    raw_mulaw = bytes([0xFF] * 160)

    # 1. mu-law to 8kHz PCM16 (160 bytes -> 320 bytes, 160 16-bit samples)
    pcm16_8k = mulaw_to_pcm16_8k(raw_mulaw)
    assert len(pcm16_8k) == 320

    # 2. 8kHz PCM16 back to mu-law (320 bytes -> 160 bytes)
    back_mulaw = pcm16_8k_to_mulaw(pcm16_8k)
    assert len(back_mulaw) == 160

    # 3. Upsample 8kHz PCM16 to 24kHz PCM16 (320 bytes -> 960 bytes, 480 samples)
    pcm16_24k = resample_8k_to_24k(pcm16_8k)
    assert len(pcm16_24k) == 960

    # 4. Downsample 24kHz PCM16 to 8kHz PCM16 (960 bytes -> 320 bytes)
    downsampled_8k = resample_24k_to_8k(pcm16_24k)
    assert len(downsampled_8k) == 320


def test_end_to_end_audio_pipeline():
    # 20ms Twilio ingress frame
    twilio_frame = bytes([0x7E] * 160)

    # Ingress: Twilio 8kHz mu-law -> OpenAI 24kHz PCM16
    openai_frame = mulaw_8k_to_pcm16_24k(twilio_frame)
    assert len(openai_frame) == 960

    # Egress: OpenAI 24kHz PCM16 -> Twilio 8kHz mu-law
    egress_frame = pcm16_24k_to_mulaw_8k(openai_frame)
    assert len(egress_frame) == 160


def test_transcoding_latency_benchmark():
    # Verify processing latency budget (< 3.0 ms per 20ms audio frame)
    test_frame = bytes([0xAA] * 160)
    iterations = 500

    start_time = time.perf_counter()
    for _ in range(iterations):
        _ = mulaw_8k_to_pcm16_24k(test_frame)
    elapsed = time.perf_counter() - start_time

    avg_latency_ms = (elapsed / iterations) * 1000
    # Must comfortably be under 3.0ms per frame
    assert avg_latency_ms < 1.0, f"Average latency too high: {avg_latency_ms:.4f} ms"


@pytest.mark.asyncio
async def test_jitter_buffer_chunking_and_clear():
    buffer = AudioJitterBuffer(frame_size=160)
    assert buffer.buffer_len == 0

    # Push 350 bytes (should yield two 160-byte frames, leaving 30 bytes buffered)
    await buffer.push(bytes([0x01] * 350))
    assert buffer.buffer_len == 350

    frame1 = await buffer.pop_frame()
    assert frame1 is not None
    assert len(frame1) == 160
    assert buffer.sequence_number == 1

    frame2 = await buffer.pop_frame()
    assert frame2 is not None
    assert len(frame2) == 160
    assert buffer.sequence_number == 2

    # Remaining 30 bytes is incomplete frame
    frame3 = await buffer.pop_frame()
    assert frame3 is None
    assert buffer.buffer_len == 30

    # Test barge-in clear
    await buffer.clear()
    assert buffer.buffer_len == 0
