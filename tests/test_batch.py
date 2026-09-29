from ytdl.batch import BatchEntry, parse_batch_file
from ytdl.cli import is_playlist_url

SAMPLE = '''\
"1. Ichor",https://www.youtube.com/watch?v=eqwbRd-QhS4
"5. Burn Under My Skin (with Bailzwil)",https://www.youtube.com/watch?v=PLf1D9-ihEE
Simple Title,https://www.youtube.com/watch?v=aaaaaaaaaaa
https://www.youtube.com/watch?v=bbbbbbbbbbb

# a comment
not a url line
https://www.youtube.com/playlist?list=PL123
'''


def _parse(tmp_path, text):
    p = tmp_path / "batch.txt"
    p.write_text(text)
    return parse_batch_file(p)


def test_parse_titles_and_bare_urls(tmp_path):
    entries = _parse(tmp_path, SAMPLE)
    # comment + non-url line are dropped; the playlist URL is still parsed here
    # (CLI is responsible for skipping playlists).
    assert entries == [
        BatchEntry("https://www.youtube.com/watch?v=eqwbRd-QhS4", "1. Ichor"),
        BatchEntry("https://www.youtube.com/watch?v=PLf1D9-ihEE",
                   "5. Burn Under My Skin (with Bailzwil)"),
        BatchEntry("https://www.youtube.com/watch?v=aaaaaaaaaaa", "Simple Title"),
        BatchEntry("https://www.youtube.com/watch?v=bbbbbbbbbbb", None),
        BatchEntry("https://www.youtube.com/playlist?list=PL123", None),
    ]


def test_quoted_title_with_comma_is_one_field(tmp_path):
    entries = _parse(tmp_path, '"Hello, World",https://youtu.be/xxxxxxxxxxx\n')
    assert entries == [BatchEntry("https://youtu.be/xxxxxxxxxxx", "Hello, World")]


def test_blank_and_comment_lines_ignored(tmp_path):
    entries = _parse(tmp_path, "\n#c\n   \nhttps://youtu.be/zzzzzzzzzzz\n")
    assert entries == [BatchEntry("https://youtu.be/zzzzzzzzzzz", None)]


def test_playlist_urls_detected_for_skipping(tmp_path):
    entries = _parse(tmp_path, SAMPLE)
    playlists = [e for e in entries if is_playlist_url(e.url)]
    assert [e.url for e in playlists] == [
        "https://www.youtube.com/playlist?list=PL123"
    ]
