# subtools-v02 031925 replaced fix_overlapping_subtitles
import os
import re
import subprocess
import ffmpeg
import yt_dlp
import webvtt
from urllib.parse import urlparse, urlunparse
from bs4 import BeautifulSoup
import codecs
import math
import datetime
import sys
import shlex
from pysrt import SubRipFile, SubRipItem
import pysubs2

def normalize_path(input_path):
    """Normalize file path to handle escaped characters and expand user directory."""
    # Replace escaped characters (e.g., '\ ') with the actual space
    cleaned_path = input_path.replace("\\", "")
    # Expand ~ to user directory
    cleaned_path = os.path.expanduser(cleaned_path)
    # Normalize the final path
    return os.path.normpath(cleaned_path)

# === Stream Extraction ===
def list_streams(file_path):
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", file_path],
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True
        )
        output = result.stderr
        streams = []
        for line in output.splitlines():
            if "Stream #" in line:
                streams.append(line.strip())
        return streams
    except Exception as e:
        print(f"Error listing streams: {e}")
        exit(1)

def extract_stream(file_path, stream_index, output_file):
    try:
        subprocess.run(
            ["ffmpeg", "-i", file_path, "-map", f"0:{stream_index}", output_file],
            check=True
        )
        print(f"Stream saved to {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error extracting stream: {e}")
        exit(1)


# === TTML Conversion Functions ===
def to_srt_time(seconds_ms):
    """Convert seconds.milliseconds to SRT time format."""
    split_time = seconds_ms.split('.')
    sec = int(split_time[0])
    milliseconds = int(split_time[1] if len(split_time) >= 2 else '0')
    hrs = sec // 3600
    sec %= 3600
    mins = sec // 60
    sec %= 60
    return f'{hrs:02}:{mins:02}:{sec:02},{milliseconds:03}'

def to_ass_time(seconds_ms):
    """Convert seconds.milliseconds to ASS time format."""
    split_time = seconds_ms.split('.')
    sec = int(split_time[0])
    milliseconds = int(split_time[1] if len(split_time) >= 2 else '0')
    hrs = sec // 3600
    sec %= 3600
    mins = sec // 60
    sec %= 60
    return f'{hrs:01}:{mins:02}:{sec:02}.{milliseconds:02}'

def consolidate_lines(text):
    """Remove unnecessary line breaks, preserving intended ones for dialogue."""
    lines = text.strip().splitlines()
    consolidated = []
    for line in lines:
        # If a line starts with a speaker marker (e.g., (Name)), keep the break
        if line.startswith("(") and ")" in line:
            consolidated.append("\n" + line.strip())
        else:
            consolidated.append(line.strip())
    return " ".join(consolidated).replace(" \n", "\n").strip()    

class Scaling:
    """Handle scaling of subtitle positions."""
    def __init__(self, initial_w, initial_h, final_w, final_h):
        self.iw = initial_w
        self.ih = initial_h
        self.fw = final_w
        self.fh = final_h

    def scale(self, x, y):
        scale_w = float(self.fw) / float(self.iw)
        scale_h = float(self.fh) / float(self.ih)
        return int(float(x) * scale_w), int(float(y) * scale_h)

    def __call__(self, x, y):
        return self.scale(x, y)

def convert_to_ass(content, outfile_name, scaling):
    """Convert TTML to ASS format."""
    outfile = codecs.open(outfile_name, 'w', encoding='utf8')
    soup = BeautifulSoup(content, features="xml")

    info = f"""[Script Info]
    Title: {outfile_name}
    ScriptType: v4.00+
    WrapStyle: 0
    PlayResX: {scaling.fw}
    PlayResY: {scaling.fh}
    """
    print(info, file=outfile)

    styles = """[V4+ Styles]
    Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
    Style: Default,MS UI Gothic,24,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,1,10,10,10,0
    """
    print(styles, file=outfile)

    events = """[Events]
    Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
    """
    print(events, file=outfile)

    cuepoints = soup.cuepoints
    captions = cuepoints.find_all('cuepoint')

    for i, caption in enumerate(captions[:-1]):
        next_caption_time = captions[i + 1]['time']
        subtitles = caption.find_all('subtitle')
        if not subtitles:
            continue

        start_time = to_ass_time(caption['time'])
        end_time = to_ass_time(next_caption_time)

        for s in subtitles:
            blurb = s.contents[0].strip()
            blurb = s.get('substitution_string', blurb)
            x, y = scaling(s['xx'], s['yy'])
            dialog = f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{{\\pos({x},{y})}}{blurb}"
            print(dialog, file=outfile)


