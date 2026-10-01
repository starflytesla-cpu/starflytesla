from fastapi import APIRouter

from app.deps import DB, AdminUser
from app.schemas import VoicePreviewIn, micros_to_usd, ok
from app.services import speech
from app.services.voices import VOICES

router = APIRouter(prefix="/api/voices", tags=["voices"])


@router.get("")
def list_voices(admin: AdminUser):
    return ok([v.out() for v in VOICES])


@router.post("/preview")
def preview(body: VoicePreviewIn, admin: AdminUser, db: DB):
    audio = speech.synthesize(db, admin, body.text, body.voice_id, speed=body.speed, source="voice_preview")
    return ok({"audio_url": audio["audio_url"], "cost_usd": micros_to_usd(audio["cost_micros"])}, "配音完成")
