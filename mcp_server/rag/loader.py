from __future__ import annotations

import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

from echo.config import Config
from echo.settings import load_app_settings
from .errors import IndexingError

###########################################
# Get Raw Data And Extract
###########################################
MARKER_TIMEOUT_SECONDS = 1800
MARKER_HEARTBEAT_SECONDS = 5
MARKER_PERCENT_PATTERN = re.compile(r"(?:(?P<label>[^:\r\n]{2,80}):\s*)?(?P<percent>\d{1,3})%")
ANSI_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ProgressCallback = Callable[[str, dict], None]

# === Basic Loader class ===
class DataLoader(ABC):
    """Load raw text from one source file."""

    @abstractmethod
    def load_data(self, file_path: str, progress_callback: ProgressCallback | None = None) -> str:
        """Load raw data from the source."""
        pass

    @abstractmethod
    def get_supported_extensions(self) -> list[str]:
        """Return a list of supported file extensions."""
        pass

class MarkDownDataLoader(DataLoader):
    def load_data(self, file_path: str, progress_callback: ProgressCallback | None = None) -> str:
        return Path(file_path).read_text(encoding="utf-8")

    def get_supported_extensions(self):
        return [".txt", ".md"]

class PDFDataLoader(DataLoader):
    def load_data(self, file_path: str, progress_callback: ProgressCallback | None = None) -> str:
        marker_error = None
        marker_command = shutil.which("marker_single") if load_app_settings().use_marker_pdf_loader else None
        if marker_command:
            try:
                return _load_pdf_with_marker(Path(file_path), marker_command, progress_callback)
            except Exception as exc:
                marker_error = str(exc)

        if marker_error:
            _emit_progress(progress_callback, "marker_fallback", message="Marker failed; falling back to PyPDF2.")
        try:
            text = _load_pdf_with_pypdf2(Path(file_path))
        except Exception as exc:
            if marker_error:
                raise IndexingError("loading", f"PDF parsing failed. Marker failed ({marker_error}); PyPDF2 failed ({exc}).") from exc
            raise IndexingError("loading", f"PDF parsing failed: {exc}") from exc

        if text.strip():
            if marker_error:
                print(f"Marker failed; fell back to PyPDF2: {marker_error}")
            return text

        if marker_error:
            raise IndexingError("loading", f"Marker failed ({marker_error}) and PyPDF2 found no readable text.")
        raise IndexingError("loading", "PyPDF2 found no readable PDF text. Install marker-pdf for OCR and Markdown conversion.")

    def get_supported_extensions(self):
        return [".pdf"]

# === Loader Interface ===
class DataLoaderFactory:
    """Choose a loader from the file extension."""

    loaders = [MarkDownDataLoader(), PDFDataLoader()]
    DATA_DIR = Config.DATA_DIR
    
    @staticmethod
    def load(file_path: str, progress_callback: ProgressCallback | None = None) -> str:
        path = Path(file_path)
        if not path.exists():
            raise IndexingError("loading", f"File not found: {file_path}")

        _, ext = os.path.splitext(file_path)
        loader = DataLoaderFactory._get_loader(ext)
        data = loader.load_data(file_path, progress_callback=progress_callback)
        if not data.strip():
            raise IndexingError("loading", f"No readable text found in {Config.get_relative_path(file_path)}.")
        print(f"|{Config.get_relative_path(file_path)}| Data loaded using {loader.__class__.__name__}")
        return data
    
    @staticmethod
    def _get_loader(file_extension):
        file_extension = file_extension.lower()
        for loader in DataLoaderFactory.loaders:
            if file_extension in loader.get_supported_extensions():
                return loader
        raise IndexingError("loading", f"No loader found for extension: {file_extension}")


