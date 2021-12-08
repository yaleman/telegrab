#!/usr/bin/env python3

import json
import os
import sys

import click
from telethon.sync import TelegramClient

import config

api_id = config.api_id
api_hash = config.api_hash
session_id = config.session_id


def download_callback(recvbytes: int, total: int):
    """ blah """
    status = round(100 * (recvbytes / total), 2)
    print(f"Downloading {total} bytes - {status}%")

def select_channel(channel_name: str, telegram_client: TelegramClient, debug: bool=False, list_chats: bool=False):
    """ selects a dialog by name """
    selected_chat = False

    for d in telegram_client.iter_dialogs(archived=False):
        if list_chats:
            print(d.name)
        if debug:
            print(json.dumps(d.entity.to_dict(), default=str, indent=4))
        # if d.entity.title == 'vlada_661':
        if hasattr(d.entity, "title"):
            if d.entity.title == channel_name:
                selected_chat = d
                break
        else:
            if f"{d.entity.first_name} {d.entity.last_name}" == channel_name:
                selected_chat = d
                break
    return selected_chat


@click.option("-d", "--debug", is_flag=True, default=False)
@click.option("-l", "--list-chats", type=bool, is_flag=True, default=False)
@click.option("--channel", default="")
@click.command()
def cli(channel: str, list_chats: bool, debug: bool):
    with TelegramClient(
        session=session_id,
        api_id=api_id,
        api_hash=api_hash,
        request_retries=5,
        connection_retries=5,
        retry_delay=30,
        auto_reconnect=True,
    ) as client:

        # grab channels

        selected_chat = select_channel(channel, client, debug, list_chats=True)
        if list_chats:
            return True

        while not selected_chat:
            channel = click.prompt("Please enter a channel")
            selected_chat = select_channel(channel.strip(), client, debug, list_chats=False)


        for messagedata in client.iter_messages(
            entity=selected_chat.entity,
            # limit=1,
        ):
            message = messagedata.to_dict()

            if message.get("media"):
                media = message.get("media")
                # print("Found an image")
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
                download_filename = f"downloads/{filename}"
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
                        download_filename = f"downloads/{message.get('id')}-{filename}"
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

            # print(json.dumps(message, indent=4,default=str))


if __name__ == "__main__":
    cli()
