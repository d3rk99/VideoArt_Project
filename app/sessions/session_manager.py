"""Session lifecycle manager."""

from __future__ import annotations

import logging
from datetime import datetime

from app.sessions.models import SessionRecord
from app.storage.file_manager import FileManager


class SessionManager:
    """Creates and tracks the current active visitor session."""

    def __init__(self, file_manager: FileManager) -> None:
        self.file_manager = file_manager
        self.logger = logging.getLogger(__name__)
        self._active_session: SessionRecord | None = None

    @property
    def active_session(self) -> SessionRecord | None:
        return self._active_session

    def has_active_session(self) -> bool:
        return self._active_session is not None

    def start_session(self) -> SessionRecord:
        if self._active_session:
            raise RuntimeError("Session already active")
        session_id = datetime.utcnow().strftime("session_%Y%m%d_%H%M%S_%f")
        archive_dir = self.file_manager.create_session_dir(session_id)
        record = SessionRecord(session_id=session_id, archive_dir=archive_dir)
        self._active_session = record
        self.logger.info("Session started: %s", session_id)
        return record

    def end_session(self) -> None:
        if self._active_session:
            self.logger.info("Session ended: %s", self._active_session.session_id)
        self._active_session = None