def _load_pdf_with_marker(
    file_path: Path,
    marker_command: str,
    progress_callback: ProgressCallback | None = None,
) -> str:
    with tempfile.TemporaryDirectory(prefix="echo-marker-") as output_dir:
        command = [
            marker_command,
            str(file_path),
            "--output_format",
            "markdown",
            "--disable_ocr",
            "--output_dir",
            output_dir,
        ]
        _emit_progress(progress_callback, "marker_started", message="Converting PDF with Marker...")
        _run_marker_command(command, progress_callback)

        candidates = [
            path
            for path in Path(output_dir).rglob("*")
            if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt"}
        ]
        if not candidates:
            raise RuntimeError("Marker finished but did not create markdown output.")

        output_path = max(candidates, key=lambda path: path.stat().st_size)
        text = output_path.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            raise RuntimeError("Marker produced empty markdown output.")
        _emit_progress(progress_callback, "marker_complete", message="Marker PDF conversion complete.", percent=100)
        return text


def _load_pdf_with_pypdf2(file_path: Path) -> str:
    from PyPDF2 import PdfReader

    reader = PdfReader(str(file_path))
    return "\n".join((page.extract_text() or "").strip() for page in reader.pages)


def _run_marker_command(command: list[str], progress_callback: ProgressCallback | None = None) -> str:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output_parts: list[str] = []
    output_queue: queue.Queue[str] = queue.Queue()
    reader = threading.Thread(target=_read_process_output, args=(process, output_queue), daemon=True)
    reader.start()

    started_at = time.monotonic()
    last_progress_at = started_at
    buffer = ""

    while process.poll() is None or not output_queue.empty():
        if time.monotonic() - started_at > MARKER_TIMEOUT_SECONDS:
            process.kill()
            raise RuntimeError(f"Marker timed out after {MARKER_TIMEOUT_SECONDS} seconds.")

        try:
            char = output_queue.get(timeout=0.2)
        except queue.Empty:
            if process.poll() is None and time.monotonic() - last_progress_at >= MARKER_HEARTBEAT_SECONDS:
                _emit_progress(progress_callback, "marker_progress", message="Marker is still converting the PDF...")
                last_progress_at = time.monotonic()
            continue

        output_parts.append(char)
        if char in "\r\n":
            last_progress_at = _emit_marker_line(buffer, progress_callback) or last_progress_at
            buffer = ""
        else:
            buffer += char
            if len(buffer) > 4000:
                last_progress_at = _emit_marker_line(buffer, progress_callback) or last_progress_at
                buffer = ""

    if buffer.strip():
        _emit_marker_line(buffer, progress_callback)
    reader.join(timeout=1)

    returncode = process.wait()
    output = "".join(output_parts)
    if returncode != 0:
        raise RuntimeError(_process_error(output, returncode))
    return output


def _read_process_output(process: subprocess.Popen[str], output_queue: queue.Queue[str]):
    if process.stdout is None:
        return
    while True:
        char = process.stdout.read(1)
        if not char:
            break
        output_queue.put(char)


def _emit_marker_line(line: str, progress_callback: ProgressCallback | None) -> float | None:
    text = _clean_process_line(line)
    if not text:
        return None
    match = MARKER_PERCENT_PATTERN.search(text)
    if match is None:
        return None

    percent = min(max(int(match.group("percent")), 0), 100)
    label = (match.group("label") or "Marker PDF conversion").strip()
    _emit_progress(
        progress_callback,
        "marker_progress",
        message=f"{label} ({percent}%)",
        percent=percent,
    )
    return time.monotonic()


def _clean_process_line(line: str) -> str:
    return ANSI_PATTERN.sub("", line).replace("\b", "").strip()


def _emit_progress(progress_callback: ProgressCallback | None, stage: str, **payload):
    if progress_callback is not None:
        progress_callback(stage, payload)


def _process_error(output: str, returncode: int) -> str:
    detail = _clean_process_line(output)
    return detail[-1000:] if detail else f"marker_single exited with code {returncode}."

if __name__ == "__main__":

    try:
        file_path = Config.TEST_FILE_PATH
        data = DataLoaderFactory.load(file_path)
        
    except ValueError as e:
        print(e)
