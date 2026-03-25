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

from telethon.tl.custom.message import Message
from telethon.tl.types import MessageMediaPhoto
from pathlib import Path
import sys
from typing import Any, Dict

from loguru import logger
import questionary
from telethon.sync import TelegramClient

from .interactive import has_interactive_terminal


def download_callback(recvbytes: int, total: int) -> None:
    """callback to print status of the download as it happens"""
    status = round(100 * (recvbytes / total), 2)
    logger.info(f"Downloading {total} bytes - {status}%")


async def process_message(
    client: TelegramClient,
    debug: bool,
    download_path: Path,
    messagedata: Message,
) -> None:
    """handles an individual message"""
    message_dict: Dict[str, Any] = messagedata.to_dict()
    media = message_dict.get("media")
    action = message_dict.get("action")

    if isinstance(messagedata.media, MessageMediaPhoto):
        assert messagedata.id is not None
        assert messagedata.date is not None
        assert messagedata.chat is not None

        chat_name = (
            f"{messagedata.chat.title} ({messagedata.chat_id})"
            if hasattr(messagedata.chat, "title")
            else f"chat_{messagedata.chat_id}"
        )

        filename = (
            f"{chat_name}/"
            + messagedata.date.strftime("%Y%m%d_%H%M%S")
            + f"_{messagedata.id}.jpg"
        )
        logger.debug("Found a photo message: {} filename: {}", messagedata.id, filename)
        file_path = download_path / filename
        if not file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
        if file_path.exists():
            logger.info("File already exists: {}, skipping download.", file_path)
            return
        await messagedata.download_media(
            file=str(file_path), progress_callback=download_callback
        )
        logger.success("Successfully downloaded {}", file_path)
        return

    if isinstance(action, dict) and action.get("_") in [
        "MessageActionPinMessage",
        "MessageActionUnpinMessage",
    ]:
        logger.info("Skipping pinned/unpinned message {}", messagedata.id)
        return
    if isinstance(action, dict) and action.get("_") in ["MessageActionChannelCreate"]:
        logger.info("Skipping channel creation message {}", messagedata.id)
        return
    if message_dict.get("_") in ["Message"] and messagedata.post:
        logger.info("Skipping channel post {}", messagedata.id)
        return

    if not isinstance(media, dict):
        logger.info("Skipping message {} without downloadable media", messagedata.id)
        return

    document = media.get("document")
    photo = media.get("photo")
    if photo is not None:
        logger.info("Skipping photo media that was not recognized as a photo message")
        return
    if document is None:
        logger.info(
            "Skipping unsupported media on message {}",
            messagedata.id,
        )
        return

    attributes = document.get("attributes") or []
    if any(att.get("_") == "DocumentAttributeSticker" for att in attributes):
        logger.info("Skipping sticker message {}", messagedata.id)
        return

    mime_type = document.get("mime_type") or ""
    is_video = mime_type.startswith("video/") or any(
        att.get("_") == "DocumentAttributeVideo" for att in attributes
    )
    is_image = mime_type.startswith("image/")
    if not (is_video or is_image):
        logger.info(
            "Skipping unsupported document message {} ({})",
            messagedata.id,
            mime_type or "unknown",
        )
        return

    filename = None
    for att in attributes:
        if att.get("_") == "DocumentAttributeFilename":
            filename = att.get("file_name")
            break
    if not filename:
        if mime_type:
            suffix = mime_type.split("/", 1)[1]
            if suffix == "jpeg":
                suffix = "jpg"
            filename = f"{messagedata.id}.{suffix}"
        else:
            filename = f"{messagedata.id}"

    logger.debug("Filename: {}", filename)
    download_filename = Path(download_path / filename).expanduser().resolve()
    if download_filename.exists():
        if not debug:
            return

        if not has_interactive_terminal():
            logger.warning(
                "Filename already exists: {} and no interactive terminal is available, skipping.",
                download_filename,
            )
            return

        user_response = await questionary.text(
            f"Filename already exists: {download_filename}, do you want to try message id based option? "
        ).ask_async()
        if user_response is not None and user_response.strip().lower() == "y":
            download_filename = (
                Path(f"{download_path}/{message_dict.get('id')}-{filename}")
                .expanduser()
                .resolve()
            )
            if download_filename.exists():
                logger.debug(f"Skipping {filename}")
                return
        else:
            logger.debug("Skipped")
            return

    try:
        logger.info("Downloading {}", download_filename)
        await messagedata.download_media(
            file=str(download_filename),
            progress_callback=download_callback,
        )
        logger.success("Successfully downloaded {}", download_filename)
    except KeyboardInterrupt:
        logger.warning(f"You interrupted this, removing {download_filename}")
        download_filename.unlink()
        sys.exit()
