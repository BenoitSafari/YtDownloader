from ytdl.cli import _extract_mode, is_playlist_url, sanitize_url


def test_extract_mode_single_dash():
    mode, rest = _extract_mode(["-mp3", "URL", "OUT"])
    assert mode == "mp3"
    assert rest == ["URL", "OUT"]


def test_extract_mode_mkv_double_dash():
    mode, rest = _extract_mode(["--mkv", "URL", "OUT", "--ordered"])
    assert mode == "mkv"
    assert rest == ["URL", "OUT", "--ordered"]


def test_extract_mode_absent():
    mode, rest = _extract_mode(["URL", "OUT"])
    assert mode is None
    assert rest == ["URL", "OUT"]


def test_extract_mode_only_first_token_consumed():
    # A stray second mode token stays in rest (argparse will reject it).
    mode, rest = _extract_mode(["-mkv", "-mp3", "URL"])
    assert mode == "mkv"
    assert rest == ["-mp3", "URL"]


def test_sanitize_url_strips_quotes_and_space():
    url = "https://www.youtube.com/watch?v=abc&list=PL1"
    assert sanitize_url(f'"{url}"') == url
    assert sanitize_url(f"'{url}'") == url
    assert sanitize_url(f'  "{url}"  ') == url
    # nested quotes as produced by "'...'"
    assert sanitize_url(f"\"'{url}'\"") == url


def test_sanitize_url_leaves_clean_url_untouched():
    url = "https://youtu.be/abc"
    assert sanitize_url(url) == url


def test_is_playlist_url():
    assert is_playlist_url("https://www.youtube.com/playlist?list=PL123")
    assert is_playlist_url("https://youtu.be/watch?v=abc&list=PL123")
    assert not is_playlist_url("https://www.youtube.com/watch?v=abc")
    assert not is_playlist_url("https://youtu.be/abc")
