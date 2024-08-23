import os
import argparse
from moviepy.editor import VideoFileClip, concatenate_videoclips, ImageClip, AudioFileClip, concatenate_audioclips
from moviepy.audio.AudioClip import AudioClip
import moviepy.config as mp_config


from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(description="Create a YouTube upload video from specific quadrants of input videos.")
    parser.add_argument('--date', help="Date in the format YYYY-MM-DD")
    parser.add_argument('--quadrant', required=True, choices=['top left', 'top right', 'bottom left', 'bottom right'], help="Quadrant to use from each video")
    parser.add_argument('--input_dir', required=True, help="Input directory containing the video files")
    parser.add_argument('--output', required=True, help="Output video file path")
    parser.add_argument('--intro', required=True, help="Intro video file path")
    parser.add_argument('--outro', required=True, help="Outro video file path")
    parser.add_argument('--transition-audio', default=None, help="Audio sting to play during the transitions")
    parser.add_argument('--chapter_index', required=True, help="Output text file for chapter index")
    parser.add_argument('--use-nvidia', action='store_true', default=False, help="Use NVidia card for encoding.")
    parser.add_argument('--min-length', type=int, default=10, help="Skip any files with a duration shorter than this.")
    parser.add_argument('--file-list', nargs='*', help="Space-separated list of files to process")

    args = parser.parse_args()
    if not args.file_list and not args.date:
        parser.error("Either --date or --file_list must be provided.")

    return parser.parse_args()

def get_quadrant_clip(clip, quadrant, target_size):
    w, h = clip.size
    if quadrant == 'top left':
        cropped_clip = clip.crop(x1=0, y1=0, x2=w/2, y2=h/2)
    elif quadrant == 'top right':
        cropped_clip = clip.crop(x1=w/2, y1=0, x2=w, y2=h/2)
    elif quadrant == 'bottom left':
        cropped_clip = clip.crop(x1=0, y1=h/2, x2=w/2, y2=h)
    elif quadrant == 'bottom right':
        cropped_clip = clip.crop(x1=w/2, y1=h/2, x2=w, y2=h)

    return cropped_clip.resize(newsize=target_size)

def create_silence(duration, fps):
    return AudioClip(make_frame=lambda t: np.zeros((len(t), 2)), duration=duration, fps=fps)

def create_text_clip(text_lines, duration, target_size, audio_path=None):
    # Create an image with the text
    img = Image.new('RGB', target_size, color='black')
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("DejaVuSans.ttf", 70)

    # Draw multiple lines of text
    y = (target_size[1] - sum([draw.textsize(line, font=font)[1] for line in text_lines])) // 2
    for line in text_lines:
        text_size = draw.textsize(line, font=font)
        text_x = (target_size[0] - text_size[0]) // 2
        draw.text((text_x, y), line, font=font, fill='white')
        y += text_size[1]

    # Convert the image to a MoviePy ImageClip
    img.save("/tmp/temp_text.png")
    txt_clip = ImageClip("/tmp/temp_text.png").set_duration(duration)

     # Handle audio if audio_path is provided
    if audio_path:
        audio_clip = AudioFileClip(audio_path)

        # If the audio is longer than the duration, cut it
        if audio_clip.duration > duration:
            audio_clip = audio_clip.subclip(0, duration)

        # Set the audio of the text clip, it will stop when the audio ends
        txt_clip = txt_clip.set_audio(audio_clip)

    return txt_clip

FILEFORMAT = "%Y-%m-%d %H-%M-%S"
DATEFORMAT = "%A %B %-d"
TIMEFORMAT = "%-I:%M %p"


def main():
    args = parse_args()

    date_str = args.date
    input_dir = args.input_dir
    output_path = args.output
    intro_path = args.intro
    outro_path = args.outro
    chapter_index_path = args.chapter_index
    quadrant = args.quadrant

    intro_clip = VideoFileClip(intro_path)
    outro_clip = VideoFileClip(outro_path)

    target_size = intro_clip.size  # Use the size of the intro clip for all videos

    video_clips = []
    chapter_index = []
    current_time = intro_clip.duration

    if args.file_list:
        files_to_process = args.file_list
    else:
        files_to_process = [os.path.join(input_dir, filename) for filename in sorted(os.listdir(input_dir)) if filename.startswith(date_str) and filename.endswith('.mkv')]

    for filepath in files_to_process:
        if os.path.isfile(filepath):
            # Get the specified quadrant of the video
            clip = VideoFileClip(filepath)
            quadrant_clip = get_quadrant_clip(clip, quadrant, target_size)
            if quadrant_clip.duration < args.min_length:
                continue
            # Create an intro/transition clip
            timestamp = datetime.strptime(os.path.basename(filepath).split('.')[0], FILEFORMAT)
            timestring = timestamp.strftime(TIMEFORMAT)
            datestring = timestamp.strftime(DATEFORMAT)
            text_clip = create_text_clip([datestring, timestring], duration=3, target_size=target_size, audio_path=args.transition_audio)
            # Put them both in the output file
            video_clips.append(text_clip)
            video_clips.append(quadrant_clip)
            # Note the start time for the chapter index
            chapter_index.append(f"{current_time:.2f} - {timestamp}")
            current_time += text_clip.duration + quadrant_clip.duration

    final_clip = concatenate_videoclips([intro_clip] + video_clips + [outro_clip])

    # Defaults:
    ffmpeg_params = None
    codec = 'libx264'
    acodec = 'aac'

    ## NOTE: THIS IS NOT WOKRING
    # I've verified that ffmpeg is compiled with nvidia support and that it's working from the CLI
    # I've run which ffmpeg from the CLI and verified even in the venv it's /usr/bin/ffmpeg
    if args.use_nvidia:
    # NVIDIA GPU encoding parameters
        ffmpeg_params = [
            '-c:v', 'h264_nvenc',  # Use NVIDIA GPU encoder
            '-preset', 'slow',     # Encoding preset
            '-b:v', '5M',          # Bitrate
            '-c:a', 'aac',         # Audio codec
            '-b:a', '192k'         # Audio bitrate
        ]
        codec = 'h264_nvenc'
        # acodec = None
        mp_config.change_settings({"FFMPEG_BINARY": "/usr/bin/ffmpeg"})  # Change this to your FFmpeg path

    final_clip.write_videofile(output_path, codec=codec, audio_codec=acodec, ffmpeg_params=ffmpeg_params)

    with open(chapter_index_path, 'w') as f:
        for entry in chapter_index:
            f.write(entry + '\n')

if __name__ == "__main__":
    main()

