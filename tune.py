from pytube import YouTube
import cv2
import os
from PIL import Image
import imagehash
import argparse
import numpy as np
import platform
import subprocess
import zipfile
import webbrowser


def download_youtube_video(url, save_path=''):
    print(f"Downloading video from {url} ...")
    yt = YouTube(url)
    stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
    if not save_path:
        save_path = stream.default_filename
    stream.download(output_path=save_path)
    print(f"Video downloaded: {stream.default_filename}")
    return os.path.join(save_path, stream.default_filename)

def is_mostly_black_or_white(image, threshold, white_threshold=225):
    """
    Check if the given image is mostly black or white.
    :param image: Image to be checked.
    :param threshold: Threshold below which the image is considered 'black'.
    :param white_threshold: Threshold above which the image is considered 'white'.
    :return: True if the image is mostly black or white; False otherwise.
    """
    # Convert image to grayscale
    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Calculate the average brightness of the image
    average_brightness = cv2.mean(gray_image)[0]

    return average_brightness < threshold or average_brightness > white_threshold

def extract_frames(video_path, frame_interval=50, save_path='', black_white_threshold=10, hash_func=imagehash.average_hash, hash_size=8, hash_diff_threshold=10):
    if save_path and not os.path.exists(save_path):
        os.makedirs(save_path)

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print("Error: Could not open video.")
        return

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"Total frames: {total_frames}, FPS: {fps}")

    frame_index = 0
    saved_frame_count = 0
    previous_hash = None

    while True:
        ret, frame = cap.read()
        if ret:
            if frame_index % frame_interval == 0:
                pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

                is_black_or_white = is_mostly_black_or_white(frame, threshold=black_white_threshold)
                current_hash = hash_func(pil_image, hash_size=hash_size)

                should_save = True  # Initialize the flag assuming the frame will be saved

                if previous_hash is not None:
                    hash_diff = current_hash - previous_hash
                    if hash_diff < hash_diff_threshold:
                        should_save = False  # If frames are similar, do not save
                        print(f"Skipping frame {frame_index} due to perceived duplication (hash diff: {hash_diff})")

                if is_black_or_white:
                    should_save = False  # If frame is mostly black or white, do not save
                    print(f"Skipping frame {frame_index} because it's mostly black or white")

                if should_save:
                    save_filename = os.path.join(save_path, f'frame_{frame_index}.jpg')
                    cv2.imwrite(save_filename, frame)
                    saved_frame_count += 1

                previous_hash = current_hash

            frame_index += 1
        else:
            break

    cap.release()
    print(f"Done extracting frames. {saved_frame_count} images are saved in '{save_path}'.")


def open_file_explorer(path):
    """
    Open the file explorer at the specified path.
    """
    if platform.system() == "Windows":
        os.startfile(path)
    elif platform.system() == "Darwin":  # macOS
        subprocess.Popen(["open", path])
    else:  # linux
        subprocess.Popen(["xdg-open", path])


def user_confirmation(path):
    """
    Prompt the user to check the images before proceeding.
    """
    confirmation = input("Press Enter to open finder to check the images.")
    open_file_explorer(path)  # This will open the file explorer so you can check the images

    confirmation = input("Have you checked the images and do you want to proceed with posting a training? (y/n): ")
    return confirmation.lower() == "y"


def user_model():
    """
    Prompt the user to input the SDXL fine tune model name
    """
    does_model_exist = input("Have you already created the model on Replicate? (y/n): ")

    if does_model_exist.lower() == "y":
        model_name = input("Please input the model name (owner/model_name): ")
        return model_name
    else:
        name = input("What do you want to call the model? Pick a short and memorable name. Use lowercase characters and dashes. (eg: sdxl-barbie): ")
        webbrowser.open(f"https://replicate.com/create?name={name}")
        input("Once you have created the model (click Create on the webpage I just opened), press Enter to continue.")
        owner = input("What is your Replicate username? ")
        return f"{owner}/{name}"


def zip_directory(folder_path, zip_path):
    """
    Compress a directory (with all files in it) into a zip file.

    :param folder_path: Path of the folder you want to compress.
    :param zip_path: Destination file path, including the filename of the new zip file.
    """
    print(f"Zipping {folder_path} to {zip_path} ...")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, os.path.relpath(file_path, folder_path))

    return zip_path

def create_training(model, save_dir):
    try:
        # Please make sure that 'replicate' is installed and available in your system's PATH.
        # The command assumes that "nightmare.zip" is correctly placed and accessible.
        command = [
            "replicate",
            "train",
            "stability-ai/sdxl",
            "--destination",
            model,
            "--web",
            f"input_images=@{save_dir}"
        ]
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print("Error executing the command:", str(e))
    except FileNotFoundError:
        print("Error: 'replicate' command not found. Is it installed correctly?")
    except Exception as e:
        print(f"An error occurred: {str(e)}")


def main():
    parser = argparse.ArgumentParser(description='Download a video from YouTube and extract frames.')
    parser.add_argument('url', help='URL of the YouTube video')
    parser.add_argument('output_directory', help='Directory where the frames will be saved', default='./extracted_frames', nargs='?')
    args = parser.parse_args()

    video_url = args.url
    output_directory = args.output_directory

    # Directory where you want to save the downloaded video
    download_directory = './downloaded_videos'  # replace with your desired directory if you want

    video_file_path = download_youtube_video(video_url, save_path=download_directory)
    extract_frames(video_file_path, frame_interval=50, save_path=output_directory)

       # After extracting and saving images, ask the user to confirm
    if user_confirmation(output_directory):
        # If the user confirms, proceed with the posting function
        model = user_model()

        # Compress the directory with the images
        zip_path = zip_directory(output_directory, output_directory + ".zip")

        create_training(model, zip_path)
    else:
        print("Operation cancelled by the user.")

if __name__ == "__main__":
    main()
