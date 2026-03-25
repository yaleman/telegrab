import asyncio

import telegrab as tg
import telegrab.__main__ as cli
from telegrab.types import ConfigObject, FakeChatClient, FakeMessage


class FakeDialog:
    def __init__(self, name: str, dialog_id: int = 1, archived: bool = False):
        self.name = name
        self.id = dialog_id
        self.is_archived = archived
        self.entity = object()
        self.draft = None

    def to_dict(self):
        return {"name": self.name, "id": self.id, "is_archived": self.is_archived}


class AsyncPrompt:
    def __init__(self, result):
        self.result = result
        self.awaited = False

    async def ask_async(self):
        self.awaited = True
        return self.result


class FakeInnerClient:
    instances = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.connect_called = False
        self.start_called = False
        FakeInnerClient.instances.append(self)

    async def connect(self):
        self.connect_called = True

    def start(self):
        self.start_called = True
        return self

    async def iter_dialogs(self, archived=False):
        yield FakeDialog("alpha", dialog_id=101)

    async def iter_messages(self, entity):
        if False:
            yield entity


def test_get_chat_awaits_async_prompt(monkeypatch):
    dialogs = [FakeDialog("alpha"), FakeDialog("beta")]
    prompt = AsyncPrompt(dialogs[1])
    captured = {}

    monkeypatch.setattr(cli, "has_interactive_terminal", lambda: True)

    def fake_select(message, choices):
        captured["message"] = message
        captured["choices"] = choices
        return prompt

    monkeypatch.setattr(cli.questionary, "select", fake_select)

    selected = asyncio.run(cli.get_chat(FakeChatClient(dialogs)))

    assert selected is dialogs[1]
    assert prompt.awaited
    assert captured["message"] == "Please select a channel to grab:"
    assert len(captured["choices"]) == 2


def test_get_chat_skips_prompt_without_tty(monkeypatch):
    dialogs = [FakeDialog("alpha")]

    monkeypatch.setattr(cli, "has_interactive_terminal", lambda: False)
    monkeypatch.setattr(
        cli.questionary,
        "select",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("prompt should not run")
        ),
    )

    selected = asyncio.run(
        cli.get_chat(
            FakeChatClient(dialogs),
        )
    )

    assert selected is None


def test_check_download_dir_skips_prompt_without_tty(monkeypatch, tmp_path):
    missing_dir = tmp_path / "downloads"
    config = ConfigObject(
        session_id="session",
        api_hash="hash",
        api_id=123,
        download_dir=str(missing_dir),
    )

    monkeypatch.setattr(cli, "has_interactive_terminal", lambda: False)
    monkeypatch.setattr(
        cli.questionary,
        "confirm",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("prompt should not run")
        ),
    )

    result = asyncio.run(cli.check_download_dir(config, None))

    assert result is None
    assert not missing_dir.exists()


def test_inner_awaits_client_start(monkeypatch, tmp_path):
    FakeInnerClient.instances.clear()
    config = ConfigObject(
        session_id="session",
        api_hash="hash",
        api_id=123,
        download_dir=str(tmp_path),
    )

    monkeypatch.setattr(cli, "TelegramClient", FakeInnerClient)
    monkeypatch.setattr(cli, "get_session", lambda config_object: object())

    result = asyncio.run(
        cli.inner(
            config,
            all_channels=False,
            channel=None,
            channel_id=None,
            list_chats=True,
            debug=False,
            download_path=tmp_path,
        )
    )

    assert result is True
    assert len(FakeInnerClient.instances) == 1
    client = FakeInnerClient.instances[0]
    assert client.connect_called is True
    assert client.start_called is True


def test_process_message_downloads_photo_messages(monkeypatch, tmp_path):
    class FakePhotoMedia:
        pass

    monkeypatch.setattr(tg, "MessageMediaPhoto", FakePhotoMedia)
    message = FakeMessage(
        media=FakePhotoMedia(),
        message_dict={"media": {"photo": {"id": 1}}, "action": None, "_": "Message"},
        message_id=77,
        chat_title="photos",
        chat_id=555,
    )

    asyncio.run(tg.process_message(FakeChatClient([]), False, tmp_path, message))

    assert len(message.downloads) == 1
    assert message.downloads[0].endswith("photos (555)/20240102_030405_77.jpg")


def test_process_message_downloads_video_documents(monkeypatch, tmp_path):
    message = FakeMessage(
        media=object(),
        message_dict={
            "media": {
                "document": {
                    "mime_type": "video/mp4",
                    "attributes": [
                        {"_": "DocumentAttributeFilename", "file_name": "clip.mp4"},
                        {"_": "DocumentAttributeVideo"},
                    ],
                }
            },
            "action": None,
            "_": "Message",
        },
        message_id=88,
    )

    asyncio.run(tg.process_message(FakeChatClient([]), False, tmp_path, message))

    assert len(message.downloads) == 1
    assert message.downloads[0].endswith("clip.mp4")


def test_process_message_skips_stickers_with_info_log(monkeypatch, tmp_path):
    logs = []

    def fake_info(message, *args, **kwargs):
        logs.append(message.format(*args))

    monkeypatch.setattr(tg.logger, "info", fake_info)
    message = FakeMessage(
        media=object(),
        message_dict={
            "media": {
                "document": {
                    "mime_type": "image/webp",
                    "attributes": [{"_": "DocumentAttributeSticker"}],
                }
            },
            "action": None,
            "_": "Message",
        },
        message_id=89,
    )

    asyncio.run(tg.process_message(FakeChatClient([]), False, tmp_path, message))

    assert message.downloads == []
    assert any("Skipping sticker message" in entry for entry in logs)
