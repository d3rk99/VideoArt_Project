from pathlib import Path

from app.sessions.session_manager import SessionManager
from app.storage.file_manager import FileManager


def test_session_folder_creation(tmp_path: Path) -> None:
    fm = FileManager(
        live_capture_dir=tmp_path / "live",
        comfy_input_dir=tmp_path / "comfy",
        output_latest_dir=tmp_path / "latest",
        output_archive_dir=tmp_path / "archive",
    )
    manager = SessionManager(fm)
    session = manager.start_session()
    assert session.archive_dir is not None
    assert session.archive_dir.exists()
