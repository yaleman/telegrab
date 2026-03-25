from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from telethon.errors import FloodWaitError

from telegrab import process_message
from telegrab.__main__ import inner
from telegrab.types import ConfigObject, FakeMessage


@pytest.mark.asyncio
async def test_dry_run_skips_download(tmp_path):
    # Setup
    msg = FakeMessage(
        message_id=1, date=datetime.now(timezone.utc), media=None, message_dict={}
    )

    # We need to satisfy isinstance(messagedata.media, MessageMediaPhoto)
    # We can patch the class in telegrab module
    with patch("telegrab.MessageMediaPhoto"):
        # The mock will match isinstance check if we make msg.media an instance of it?
        # Actually patching the class name in the module makes the module use the Mock.
        # But we need msg.media to be an instance of that Mock.

        # Alternative: Create a dummy class that looks like MessageMediaPhoto
        class DummyPhoto:
            pass

        with patch("telegrab.MessageMediaPhoto", DummyPhoto):
            msg.media = DummyPhoto()
            msg._message_dict["media"] = {"photo": {}}

            # Test Dry Run = True
            await process_message(MagicMock(), False, tmp_path, msg, dry_run=True)
            assert msg.download_called == 0

            # Test Dry Run = False
            await process_message(MagicMock(), False, tmp_path, msg, dry_run=False)
            assert msg.download_called == 1


@pytest.mark.asyncio
async def test_rate_limit_handling(tmp_path):
    class DummyPhoto:
        pass

    msg = FakeMessage(
        message_id=1, date=datetime.now(timezone.utc), media=None, message_dict={}
    )
    msg.media = DummyPhoto()

    with (
        patch("telegrab.MessageMediaPhoto", DummyPhoto),
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        # Mock download_media to raise FloodWaitError first, then succeed
        # FloodWaitError(request, capture)
        error = FloodWaitError(None, 10)
        msg.download_media = AsyncMock(side_effect=[error, "path"])

        await process_message(MagicMock(), False, tmp_path, msg)

        assert msg.download_media.call_count == 2
        mock_sleep.assert_called_with(10)


@pytest.mark.asyncio
async def test_filtering_min_date(tmp_path):
    # Setup
    now = datetime.now(timezone.utc)
    msg1 = FakeMessage(1, now)
    msg2 = FakeMessage(2, now - timedelta(days=2))  # Older than cutoff
    msg3 = FakeMessage(3, now - timedelta(days=3))  # Even older

    messages = [msg1, msg2, msg3]

    client_mock = MagicMock()
    client_mock.connect = AsyncMock()
    client_mock.start = MagicMock()

    async def iter_messages(entity):
        for m in messages:
            yield m

    client_mock.iter_messages = iter_messages

    dialog_mock = MagicMock()
    dialog_mock.id = 123
    dialog_mock.entity = MagicMock()

    async def iter_dialogs(archived=False):
        yield dialog_mock

    client_mock.iter_dialogs = iter_dialogs

    config = ConfigObject(
        session_id="s", api_hash="h", api_id=1, download_dir=str(tmp_path)
    )

    with (
        patch("telegrab.__main__.TelegramClient", return_value=client_mock),
        patch("telegrab.__main__.get_session"),
        patch(
            "telegrab.__main__.process_message", new_callable=AsyncMock
        ) as mock_process,
        patch("telegrab.__main__.check_download_dir", return_value=tmp_path),
    ):  # Bypass interactive check
        # Test with min_date = now - 1 day
        min_date = now - timedelta(days=1)

        await inner(
            config,
            all_channels=True,
            channel=None,
            channel_id=None,
            list_chats=False,
            debug=False,
            download_path=None,
            min_date=min_date,
        )

        # msg1 is newer -> processed
        # msg2 is older -> loop should break

        assert mock_process.call_count == 1
        assert mock_process.call_args[0][3] == msg1