def convert_to_srt(content, outfile_name, scaling):
    """Convert TTML to SRT format with line break adjustments."""
    outfile = codecs.open(outfile_name, 'w', encoding='utf8')
    soup = BeautifulSoup(content, features="xml")

    cuepoints = soup.cuepoints
    captions = cuepoints.find_all('cuepoint')

    caption_id = 1
    for i, caption in enumerate(captions[:-1]):
        next_caption_time = captions[i + 1]['time']
        subtitles = caption.find_all('subtitle')
        if not subtitles:
            continue

        print(f"{caption_id}", file=outfile)
        caption_id += 1

        start_time = to_srt_time(caption['time'])
        end_time = to_srt_time(next_caption_time)
        print(f"{start_time} --> {end_time}", file=outfile)

        subtitle_texts = []
        for s in subtitles:
            blurb = s.contents[0].strip()
            blurb = s.get('substitution_string', blurb)
            subtitle_texts.append(blurb)

        # Consolidate lines and print to SRT
        combined_text = consolidate_lines("\n".join(subtitle_texts))
        print(combined_text, file=outfile)
        print("", file=outfile)


def parse_ttml_file(infile, user_outfile=None, extension='srt'):
    """Parse and convert TTML files."""
    if user_outfile:
        outfile = user_outfile
    else:
        outfile = '.'.join(infile.split('.')[:-1]) + '.' + extension

    with open(infile, 'r', encoding='utf8') as f:
        content = f.read()

    scaling = Scaling(1600, 900, 640, 360)
    if extension == 'srt':
        convert_to_srt(content, outfile, scaling)
    elif extension == 'ass':
        convert_to_ass(content, outfile, scaling)
    else:
        print("Unsupported output format.")


# === Subtitle Cleaning ===
def clean_srt_file(srt_file_path):
    new_file_path = os.path.splitext(srt_file_path)[0] + ".cleaned.srt"
    with open(srt_file_path, "r") as file:
        content = file.read()

    # Perform cleaning
    content = re.sub(r'[\\h📱🔊📺]', '', content)
    content = re.sub(r"WEBVTT\n", "", content)
    content = re.sub(r"X-TIMESTAMP-MAP=.+\n", "", content)

    # Save cleaned content
    with open(new_file_path, "w") as file:
        file.write(content)

    return new_file_path

# === Online Subtitle Download ===
def clean_hulu_link(vtt_link):
    """Remove query parameters like ?ts=xxxxxx from Hulu links."""
    parsed_url = urlparse(vtt_link)
    cleaned_url = urlunparse(parsed_url._replace(query=""))
    return cleaned_url

def download_and_convert_vtt_to_srt(vtt_link, srt_file_name):
    """Downloads Hulu VTT and converts to SRT, cleaning the file afterward."""
    if not srt_file_name.endswith(".srt"):
        srt_file_name += ".srt"
    
    # Clean the Hulu link
    vtt_link = clean_hulu_link(vtt_link)
    
    # Download and convert
    command = f'ffmpeg -i "{vtt_link}" -c:s subrip "{srt_file_name}"'
    subprocess.call(command, shell=True)

    # Clean the SRT file
    cleaned_srt = clean_srt_file(srt_file_name)
    print(f"Hulu subtitles cleaned and saved as: {cleaned_srt}")

