""" types things for telegrab """

from typing import Optional
from pydantic import BaseModel

class ConfigObject(BaseModel):
    """ configuration loader """
    session_id: str
    api_hash: str
    api_id: str
    download_dir: Optional[str]
