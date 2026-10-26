from app.config import JWT_SECRET
from fastapi import APIRouter, Form, Depends, HTTPException, Cookie
from jose import jwt, JWTError
from app.services.tts_service import text_to_speech
import os
import uuid
from pathlib import Path
from app.services.processor_service import get_llm_response, SUPPORTED_TARGET_LANGUAGES
from app.services.tts_service import MAX_SPEECH_LENGTH
from app.services.contact_translation import parse_contacts, translate_answer

router = APIRouter()

# Configuration that must match the Java server
SECRET_KEY = JWT_SECRET   # Must be identical to Java JwtUtil.SECRET
ALGORITHM = "HS256"
ISSUER = "simple-auth-server"         # Must be identical to Java JwtUtil.ISSUER


def get_current_user(
    access_token: str | None = Cookie(default=None, alias="ACCESS_TOKEN")
):
    """
    Reads the ACCESS_TOKEN(JWT) cookie issued by the Java server on port 8080
    and returns the current logged-in user information as a dependency.
    """
    if access_token is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated (no ACCESS_TOKEN cookie)",
        )

    try:
        payload = jwt.decode(
            access_token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            issuer=ISSUER,
        )
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    username = payload.get("username")

    if user_id is None or username is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid token payload",
        )

    # If needed, query the DB here and return an actual User object
    return {"id": user_id, "username": username}


# Path to the uploads folder for saving output files
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/")
def tts_endpoint(
    current_user: dict = Depends(get_current_user),
    text: str = Form(..., min_length=1, max_length=4096),
    target_language: str = Form("ko"),
    contacts: str = Form("[]", max_length=12000),
):
    # FastAPI runs this synchronous handler in its worker pool.
    if target_language not in SUPPORTED_TARGET_LANGUAGES:
        raise HTTPException(status_code=400, detail="지원하지 않는 번역 언어입니다.")
    if not text.strip():
        raise HTTPException(status_code=400, detail="읽을 내용이 없습니다.")
    try:
        original_contacts = parse_contacts(contacts)
    except ValueError:
        raise HTTPException(status_code=400, detail="연락처 표시 정보가 올바르지 않습니다.")
    try:
        # Preserve the original no-contact path for existing clients.
        if original_contacts:
            translated, translated_contacts = translate_answer(text, target_language, original_contacts)
        else:
            translated = text if target_language == "ko" else get_llm_response(text, target_language)
            translated_contacts = []
    except Exception:
        raise HTTPException(status_code=502, detail="번역을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.")
    if len(translated) > MAX_SPEECH_LENGTH:
        raise HTTPException(status_code=400, detail="번역문이 음성 길이 제한(4,096자)을 초과합니다. 답변을 짧게 나누어 주세요.")
    file_name = f"{uuid.uuid4()}_tts.mp3"
    output_path = Path(UPLOAD_DIR) / file_name
    try:
        text_to_speech(translated, str(output_path))
    except Exception:
        output_path.unlink(missing_ok=True)
        raise HTTPException(status_code=502, detail="음성을 생성하지 못했습니다. 잠시 후 다시 시도해 주세요.")
    return {
        "file_path": f"/uploads/{file_name}",
        "original_text": text,
        "translated_text": translated,
        "target_language": target_language,
        "original_contacts": [item.model_dump() for item in original_contacts],
        "translated_contacts": translated_contacts,
    }
