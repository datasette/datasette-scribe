from pydantic import BaseModel


class TranscriptionSummary(BaseModel):
    id: int
    url: str | None = None
    input_type: str = "url"
    filename: str | None = None
    model: str
    granularity: str
    submitted_at: str
    completed_at: str | None = None
    error: str | None = None
    entries_count: int = 0
    duration: float | None = None
    speakers_count: int = 0


class CollectionSummary(BaseModel):
    id: int
    name: str
    description: str = ""
    created_at: str = ""


class CollectionWithTranscriptions(BaseModel):
    id: int
    name: str
    description: str = ""
    created_at: str = ""
    transcriptions: list[TranscriptionSummary] = []


# /$db/-/scribe — main listing page showing all transcriptions for a database
class ScribePageData(BaseModel):
    database_name: str
    collections: list[CollectionWithTranscriptions] = []
    uncollected_transcriptions: list[TranscriptionSummary] = []


class TranscriptionEntry(BaseModel):
    id: int
    start: float
    end: float
    speaker_id: str | None = None
    text: str
    original_speaker_id: str | None = None
    original_text: str | None = None


class TranscriptionSpeaker(BaseModel):
    id: int
    name: str
    is_original: bool = True
    used_in_other_transcriptions: bool = False


class TranscriptionEdit(BaseModel):
    id: int
    operation: str
    detail: str  # JSON string
    created_at: str
    entry_id: int | None = None


# /$db/-/scribe/transcription/$id — detail page for a single transcription with entries
class TranscriptionDetailPageData(BaseModel):
    database_name: str
    transcription: TranscriptionSummary
    audio_url: str | None = None
    entries: list[TranscriptionEntry] = []
    speakers: list[TranscriptionSpeaker] = []
    all_speakers: list[TranscriptionSpeaker] = []
    edits: list[TranscriptionEdit] = []
    collection: CollectionSummary | None = None
    all_collections: list[CollectionSummary] = []


# /$db/-/scribe/new — form to submit a new audio URL for transcription
class NewTranscriptionPageData(BaseModel):
    database_name: str
    collections: list[CollectionSummary] = []


class CollectionSpeakerStat(BaseModel):
    name: str
    entry_count: int
    transcription_count: int


# /$db/-/scribe/collections/$id — detail page for a single collection
class CollectionDetailPageData(BaseModel):
    database_name: str
    collection: CollectionSummary
    transcriptions: list[TranscriptionSummary] = []
    available_transcriptions: list[TranscriptionSummary] = []
    speakers: list[CollectionSpeakerStat] = []


# POST /-/api/scribe/new — submit a new audio URL for transcription
class NewTranscriptionRequest(BaseModel):
    database: str
    url: str | None = None
    file_data: str | None = None  # base64-encoded audio
    filename: str | None = None
    content_type: str | None = None
    collection_id: int | None = None


class NewTranscriptionResponse(BaseModel):
    ok: bool
    id: int | None = None
    entries_count: int | None = None
    error: str | None = None


# Edit API request/response models
class EditEntryRequest(BaseModel):
    database: str
    text: str | None = None
    speaker_id: str | None = None


class CreateSpeakerRequest(BaseModel):
    database: str
    name: str


class CombineSpeakersRequest(BaseModel):
    database: str
    from_speaker: str
    to_speaker: str


class RenameSpeakerRequest(BaseModel):
    database: str
    new_name: str


class DeleteSpeakerRequest(BaseModel):
    database: str
    speaker_name: str


class EditResponse(BaseModel):
    ok: bool
    error: str | None = None


# Collection API request models
class CreateCollectionRequest(BaseModel):
    database: str
    name: str
    description: str = ""


class UpdateCollectionRequest(BaseModel):
    database: str
    name: str
    description: str = ""


class CollectionTranscriptionRequest(BaseModel):
    database: str
    transcription_id: int


__exports__ = [
    ScribePageData,
    TranscriptionDetailPageData,
    NewTranscriptionPageData,
    CollectionDetailPageData,
]
