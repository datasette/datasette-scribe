import httpx
import os

from pydantic import BaseModel

TRANSCRIPTION_URL = "https://api.mistral.ai/v1/audio/transcriptions"


class TranscriptionSegment(BaseModel):
    text: str
    start: float
    end: float
    speaker_id: str | None = None
    type: str | None = None


class TranscriptionUsage(BaseModel):
    prompt_audio_seconds: int | None = None
    prompt_tokens: int | None = None
    total_tokens: int | None = None
    completion_tokens: int | None = None
    num_cached_tokens: int | None = None


class TranscriptionResponse(BaseModel):
    model: str
    text: str
    language: str | None = None
    segments: list[TranscriptionSegment] = []
    usage: TranscriptionUsage | None = None
    finish_reason: str | None = None


async def transcribe(
    file_url: str | None = None,
    *,
    file_data: bytes | None = None,
    filename: str | None = None,
    model: str = "voxtral-mini-2602",
    diarize: bool = True,
    timestamp_granularities: list[str] | None = None,
    api_key: str | None = None,
) -> TranscriptionResponse:
    if api_key is None:
        api_key = os.environ["MISTRAL_API_KEY"]
    if timestamp_granularities is None:
        timestamp_granularities = ["segment"]

    data = {
        "model": model,
        "diarize": str(diarize).lower(),
    }
    for granularity in timestamp_granularities:
        data["timestamp_granularities"] = granularity

    files = None
    if file_data is not None:
        files = {"file": (filename or "audio.mp3", file_data)}
    else:
        data["file_url"] = file_url or ""

    async with httpx.AsyncClient() as client:
        response = await client.post(
            TRANSCRIPTION_URL,
            headers={"x-api-key": api_key},
            data=data,
            files=files,
            timeout=300,
        )
        response.raise_for_status()
        return TranscriptionResponse.model_validate(response.json())
