"""types things for telegrab"""

from typing import Optional
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