def download_fod_convert_vtt_to_srt(fod_link):
    """Download and convert FOD subtitles."""
    srt_filename = input("Enter the desired name for the SRT file (without extension): ") + '.ja-JP.srt'
    vtt_filename = 'subtitle.vtt'

    ydl_opts = {'outtmpl': vtt_filename, 'quiet': True}

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([fod_link])

    webvtt.read(vtt_filename).save_as_srt(srt_filename)

    if os.path.exists(vtt_filename):
        os.remove(vtt_filename)

    print(f"Conversion complete! SRT file saved as: {srt_filename}")

# def download_tver_and_convert_vtt_to_srt(tver_link):
#    """Download and convert TVer subtitles."""
#    yt_dlp_command = f'yt-dlp "{tver_link}" --write-sub --convert-sub=srt --skip-download -k'
#    subprocess.call(yt_dlp_command, shell=True)

# === New TVer subtitle download 051225 ===
def download_tver_and_convert_vtt_to_srt(tver_link):
    """Download and convert TVer subtitles using the standalone yt-dlp binary."""

    # Path to standalone binary (you should have downloaded and chmod +x it)
    ytdlp_path = os.path.join(os.path.dirname(__file__), "yt-dlp")

    # Sanity check: is the binary there?
    if not os.path.exists(ytdlp_path):
        print("❌ yt-dlp-latest binary not found.")
        print("Please download it from https://github.com/yt-dlp/yt-dlp/releases and place it next to this script.")
        return

    # Run yt-dlp using the standalone binary (not the Python module)
    yt_dlp_command = f'"{ytdlp_path}" "{tver_link}" --write-sub --convert-sub=srt --skip-download -k'
    try:
        print(f"📥 Downloading subtitles from TVer...")
        subprocess.run(yt_dlp_command, shell=True, check=True)
        print(f"✅ Subtitles downloaded and converted.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to download TVer subtitles:\n{e}")

# === NHK Subtitle Handling ===
def download_convert_nhk_caps(nhk_link):
    """Download and convert NHK TTML files."""
    ttml_file_name = input("Enter the name for the TTML file (without extension): ")
    ttml_file_path = f"{ttml_file_name}.ttml"

    # Download the TTML file
    command = f'curl -o "{ttml_file_path}" "{nhk_link}"'
    subprocess.call(command, shell=True)

    # Convert TTML to desired format
    output_format = input("Enter the desired output format (srt/ass): ").strip()
    parse_ttml_file(ttml_file_path, extension=output_format)
    print(f"NHK TTML conversion completed: {ttml_file_path} -> {output_format}")   

