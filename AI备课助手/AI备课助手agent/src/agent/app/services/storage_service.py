from pathlib import Path
from app.config import OUTPUT_ROOT, PUBLIC_BASE_URL
from app.utils.fs_utils import ensure_dir, sanitize_course_dir_name

class StorageService:
    def __init__(self) -> None:
        ensure_dir(OUTPUT_ROOT)

    def resolve_course_path(self, course_name: str, relative_path: str) -> Path:
        course_dir = sanitize_course_dir_name(course_name)
        return OUTPUT_ROOT / course_dir / relative_path

    def to_result_url(self, course_name: str, relative_path: str) -> str:
        course_dir = sanitize_course_dir_name(course_name)
        normalized = f"{course_dir}/{relative_path}".replace('\\', '/')
        if PUBLIC_BASE_URL:
            return f"{PUBLIC_BASE_URL.rstrip('/')}/{normalized}"
        return f"file://{(OUTPUT_ROOT / normalized).as_posix()}"

storage_service = StorageService()
