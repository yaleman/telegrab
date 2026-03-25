#!/usr/bin/env python3

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

import asyncio
from datetime import datetime, timedelta, timezone

import json
from pathlib import Path
import sys
from typing import List, Optional

import click
from loguru import logger
import questionary
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.sessions import SQLiteSession
from telethon.tl.custom.dialog import Dialog

from .types import ConfigObject, FakeChatClient
from . import process_message
from .interactive import has_interactive_terminal


async def get_channel_by_id(
    channel_id: int,
    telegram_client: TelegramClient | FakeChatClient,
) -> Optional[Dialog]:
    """grabs the `Dialog` object by id"""
    selected_chat: Optional[Dialog] = None

    async for dialog in telegram_client.iter_dialogs(archived=False):
        logger.debug(
            "Channel data: {}",
            json.dumps(dialog.entity.to_dict(), default=str, indent=4),
        )
        if dialog.id == channel_id:
            selected_chat = dialog
            break
    return selected_chat


async def get_channel_by_name(
    channel_name: str,
    telegram_client: TelegramClient | FakeChatClient,
) -> Optional[Dialog]:
    """grabs the `Dialog` object by name"""
    selected_chat: Optional[Dialog] = None

    async for dialog in telegram_client.iter_dialogs(archived=False):
        logger.debug(json.dumps(dialog.entity.to_dict(), default=str, indent=4))
        if hasattr(dialog.entity, "title"):
            if dialog.entity.title == channel_name:
                selected_chat = dialog
                break
        else:
            if f"{dialog.entity.first_name} {dialog.entity.last_name}" == channel_name:
                selected_chat = dialog
                break
    return selected_chat


def load_config() -> Optional[ConfigObject]:
    """
    loads configuration things
    """
    config_filename = Path("~/.config/telegrab.json").expanduser().resolve()
    if not config_filename.exists():
        logger.error(f"Unable to find config file, looked in : {config_filename}")
        return None
    config = ConfigObject.model_validate_json(config_filename.read_text())
    return config


async def check_download_dir(
    config_object: ConfigObject,
    download_dir: Optional[Path],
) -> Optional[Path]:
    """checks for a valid download dir"""
    if download_dir is not None:
        download_path = Path(download_dir).expanduser().resolve()
    elif config_object.download_dir is None:
        logger.info("Please specify a download dir in config or command line options.")
        return None
    else:
        download_path = Path(config_object.download_dir).expanduser().resolve()

    if not download_path.exists():
        if not has_interactive_terminal():
            logger.error(
                "The downloads dir {} does not exist and no interactive terminal is available.",
                download_path,
            )
            return None

        create_dir = await questionary.confirm(
            f"The downloads dir {download_path} does not exist, do you want to create it?"
        ).ask_async()
        if create_dir:
            download_path.mkdir(parents=True, exist_ok=True)
            return download_path

        else:
            logger.error(
                f"The downloads dir {download_path} does not exist, please create it."
            )
        return None
    if not download_path.is_dir():
        logger.error(f"The path {download_path} is not a directory! Bailing.")
        return None

    return download_path


def get_session(config_object: ConfigObject) -> SQLiteSession:
    """returns a config session thing"""
    config_path = Path("~/.config/telegrab/").expanduser()
    if not config_path.exists():
        config_path.mkdir()
    filename = (
        Path(f"~/.config/telegrab/{config_object.session_id}").expanduser().resolve()
    )
    return SQLiteSession(str(filename))


async def get_chat(
    client: TelegramClient | FakeChatClient,
    channel: Optional[str] = None,
    channel_id: Optional[int] = None,
    list_chats: bool = False,
) -> Optional[Dialog]:
    """figure out which `Dialog` we're looking at"""
    selected_chat: Optional[Dialog] = None
    if list_chats:
        async for dialog in client.iter_dialogs(archived=False):
            dialog: Dialog = dialog
            msg = f"{dialog.name} (id: {dialog.id})"
            if dialog.is_archived:
                msg += " [archived]"
            logger.info(msg)
        return None
    # grab channels
    if channel is not None:
        selected_chat = await get_channel_by_name(channel, client)

    if selected_chat is None and channel_id is not None:
        selected_chat = await get_channel_by_id(channel_id, client)

    if selected_chat is None:
        if not has_interactive_terminal():
            logger.error(
                "No channel was selected and no interactive terminal is available."
            )
            return None

        # build a list of choices
        choices: List[questionary.Choice] = []

        async for dialog in client.iter_dialogs(archived=False):
            if not dialog.name or not dialog.name.strip():
                logger.debug(
                    "Dialog with id {} has no name, dumping data: \n{}",
                    dialog.id,
                    json.dumps(dialog.to_dict(), default=str, indent=4),
                )
                if dialog.draft is not None:
                    logger.debug(
                        "Draft message: \n{}",
                        json.dumps(dialog.draft.to_dict(), default=str, indent=4),
                    )
                    continue
                name = str(dialog)
            else:
                logger.debug(json.dumps(dialog.to_dict(), default=str, indent=4))
                name = f"{dialog.name} (id: {dialog.id})"
            choices.append(questionary.Choice(title=name, value=dialog))
        # prompt the user for a channel
        selected_chat = await questionary.select(
            "Please select a channel to grab:", choices=choices
        ).ask_async()
    return selected_chat


