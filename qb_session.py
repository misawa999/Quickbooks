"""COM connection/session lifecycle for the QuickBooks Desktop SDK.

Windows + QuickBooks Desktop + QBSDK (QBXMLRP2) only. The pywin32 import is
deferred so the rest of this tool (schema validation, dry-run reporting,
tests) works cross-platform without QuickBooks installed.
"""
from __future__ import annotations

import sys
from typing import Optional

APP_NAME = "SimpleJournalImporter"
QB_LOCAL_QBD = 1  # OpenConnection2 connection type: local QuickBooks Desktop
QB_FILE_OPEN_DO_NOT_CARE = 2  # BeginSession mode: use whatever company file is open


class QBSessionError(RuntimeError):
    """Raised for anything that stops us from talking to QuickBooks."""


class QBSession:
    def __init__(self, company_file: str = ""):
        self.company_file = company_file
        self._rp = None
        self._ticket: Optional[str] = None

    def __enter__(self) -> "QBSession":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def open(self) -> None:
        if sys.platform != "win32":
            raise QBSessionError(
                "QuickBooks COM connectivity requires Windows with QuickBooks "
                "Desktop and the QBSDK installed. This machine is not Windows."
            )
        try:
            import win32com.client
        except ImportError as e:
            raise QBSessionError("pywin32 is not installed. Run: pip install pywin32") from e

        try:
            self._rp = win32com.client.Dispatch("QBXMLRP2.RequestProcessor")
            self._rp.OpenConnection2("", APP_NAME, QB_LOCAL_QBD)
            self._ticket = self._rp.BeginSession(self.company_file, QB_FILE_OPEN_DO_NOT_CARE)
        except Exception as e:
            raise QBSessionError(f"failed to open QuickBooks session: {e}") from e

    def close(self) -> None:
        if self._rp is not None:
            try:
                if self._ticket is not None:
                    self._rp.EndSession(self._ticket)
            finally:
                self._rp.CloseConnection()
        self._rp = None
        self._ticket = None

    def process(self, request_xml: str) -> str:
        if self._rp is None or self._ticket is None:
            raise QBSessionError("session is not open")
        return self._rp.ProcessRequest(self._ticket, request_xml)
