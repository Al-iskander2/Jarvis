
import math
import struct
from typing import List

class SimpleVAD:
    """
    A very simple energy-based VAD (Voice Activity Detection).
    """
    def __init__(self, sample_rate=16000, frame_duration_ms=30, threshold=500):
        self.sample_rate = sample_rate
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)
        self.threshold = threshold
        self.speech_frames = 0
        self.silence_frames = 0
        self.is_speech = False

    def is_speech_frame(self, frame: bytes) -> bool:
        # Calculate RMS amplitude
        # Assume 16-bit PCM
        count = len(frame) // 2
        if count == 0:
            return False
            
        shorts = struct.unpack(f"{count}h", frame)
        sum_squares = sum(s * s for s in shorts)
        rms = math.sqrt(sum_squares / count)
        
        return rms > self.threshold

    def process_chunk(self, chunk: bytes) -> bool:
        """
        Returns True if speech is detected in this chunk.
        """
        return self.is_speech_frame(chunk)
