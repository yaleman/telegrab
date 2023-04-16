"""
telegrab

A tool for downloading files from telegram channels.

## Configuration

It's a JSON file in `~/.config/telegrab.json` or your OS equivalent.

Generate a session id using something like `openssl rand -hex 32` - keeping it stable means you don't have to log in each time.

```json
{
"session_id" : "asdfasdfasfsfasd",
"api_id" : "123456",
"api_hash" : "asdfasdfasdfasdf"
}

```

You specify the `download_dir` in config or on the command line (with `--download-dir`).

## Session storage

It'll take the "session_id" value and store session data in `~/.config/telegrab/{session_id}`

"""

import json
from pathlib import Path
import sys
from typing import Any, Dict, Optional
import asyncio.exceptions
from loguru import logger
import questionary
from telethon.sync import TelegramClient #type: ignore

class BailOut(Exception):
    """ bailing out """

def download_callback(recvbytes: int, total: int) -> None:
    """ callback to print status of the download as it happens """
    status = round(100 * (recvbytes / total), 2)
    logger.info(f"Downloading {total} bytes - {status}%")

def process_message(
    client: TelegramClient,
    debug: bool,
    download_path: Path,
    messagedata: Any,
    search: Optional[str],
    ) -> None:
    """ handles an individual message """
    message: Dict[str, Any] = messagedata.to_dict()
    if search is not None:
        if search.lower() not in str(message).lower():
            logger.debug("Skipping this one, doesn't match search")
            return
    if 'reactions' in message:
        del message['reactions']
    if "media" in message and message["media"] is not None:
        media = message["media"]
        logger.debug("Found an image")
        logger.debug(json.dumps(message, default=str, indent=4))
        if "document" not in media:
            logger.error(
                "Couldn't find 'document' field in media message, dumping: \n{}",
                json.dumps(message, default=str, indent=4),
                )
            return
        if "attributes" not in media["document"]:
            logger.error(
                "Couldn't find document 'attributes' field in media message, dumping: \n{}",
                json.dumps(media, default=str, indent=4),
                )
            return
        attributes = media["document"]["attributes"]
        filename = False
        for att in attributes:
            if att.get("_") == "DocumentAttributeFilename":
                filename = att.get("file_name")
                break
        if not filename:
            logger.debug(f"Couldn't find a filename? is post: {message.get('post')}")
            logger.debug("Dumping data:")
            logger.debug(json.dumps(message, default=str))
            return
        logger.debug(f"Filename: {filename}")
        download_filename = Path(f"{download_path}/{filename}").expanduser().resolve()
        if download_filename.exists():
            if not debug:
                return

            user_response =  questionary.text(
                    f"Filename already exists: {download_filename}, do you want to try message id based option? ").ask()
            if user_response is not None and user_response.strip().lower() == "y":
                download_filename = Path(f"{download_path}/{message.get('id')}-{filename}").expanduser().resolve()
                if download_filename.exists():
                    logger.debug(f"Skipping {filename}")
                    return
            else:
                logger.debug("Skipped")
                return

        try:
            confirmation = questionary.confirm(f"Download {filename}?").ask()
            if confirmation:
                logger.info("Downloading {}", download_filename)

                try:
                    client.download_media(
                        message=messagedata,
                        file=download_filename,
                        progress_callback=download_callback,
                    )
                except asyncio.exceptions.IncompleteReadError:
                    pass
                logger.success("Successfully downloaded {}", download_filename)
            elif confirmation is None:
                raise BailOut
        except KeyboardInterrupt:
            logger.warning(f"You interrupted this, removing {download_filename}")
            download_filename.unlink()
            sys.exit()
    else:
        logger.debug(json.dumps(message, indent=4, default=str))