import struct
from typing import List

# ------------------------------------------------------------------------------
# ITU-T Recommendation G.711 (mu-law / PCMU)
# ------------------------------------------------------------------------------

BIAS = 132
CLIP = 32635

# Exponent boundary thresholds for linear to mu-law encoding
EXP_BOUNDARIES = (0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF, 0x1FFF, 0x3FFF, 0x7FFF)


def _build_mulaw_to_linear_lut() -> List[int]:
    """Builds a 256-entry lookup table mapping 8-bit mu-law to 16-bit signed PCM."""
    table = []
    for b in range(256):
        ub = ~b & 0xFF
        sign = -1 if (ub & 0x80) else 1
        exponent = (ub >> 4) & 0x07
        mantissa = ub & 0x0F
        sample = ((mantissa << 3) + BIAS) << exponent
        sample -= BIAS
        table.append(sign * sample)
    return table


def _sample_to_mulaw(sample: int) -> int:
    """Encodes a single signed 16-bit linear PCM sample into an 8-bit mu-law byte."""
    if sample < 0:
        sample = -sample
        sign = 0x80
    else:
        sign = 0x00

    if sample > CLIP:
        sample = CLIP
    sample += BIAS

    exponent = 7
    for exp, threshold in enumerate(EXP_BOUNDARIES):
        if sample <= threshold:
            exponent = exp
            break

    mantissa = (sample >> (exponent + 3)) & 0x0F
    return ~(sign | (exponent << 4) | mantissa) & 0xFF


def _build_linear_to_mulaw_lut() -> bytes:
    """
    Precomputes a 65536-byte lookup table mapping every 16-bit signed integer
    (-32768 to 32767) to its corresponding 8-bit mu-law byte.
    Enables O(1) single-cycle transcoding without arithmetic branching.
    """
    lut = bytearray(65536)
    for i in range(65536):
        # Convert index [0..65535] back to signed 16-bit [-32768..32767]
        sample = i if i < 32768 else i - 65536
        lut[i] = _sample_to_mulaw(sample)
    return bytes(lut)


# Module-level static precomputed tables
MULAW_TO_LINEAR_LUT: List[int] = _build_mulaw_to_linear_lut()
LINEAR_TO_MULAW_LUT: bytes = _build_linear_to_mulaw_lut()


# ------------------------------------------------------------------------------
# Audio Transcoding Functions
# ------------------------------------------------------------------------------

def mulaw_to_pcm16_8k(mulaw_bytes: bytes) -> bytes:
    """
    Converts 8kHz G.711 mu-law bytes into 8kHz 16-bit signed little-endian PCM.
    Twilio 20ms frame = 160 mu-law bytes -> 320 PCM16 bytes.
    """
    n_samples = len(mulaw_bytes)
    samples = [MULAW_TO_LINEAR_LUT[b] for b in mulaw_bytes]
    return struct.pack(f"<{n_samples}h", *samples)


def pcm16_8k_to_mulaw(pcm16_bytes: bytes) -> bytes:
    """
    Converts 8kHz 16-bit signed little-endian PCM into 8kHz G.711 mu-law bytes.
    Uses precomputed 64KB LUT for maximum execution speed.
    """
    n_samples = len(pcm16_bytes) // 2
    raw_indices = struct.unpack(f"<{n_samples}H", pcm16_bytes)
    # Map unsigned 16-bit index directly to mu-law byte from LUT
    return bytes([LINEAR_TO_MULAW_LUT[idx] for idx in raw_indices])


def resample_8k_to_24k(pcm16_8k: bytes) -> bytes:
    """
    Upsamples 8kHz 16-bit PCM to 24kHz 16-bit PCM (1:3 upsampling)
    using linear interpolation between adjacent samples.
    Input: 160 samples (320 bytes) -> Output: 480 samples (960 bytes).
    """
    n_in = len(pcm16_8k) // 2
    if n_in == 0:
        return b""

    samples = struct.unpack(f"<{n_in}h", pcm16_8k)
    out_samples = [0] * (n_in * 3)

    for i in range(n_in):
        s0 = samples[i]
        s1 = samples[i + 1] if i + 1 < n_in else s0
        delta = s1 - s0

        out_samples[3 * i] = s0
        out_samples[3 * i + 1] = max(-32768, min(32767, int(s0 + delta / 3.0)))
        out_samples[3 * i + 2] = max(-32768, min(32767, int(s0 + (2.0 * delta) / 3.0)))

    return struct.pack(f"<{len(out_samples)}h", *out_samples)


def resample_24k_to_8k(pcm16_24k: bytes) -> bytes:
    """
    Downsamples 24kHz 16-bit PCM to 8kHz 16-bit PCM (3:1 downsampling)
    using a 3-tap anti-aliasing boxcar moving average filter.
    Input: 480 samples (960 bytes) -> Output: 160 samples (320 bytes).
    """
    n_in = len(pcm16_24k) // 2
    n_out = n_in // 3
    if n_out == 0:
        return b""

    samples = struct.unpack(f"<{n_in}h", pcm16_24k)
    out_samples = [0] * n_out

    for i in range(n_out):
        idx = i * 3
        # Boxcar 3-tap average filter to suppress high-frequency aliasing
        avg = (samples[idx] + samples[idx + 1] + samples[idx + 2]) // 3
        out_samples[i] = max(-32768, min(32767, avg))

    return struct.pack(f"<{n_out}h", *out_samples)


def mulaw_8k_to_pcm16_24k(mulaw_bytes: bytes) -> bytes:
    """
    High-level ingress pipeline:
    Translates incoming Twilio audio (8kHz mu-law) to OpenAI Realtime format (24kHz PCM16).
    160 bytes mu-law (20ms) -> 960 bytes PCM16 (20ms).
    """
    pcm16_8k = mulaw_to_pcm16_8k(mulaw_bytes)
    return resample_8k_to_24k(pcm16_8k)


def pcm16_24k_to_mulaw_8k(pcm16_bytes: bytes) -> bytes:
    """
    High-level egress pipeline:
    Translates outgoing OpenAI Realtime audio (24kHz PCM16) to Twilio format (8kHz mu-law).
    960 bytes PCM16 (20ms) -> 160 bytes mu-law (20ms).
    """
    pcm16_8k = resample_24k_to_8k(pcm16_bytes)
    return pcm16_8k_to_mulaw(pcm16_8k)
