#!/usr/bin/env python3

""" telegrab

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
"""

import json
from json.decoder import JSONDecodeError
import os
import sys

import click
from telethon.sync import TelegramClient


def download_callback(recvbytes: int, total: int):
    """ blah """
    status = round(100 * (recvbytes / total), 2)
    print(f"Downloading {total} bytes - {status}%")


def select_channel(
    channel_name: str,
    telegram_client: TelegramClient,
    debug: bool = False,
    list_chats: bool = False,
):
    """ selects a dialog by name """
    selected_chat = False

    for dialog in telegram_client.iter_dialogs(archived=False):
        if list_chats:
            print(dialog.name)
        if debug:
            print(json.dumps(dialog.entity.to_dict(), default=str, indent=4))
        # if d.entity.title == 'vlada_661':
        if hasattr(dialog.entity, "title"):
            if dialog.entity.title == channel_name:
                selected_chat = dialog
                break
        else:
            if f"{dialog.entity.first_name} {dialog.entity.last_name}" == channel_name:
                selected_chat = dialog
                break
    return selected_chat


def load_config():
    """
    loads configuration things
    """
    homedir = os.path.expanduser("~/.config/")
    config_filename = f"{homedir}telegrab.json"
    if not os.path.exists(config_filename):
        print(f"Unable to find config file, looked in : {config_filename}")
        return False
    with open(config_filename, "r", encoding="utf8") as file_handle:
        try:
            config = json.load(file_handle)
        except JSONDecodeError as error_message:
            print(f"Failed to parse {config_filename}: {error_message}")
            return False

    missing_vars = []
    failed = False
    for var in ("session_id", "api_hash", "api_id"):  # "download_dir",
        if not config.get(var):
            failed = True
            missing_vars.append(var)
    if failed:
        print(
            f"Missing config fars in {config_filename}, please configure the following: {','.join(missing_vars)}"
        )
        return False
    return config


def check_download_dir(config_object, downdir, debug):
    """ checks for a valid download dir """
    if not config_object.get("download_dir", downdir):
        print("Please specify a download dir in config or command line options.")
        return False
    if debug:
        print(f"Download dir: {downdir}")

    download_dir = os.path.expanduser(config_object.get("download_dir", downdir))
    if not download_dir.endswith("/"):
        download_dir = f"{download_dir}/"

    if not os.path.exists(download_dir):
        print(f"The downloads dir {download_dir} does not exist, please create it.")
        return False
    return download_dir


@click.option("-d", "--debug", is_flag=True, default=False)
@click.option("-l", "--list-chats", type=bool, is_flag=True, default=False)
@click.option("--channel", default="")
@click.option(
    "-o",
    "--download-dir",
    type=click.Path(
        exists=True, allow_dash=False, writable=True, file_okay=False, dir_okay=True
    ),
)
@click.command()
# pylint: disable=too-many-branches
def cli(channel: str, list_chats: bool, debug: bool, download_dir: str):
    """ main cli interface """
    config = load_config()
    if not config:
        return False

    download_dir = check_download_dir(config, download_dir, debug)
    if not download_dir:
        return False

    with TelegramClient(
        session=config.get("session_id"),
        api_id=config.get("api_id"),
        api_hash=config.get("api_hash"),
        request_retries=5,
        connection_retries=5,
        retry_delay=30,
        auto_reconnect=True,
    ) as client:

        # grab channels
        selected_chat = select_channel(channel, client, debug, list_chats=True)
        if list_chats:
            return True

        # prompt the user for a channel
        while not selected_chat:
            channel = click.prompt("Please enter a channel")
            selected_chat = select_channel(
                channel.strip(), client, debug, list_chats=False
            )

        for messagedata in client.iter_messages(
            entity=selected_chat.entity,
        ):
            message = messagedata.to_dict()

            if message.get("media"):
                media = message.get("media")
                if debug:
                    print("Found an image")
                attributes = media.get("document", {}).get("attributes", {})
                filename = False
                for att in attributes:
                    if att.get("_") == "DocumentAttributeFilename":
                        filename = att.get("file_name")
                        break
                if not filename:
                    print(f"Couldn't find a filename? is post: {message.get('post')}")
                    if debug:
                        print("Dumping data:")
                        print(json.dumps(message, default=str))
                    continue
                print(f"Filename: {filename}")
                download_filename = f"{download_dir}{filename}"
                if os.path.exists(download_filename):
                    print(f"Skipping {filename}")
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
                        download_filename = (
                            f"{download_dir}{message.get('id')}-{filename}"
                        )
                        if os.path.exists(download_filename):
                            print(f"Skipping {filename}")
                            continue
                    else:
                        print("Skipped")
                        continue

                try:
                    client.download_media(
                        message=messagedata,
                        file=download_filename,
                        progress_callback=download_callback,
                    )
                except KeyboardInterrupt:
                    print(f"You interrupted this, removing {download_filename}")
                    os.remove(download_filename)
                    sys.exit()

            if debug:
                print(json.dumps(message, indent=4, default=str))


if __name__ == "__main__":
    # pylint: disable=no-value-for-parameter
    cli()
