from typing import Literal

VoiceState = Literal["IDLE", "LISTENING", "THINKING", "SPEAKING", "ERROR"]
ClientFrameType = Literal["audio_chunk", "audio_end", "cancel", "ping"]
ServerFrameType = Literal[
    "state",
    "partial",
    "final",
    "audio",
    "error",
    "pong",
]