# === Batch VTT to SRT Conversion ===
def preprocess_vtt(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        vtt_content = f.read()
    
    # Cleaning steps for the VTT file
    vtt_content = re.sub(r"^WEBVTT\s*\n", "", vtt_content)
    vtt_content = re.sub(r"(\d{2}:\d{2}:\d{2})[.,](\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2})[.,](\d{3})", r"\1,\2 --> \3,\4", vtt_content)
    vtt_content = re.sub(r"^NOTE.*?$", "", vtt_content, flags=re.MULTILINE)
    vtt_content = vtt_content.replace("&lrm;", "").strip()
    vtt_content = re.sub(r"<(?!/i)(\w+)>", r"{\\i1}", vtt_content)
    vtt_content = re.sub(r"</(\w+)>", r"{\\i0}", vtt_content)
    vtt_content = re.sub(r"<[^>]+>", "", vtt_content)
    vtt_content = re.sub(r"position:.*$", "", vtt_content, flags=re.MULTILINE)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(vtt_content)

def convert_vtt_to_srt(input_file):
    output_file = os.path.splitext(input_file)[0] + ".srt"
    print(f"Converting {input_file} to {output_file}...")
    try:
        preprocess_vtt(input_file, output_file)
    except Exception as e:
        print(f"Error converting {input_file}: {e}")

def batch_convert_vtt_to_srt():
    input_folder = input("Enter the path to the folder containing VTT files: ")
    if not os.path.exists(input_folder):
        print(f"Error: Directory '{input_folder}' not found.")
        return
    
    for file in os.listdir(input_folder):
        if file.endswith(".vtt"):
            input_file = os.path.join(input_folder, file)
            convert_vtt_to_srt(input_file)
    print(f"Batch conversion complete!")


# === Overlap Fixer ===
def parse_time(timestamp):
    """Convert SRT timestamp to a datetime.timedelta."""
    h, m, s_ms = timestamp.split(":")
    s, ms = s_ms.split(",")
    return datetime.timedelta(hours=int(h), minutes=int(m), seconds=int(s), milliseconds=int(ms))

def format_time(td):
    """Convert a datetime.timedelta back to SRT time format."""
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    milliseconds = td.microseconds // 1000
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

# def fix_overlapping_subtitles(input_file):
#     """Fix overlapping subtitles in an SRT file."""
#     # Normalize file path
#     input_file = normalize_path(input_file)

#     if not os.path.exists(input_file):
#         print(f"Error: Input file '{input_file}' does not exist.")
#         return

#     # Generate the output file path in the same directory
#     base, ext = os.path.splitext(input_file)
#     output_file = f"{base}.fixed{ext}"

#     with open(input_file, "r", encoding="utf-8") as infile:
#         subtitles = infile.read().strip().split("\n\n")

#     fixed_subtitles = []
#     last_entry = None  # Temporary storage for merging overlapping subtitles

#     for subtitle in subtitles:
#         lines = subtitle.split("\n")
#         if len(lines) < 3:
#             continue

#         index, timing, *text = lines
#         start, end = timing.split(" --> ")

#         # If the current subtitle matches the last one in timing, merge the lines
#         if last_entry and last_entry["timing"] == timing:
#             last_entry["text"].extend(text)
#         else:
#             # If there was a previous entry, finalize it
#             if last_entry:
#                 fixed_subtitles.append(
#                     f"{last_entry['index']}\n{last_entry['timing']}\n" +
#                     "\n".join(last_entry["text"])
#                 )
#             # Start a new subtitle entry
#             last_entry = {
#                 "index": index,
#                 "timing": timing,
#                 "text": text
#             }

#     # Finalize the last subtitle entry
#     if last_entry:
#         fixed_subtitles.append(
#             f"{last_entry['index']}\n{last_entry['timing']}\n" +
#             "\n".join(last_entry["text"])
#         )

#     with open(output_file, "w", encoding="utf-8") as outfile:
#         outfile.write("\n\n".join(fixed_subtitles))

#     print(f"Overlapping subtitles fixed and saved to {output_file}.")

# === overlap for srt and ass ===

def clean_ass_text(text):
    """Removes positioning codes, color codes, and other formatting from ASS subtitle text."""
    # Remove all styling codes like {\pos(x,y)}, {\c&H00ffff&}, etc.
    text = re.sub(r'\{\\[^}]*\}', '', text)
    # Remove trailing \N
    text = re.sub(r'\\N\s*$', '', text)
    return text.strip()

def cleanup_ass_file(input_file, output_file=None):
    """Cleans up an .ass subtitle file by removing formatting codes and converting to SRT."""
    # Normalize path
    input_file = normalize_path(input_file)
    
    if not os.path.exists(input_file):
        print(f"Error: Input file '{input_file}' does not exist.")
        return None
    
    # Default output file path if not specified
    if not output_file:
        base = os.path.splitext(input_file)[0]
        output_file = f"{base}.cleaned.srt"
    
    try:
        # Load the subtitle file
        subs = pysubs2.load(input_file)
        
        # Clean each line
        for event in subs.events:
            event.text = clean_ass_text(event.text)
        
        # Save directly as SRT (no need for temporary file)
        temp_file = f"{os.path.splitext(input_file)[0]}.temp.srt"
        subs.save(temp_file, format_="srt")
        
        # Now fix overlapping subtitles
        fix_overlapping_subtitles(temp_file)
        
        # Clean up temp file
        os.rename(f"{os.path.splitext(temp_file)[0]}.fixed.srt", output_file)
        os.remove(temp_file)
        
        print(f"✅ ASS file cleaned, converted to SRT, and fixed: {output_file}")
        return output_file
    
    except Exception as e:
        print(f"Error processing file: {e}")
        return None    

def fix_overlapping_subtitles(input_file):
    """Fix overlapping subtitles in an SRT file."""
    # Normalize file path
    input_file = normalize_path(input_file)

    if not os.path.exists(input_file):
        print(f"Error: Input file '{input_file}' does not exist.")
        return

    # Generate the output file path in the same directory
    base, ext = os.path.splitext(input_file)
    output_file = f"{base}.fixed{ext}"

    # Parse SRT into structured format
    subtitles = []
    current_subtitle = None
    
    try:
        with open(input_file, "r", encoding="utf-8") as infile:
            lines = infile.readlines()
            
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                
                # Skip empty lines
                if not line:
                    i += 1
                    continue
                
                # Start of a new subtitle entry
                if line.isdigit():
                    # Save previous subtitle if it exists
                    if current_subtitle and 'timing' in current_subtitle:
                        subtitles.append(current_subtitle)
                    
                    # Start new subtitle
                    current_subtitle = {'index': int(line), 'text': []}
                    i += 1
                    continue
                
                # Timing line (make sure it contains " --> ")
                if " --> " in line and not 'timing' in current_subtitle:
                    current_subtitle['timing'] = line
                    i += 1
                    continue
                
                # Text lines
                if current_subtitle and 'timing' in current_subtitle:
                    current_subtitle['text'].append(line)
                    i += 1
                    continue
                
                # If we get here, something's wrong with the format, skip this line
                print(f"Warning: Skipping malformed line: {line}")
                i += 1
        
        # Add the last subtitle
        if current_subtitle and 'timing' in current_subtitle:
            subtitles.append(current_subtitle)
    
    except UnicodeDecodeError:
        # Try different encodings if UTF-8 fails
        try:
            with open(input_file, "r", encoding="shift-jis") as infile:
                # (re-implement the same parsing logic here)
                # ...
                pass
        except:
            try:
                with open(input_file, "r", encoding="cp932") as infile:
                    # (re-implement the same parsing logic here)
                    # ...
                    pass
            except:
                print(f"Error: Could not decode the file with UTF-8, Shift-JIS, or CP932 encodings.")
                return
    
    # Process subtitles to merge overlapping entries
    merged_subtitles = []
    timing_dict = {}
    
    # Group subtitles by timing
    for sub in subtitles:
        timing = sub['timing']
        if timing not in timing_dict:
            timing_dict[timing] = []
        timing_dict[timing].append(sub)
    
    # Create merged entries
    new_index = 1
    for timing, subs in timing_dict.items():
        combined_text = []
        for sub in subs:
            combined_text.extend(sub['text'])
        
        merged_subtitles.append({
            'index': new_index,
            'timing': timing,
            'text': combined_text
        })
        new_index += 1
    
    # Sort by timing
    merged_subtitles.sort(key=lambda x: x['index'])
    
    # Write output
    with open(output_file, "w", encoding="utf-8") as outfile:
        for sub in merged_subtitles:
            outfile.write(f"{sub['index']}\n")
            outfile.write(f"{sub['timing']}\n")
            outfile.write("\n".join(sub['text']) + "\n\n")
    
    print(f"✅ Overlapping subtitles fixed and saved to {output_file}.")


# === De-dupe and Merge ===

def merge_duplicate_subtitles01(input_srt):
    # Expand tilde (~) and escape sequences in file paths
    input_srt = os.path.expanduser(input_srt)
    input_srt = os.path.abspath(input_srt)

    if not os.path.exists(input_srt):
        print(f"❌ Error: File '{input_srt}' not found.")
        return
    
    subs = SubRipFile.open(input_srt)
    merged_subs = []
    
    i = 0
    while i < len(subs):
        start_time = subs[i].start
        end_time = subs[i].end
        text = subs[i].text.strip()
        
        j = i + 1
        while j < len(subs) and subs[j].text.strip() == text:
            end_time = subs[j].end  # Extend end time to last occurrence
            j += 1
        
        merged_subs.append(SubRipItem(index=len(merged_subs) + 1, start=start_time, end=end_time, text=text))
        i = j  # Move to the next non-duplicate entry
    
    # Define output filename
    output_srt = os.path.splitext(input_srt)[0] + "_merged.srt"
    
    # Save the modified SRT file
    merged_srt = SubRipFile()
    merged_srt.extend(merged_subs)
    merged_srt.save(output_srt, encoding='utf-8')
    
    print(f"✅ Process complete! Merged subtitles saved to: {output_srt}")

def clean_ass_text(text):
    # Remove override tags (e.g., {\an8}, {\pos(320,240)}, {\c&HFF0000&})
    text = re.sub(r"\{\\.*?\}", "", text)  # Use raw string (r"")
    return text.strip()  


# === Main Menu ===
def main():
    print("Select a task:")
    print("1. Extract stream from video file")
    print("2. Hulu VTT - download clean convert")
    print("3. FOD VTT - download convert")
    print("4. TVer VTT - download convert")
    print("5. NHK TTML - download convert")
    print("6. Batch convert VTT to SRT")
    print("7. Clean SRT file")
    print("8. Overlap fix in SRT")
    print("9. Dedupe merge lines SRT from SUP")
    print("10. Clean Caption2Ass files, convert to SRT, and fix overlaps")

    choice = input("Enter choice (1-10): ").strip()

    if choice == '1':
        file_path = input("Insert file path here: ").strip()
        file_path = os.path.expanduser(file_path.replace("\\", ""))

        if not os.path.exists(file_path):
            print("File does not exist. Please check the path.")
            return

        streams = list_streams(file_path)
        print("\nAvailable Streams:")
        for idx, stream in enumerate(streams):
            print(f"[{idx}] {stream}")

        stream_index = int(input("Enter the number of the stream to extract: "))
        output_file = input("Enter the output file name (e.g., output.srt): ").strip()
        extract_stream(file_path, stream_index, output_file)

    elif choice == '2':
        vtt_link = input("Enter the Hulu VTT link: ")
        srt_file_name = input("Enter the name for the SRT file (without extension): ").strip()
        download_and_convert_vtt_to_srt(vtt_link, srt_file_name)

    elif choice == '3':
        fod_link = input("Enter the FOD link: ")
        download_fod_convert_vtt_to_srt(fod_link)

    elif choice == '4':
        tver_link = input("Enter the TVer link: ")
        download_tver_and_convert_vtt_to_srt(tver_link)

    elif choice == '5':
        nhk_link = input("Enter the NHK TTML link: ")
        download_convert_nhk_caps(nhk_link)

    elif choice == '6':
        batch_convert_vtt_to_srt()

    elif choice == '7':
        srt_file_path = input("Enter the path to the SRT file to clean: ").strip()
        if os.path.exists(srt_file_path):
            new_file_path = clean_srt_file(srt_file_path)
            print(f"Cleaned SRT file saved as: {new_file_path}")
        else:
            print("SRT file not found.")

    elif choice == '8':
        input_file = input("Enter the path to the SRT file: ").strip()
    
        # Normalize file path before processing
        input_file = normalize_path(input_file)
    
        fix_overlapping_subtitles(input_file)

    elif choice == '9':
        print("📂 Drag and drop your .srt file here and press Enter:")
        input_srt = input().strip()
    
        # Properly handle escape sequences in file paths
        input_srt = shlex.split(input_srt)[0] if "\\" in input_srt or " " in input_srt else input_srt
    
        merge_duplicate_subtitles(input_srt)

    elif choice == '10':
        print("📂 Clean ASS file, convert to SRT, and fix overlaps:")
        input_ass = input("Enter the path to the ASS file: ").strip()
        input_ass = normalize_path(input_ass)
        
        if os.path.exists(input_ass):
            cleanup_ass_file(input_ass)
        else:
            print("ASS file not found.") 
       

    else:
        print("Invalid choice. Exiting.")

if __name__ == "__main__":
    main()
