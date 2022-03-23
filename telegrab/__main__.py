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

import json
from pathlib import Path
import sys
from typing import List, Optional

import click
from loguru import logger
import questionary
from telethon.sync import TelegramClient #type: ignore
from telethon.sessions import SQLiteSession #type: ignore
from telethon.tl.types import Dialog #type: ignore

from .types import ConfigObject

def download_callback(recvbytes: int, total: int) -> None:
    """ callback to print status of the download as it happens """
    status = round(100 * (recvbytes / total), 2)
    logger.debug(f"Downloading {total} bytes - {status}%")

def select_channel(
    channel_name: str,
    telegram_client: TelegramClient,
) -> Dialog:
    """ selects a dialog by name """
    selected_chat = False

    for dialog in telegram_client.iter_dialogs(archived=False):
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
    config = ConfigObject.parse_file(config_filename)
    return config

def check_download_dir(
    config_object: ConfigObject,
    download_dir: Optional[Path],
    ) -> Optional[Path]:
    """ checks for a valid download dir """
    if download_dir is not None:
        download_path = Path(download_dir).expanduser().resolve()
    elif config_object.download_dir is None :
        logger.info("Please specify a download dir in config or command line options.")
        return None
    else:
        download_path = Path(config_object.download_dir).expanduser().resolve()

    if not download_path.exists():
        logger.error(f"The downloads dir {download_path} does not exist, please create it.")
        return None
    if not download_path.is_dir():
        logger.error(f"The path {download_path} is not a directory! Bailing.")
        return None

    return download_path


def get_session(config_object: ConfigObject) -> SQLiteSession:
    """ returns a config session thing """
    config_path = Path("~/.config/telegrab/").expanduser()
    if not config_path.exists():
        config_path.mkdir()
    filename = Path(
        f"~/.config/telegrab/{config_object.session_id}"
    ).expanduser().resolve()
    return SQLiteSession(str(filename))

def get_chat(
    client: TelegramClient,
    channel: Optional[str],
    list_chats:bool,
    ) -> Optional[Dialog]:
    """ figure out which `Dialog` we're looking at"""
    selected_chat: Optional[Dialog] = None
    # grab channels
    if channel is not None:
        selected_chat = select_channel(channel, client)
        if list_chats:
            return True

    if selected_chat is None:
        # build a list of choices
        choices: List[questionary.Choice] = [ questionary.Choice(title=dialog.name,value=dialog)
            for dialog in
            client.iter_dialogs(archived=False)
            ]
        # prompt the user for a channel
        selected_chat = questionary.select(
            "What do you want to do?",
            choices=choices).ask()
    return selected_chat

@click.option("-d", "--debug", is_flag=True, default=False)
@click.option("-l", "--list-chats", type=bool, is_flag=True, default=False)
@click.option("--channel", help="Which channel to pull from")
@click.option(
    "-o",
    "--download-dir",
    type=click.Path(
        exists=True, allow_dash=False, writable=True, file_okay=False, dir_okay=True
    ),
)
@click.command()
# pylint: disable=too-many-branches
def cli(
    channel: Optional[str]=None,
    list_chats: bool=False,
    debug: bool=False,
    download_dir: Optional[Path]=None,
    ) -> bool:
    """ main cli interface """
    config = load_config()
    if not config:
        return False

    if not debug:
        logger.remove()
        logger.add(sys.stderr, level="INFO")

    download_path = check_download_dir(config_object=config, download_dir=download_dir)
    if not download_path:
        return False

    with TelegramClient(
        session=get_session(config),
        api_id=config.api_id,
        api_hash=config.api_hash,
        request_retries=5,
        connection_retries=5,
        retry_delay=30,
        auto_reconnect=True,
    ) as client:

        selected_chat = get_chat(client=client, channel=channel, list_chats=list_chats)
        if selected_chat is None:
            logger.error("Couldn't select a chat, bailing!")
            return False

        for messagedata in client.iter_messages(
            entity=selected_chat.entity,
        ):
            message = messagedata.to_dict()

            if message.get("media"):
                media = message.get("media")
                logger.debug("Found an image")
                attributes = media.get("document", {}).get("attributes", {})
                filename = False
                for att in attributes:
                    if att.get("_") == "DocumentAttributeFilename":
                        filename = att.get("file_name")
                        break
                if not filename:
                    logger.debug(f"Couldn't find a filename? is post: {message.get('post')}")
                    logger.debug("Dumping data:")
                    logger.debug(json.dumps(message, default=str))
                    continue
                logger.debug(f"Filename: {filename}")
                download_filename = Path(f"{download_path}/{filename}").expanduser().resolve()
                if download_filename.exists():
                    if not debug:
                        continue
                    if (
                        input(
                            f"Filename already exists: {download_filename}, do you want to try message id based option? "
                        )
                        .strip()
                        .lower()
                        == "y"
                    ):
                        download_filename = Path(f"{download_path}/{message.get('id')}-{filename}").expanduser().resolve()
                        if download_filename.exists():
                            logger.debug(f"Skipping {filename}")
                            continue
                    else:
                        logger.debug("Skipped")
                        continue

                try:
                    logger.info("Downloading {}", download_filename)
                    client.download_media(
                        message=messagedata,
                        file=download_filename,
                        progress_callback=download_callback,
                    )
                except KeyboardInterrupt:
                    logger.warning(f"You interrupted this, removing {download_filename}")
                    download_filename.unlink()
                    sys.exit()

            if debug:
                logger.debug(json.dumps(message, indent=4, default=str))
    return True

if __name__ == "__main__":
    cli()
