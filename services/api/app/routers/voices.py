from fastapi import APIRouter

from app.deps import DB, AdminUser
from app.errors import AppError
from app.schemas import VoicePreviewIn, micros_to_usd, ok
from app.services import ai_provider, speech
from app.services.voices import ALL_VOICES, engine_for_model

router = APIRouter(prefix="/api/voices", tags=["voices"])


@router.get("")
def list_voices(admin: AdminUser, db: DB):
    try:
        active = engine_for_model(ai_provider.default_model(db, admin.tenant_id, "tts").model_key)
    except AppError:
        active = None
    return ok({"active_engine": active, "items": [v.out() for v in ALL_VOICES]})


@router.post("/{voice_id}/sample")
def sample(voice_id: str, admin: AdminUser, db: DB):
    result = speech.voice_sample(db, admin, voice_id)
    return ok({"audio_url": result["audio_url"], "cost_usd": micros_to_usd(result["cost_micros"])})


@router.post("/preview")
def preview(body: VoicePreviewIn, admin: AdminUser, db: DB):
    audio = speech.synthesize(db, admin, body.text, body.voice_id, speed=body.speed, source="voice_preview")
    return ok({"audio_url": audio["audio_url"], "cost_usd": micros_to_usd(audio["cost_micros"])}, "配音完成")
