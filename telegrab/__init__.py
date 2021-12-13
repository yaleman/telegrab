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

"""

__version__ = "0.0.2"
