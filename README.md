# 🎬 SubTools v0.2

A powerful Python toolkit for working with subtitle files — clean, convert, merge, and extract subtitles from video platforms like Hulu, TVer, FOD, and NHK.

## 🚀 Features

- ✅ Download and convert subtitle formats from popular Japanese platforms (Hulu, FOD, TVer, NHK)
- 🎯 Convert subtitles between formats (TTML, VTT → SRT/ASS)
- 🧼 Clean unwanted tags and formatting from SRT/ASS files
- 🔄 Fix overlapping subtitle timings
- 📚 Merge duplicate lines in subtitle files
- 🗂 Batch convert VTT → SRT
- 🎥 Extract specific subtitle/audio streams from media files

## 📦 Requirements

Install required libraries via pip:

```bash
pip install yt-dlp ffmpeg-python beautifulsoup4 webvtt-py pysrt pysubs2
```

You’ll also need:
- [`ffmpeg`](https://ffmpeg.org/) installed and accessible in PATH
- `yt-dlp` standalone binary (used for TVer downloads)

## 🧩 Usage

Run the script:

```bash
python subtools-v02.py
```

Then choose from the menu:

```
1. Extract stream from video file
2. Hulu VTT - download clean convert
3. FOD VTT - download convert
4. TVer VTT - download convert
5. NHK TTML - download convert
6. Batch convert VTT to SRT
7. Clean SRT file
8. Overlap fix in SRT
9. Dedupe merge lines SRT from SUP
10. Clean Caption2Ass files, convert to SRT, and fix overlaps
```

### Example: Convert NHK TTML to SRT

```text
> 5
Enter the NHK TTML link: https://example.nhk.or.jp/subs.xml
Enter the name for the TTML file: episode01
Enter the desired output format (srt/ass): srt
```

## 📂 Directory Structure

Outputs are saved in the same folder unless otherwise specified.

| Task              | Output                          |
|-------------------|----------------------------------|
| Hulu/FOD/VTT      | `.srt` cleaned subtitle file     |
| NHK TTML          | `.srt` or `.ass` subtitle file   |
| ASS Cleanup       | `.cleaned.srt` file              |
| Overlap Fix       | `.fixed.srt` version             |
| Merge Duplicates  | `_merged.srt` version            |

## 🛡️ Safety

No personal data or hardcoded paths are embedded in the script. All inputs are handled interactively.

## 📄 License

MIT License. Use freely, attribution appreciated!

---

### 🧠 Tips

- To download TVer subs, ensure `yt-dlp` binary is next to this script and marked as executable.
- For batch processing, keep your `.vtt` files in one folder and run the batch tool.

---

Feel free to fork and customize to your fansub or localization workflow! 🇯🇵📺
