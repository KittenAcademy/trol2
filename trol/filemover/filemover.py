import os
import shutil
import time
import argparse

def monitor_and_move(source_dir, dest_dir, wait_time):
    file_sizes = {}

    while True:
        # List all files in the source directory
        files = os.listdir(source_dir)

        for file_name in files:
            source_file = os.path.join(source_dir, file_name)

            # Skip if it's not a file
            if not os.path.isfile(source_file):
                continue

            # Get the current size of the file
            current_size = os.path.getsize(source_file)

            # If the file is new, add it to the dictionary with the current time and size
            if file_name not in file_sizes:
                print(f"New file: {file_name}")
                file_sizes[file_name] = (current_size, time.time())
            else:
                previous_size, last_time = file_sizes[file_name]

                # Check if the file size has changed
                if current_size != previous_size:
                    file_sizes[file_name] = (current_size, time.time())
                else:
                    # Check if the file has been the same size for the specified wait_time
                    if time.time() - last_time > wait_time:
                        print(f"Moving file: {file_name}")
                        dest_file = os.path.join(dest_dir, file_name)
                        shutil.move(source_file, dest_file)
                        print(f"Moved {file_name} to {dest_dir}")
                        del file_sizes[file_name]

        # Remove entries for files that no longer exist in the source directory
        for file_name in list(file_sizes.keys()):
            if file_name not in files:
                del file_sizes[file_name]

        # Wait for a short period before the next check
        time.sleep(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor and move files from one directory to another after they have not grown for a specified time.")
    parser.add_argument("source_dir", help="The source directory to monitor")
    parser.add_argument("dest_dir", help="The destination directory to move files to")
    parser.add_argument("wait_time", type=int, help="The time in seconds to wait after the file has stopped growing before moving it")

    args = parser.parse_args()

    print(f"Monitoring {args.source_dir} for move to {args.dest_dir}")
    monitor_and_move(args.source_dir, args.dest_dir, args.wait_time)

