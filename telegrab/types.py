"""types things for telegrab"""

from datetime import datetime
from types import SimpleNamespace

from typing import Any, Optional
from pydantic import BaseModel


class ConfigObject(BaseModel):
    """configuration loader"""

    session_id: str
    api_hash: str
    api_id: int
    download_dir: Optional[str] = None


class FakeChatClient:
    def __init__(self, dialogs):
        self._dialogs = dialogs

    async def iter_dialogs(self, archived=False):
        for dialog in self._dialogs:
            yield dialog


class FakeMessage:
    download_called: int
    downloads: list[str]
    download_media: Any

    def __init__(
        self,
        message_id=1,
        date=None,
        media=None,
        message_dict=None,
        chat_title="alpha",
        chat_id=101,
        post=False,
    ):
        self.media = media
        self.id = message_id
        self._message_dict = message_dict or {}
        self.chat_id = chat_id
        self.chat = SimpleNamespace(title=chat_title)
        self.date = date or datetime(2024, 1, 2, 3, 4, 5)
        self.post = post
        self.download_called = 0
        self.downloads = []
        self.download_media = self._download_media

    def to_dict(self):
        return self._message_dict

    async def _download_media(self, file, progress_callback):
        self.download_called += 1
        self.downloads.append(file)
        return file