async def inner(
    config: ConfigObject,
    all_channels: bool,
    channel: Optional[str],
    channel_id: Optional[int],
    list_chats: bool,
    debug: bool,
    download_path: Optional[Path],
    dry_run: bool = False,
    min_date: Optional[datetime] = None,
) -> bool:
    download_path = await check_download_dir(
        config_object=config, download_dir=download_path
    )
    if not download_path:
        return False

    client = TelegramClient(
        session=get_session(config),
        api_id=int(config.api_id),
        api_hash=config.api_hash,
        request_retries=5,
        connection_retries=5,
        retry_delay=30,
        auto_reconnect=True,
    )
    await client.connect()
    client.start()

    if all_channels:
        channels_to_process: list[Dialog] = []
        async for dialog in client.iter_dialogs(archived=False):
            channels_to_process.append(dialog)
    else:
        selected_chat = await get_chat(
            client=client, channel=channel, channel_id=channel_id, list_chats=list_chats
        )
        if list_chats:
            return True
        if selected_chat is None and not all_channels:
            logger.error("Couldn't select a chat, bailing!")
            return False
        channels_to_process = [selected_chat]

    for current_chat in channels_to_process:
        assert current_chat is not None
        logger.debug(
            "Selected chat: {} starting to process messages...",
            json.dumps(current_chat.id, default=str, indent=4),
        )
        try:
            async for messagedata in client.iter_messages(
                entity=current_chat.entity,
            ):
                if min_date is not None:
                    if messagedata.date is not None and messagedata.date < min_date:
                        logger.info(
                            "Reached message limit (date), stopping for this channel."
                        )
                        break
                await process_message(
                    client, debug, download_path, messagedata, dry_run=dry_run
                )
        except FloodWaitError as e:
            logger.warning(
                f"Rate limit hit during message iteration, sleeping for {e.seconds} seconds"
            )
            await asyncio.sleep(e.seconds)
            # We can't easily resume the iterator from the same spot without complexity.
            logger.error("Stopping processing for this channel due to rate limit.")

    return True


@click.option("-d", "--debug", is_flag=True, default=False)
@click.option("-l", "--list-chats", type=bool, is_flag=True, default=False)
@click.option("--channel", help="Which channel to pull from")
@click.option(
    "--all-channels",
    type=bool,
    is_flag=True,
    default=False,
    help="Pull from all channels",
)
@click.option("--channel-id", type=int, help="Which channel ID to pull from")
@click.option(
    "-o",
    "--download-dir",
    type=click.Path(
        exists=False, allow_dash=False, writable=True, file_okay=False, dir_okay=True
    ),
)
@click.option("--dry-run", is_flag=True, default=False, help="Simulate download")
@click.option(
    "--since", help="Process messages since this ISO 8601 date (e.g. 2023-01-01)"
)
@click.option("--days", type=int, help="Process messages from the last X days")
@click.command()
def cli(
    all_channels: Optional[bool] = False,
    channel: Optional[str] = None,
    channel_id: Optional[int] = None,
    list_chats: bool = False,
    debug: bool = False,
    download_dir: Optional[Path] = None,
    dry_run: bool = False,
    since: Optional[str] = None,
    days: Optional[int] = None,
) -> bool:
    """main cli interface"""
    config = load_config()
    if not config:
        return False

    if not debug:
        logger.remove()
        logger.add(sys.stderr, level="INFO")

    min_date = None
    if since:
        try:
            # Basic ISO parsing
            min_date = datetime.fromisoformat(since)
            if min_date.tzinfo is None:
                min_date = min_date.replace(tzinfo=timezone.utc)
        except ValueError:
            logger.error(
                "Invalid date format for --since. Please use ISO 8601 (e.g. 2023-01-01)"
            )
            return False
    elif days:
        min_date = datetime.now(timezone.utc) - timedelta(days=days)

    return asyncio.run(
        inner(
            config,
            all_channels or False,
            channel,
            channel_id,
            list_chats,
            debug,
            download_dir,
            dry_run=dry_run,
            min_date=min_date,
        )
    )


if __name__ == "__main__":
    sys.exit(0 if cli() else 1)
