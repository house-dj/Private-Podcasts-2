import os
import datetime
import subprocess
import shutil
import xml.etree.ElementTree as ET
import csv  # <--- ADDED: Import for CSV handling
from mutagen.mp3 import MP3

# --- Configuration ---
# Get the directory where the script is located (this is assumed to be the repo root)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Your GitHub Pages Base URL (REQUIRED for enclosure links)
BASE_URL = "https://house-dj.github.io/Private-Podcasts-2/"
# Local directory where new, un-processed MP3 files are placed
NEW_AUDIO_DIR = "_new_uploads"
# Name of the RSS feed file
FEED_FILE = "feed.xml"
# Name of the topics CSV file
TOPICS_CSV_FILE = ("C:/Users/jdhou/PycharmProjects/ReportGenerator/Generate Text Scripts/reference files/"
                   "topics.csv")  # <--- ADDED: CSV filename constant
# Repository details for Git commands
REPO_NAME = "Private-Podcasts-2"

# Construct absolute paths for reliable file access
NEW_AUDIO_FULL_PATH = os.path.join(SCRIPT_DIR, NEW_AUDIO_DIR)
FEED_FILE_FULL_PATH = os.path.join(SCRIPT_DIR, FEED_FILE)
TOPICS_CSV_FULL_PATH = os.path.join(SCRIPT_DIR, TOPICS_CSV_FILE)  # <--- ADDED: CSV full path constant

# --- Constants for XML Namespace ---
# Registering namespaces is necessary for correct XML output with iTunes tags
NS_ITUNES = 'http://www.itunes.com/dtds/podcast-1.0.dtd'
ET.register_namespace('itunes', NS_ITUNES)
NS_ATOM = 'http://www.w3.org/2005/Atom'
ET.register_namespace('atom', NS_ATOM)


# Helper function to convert seconds to HH:MM:SS format
def seconds_to_hms(duration):
    """Converts duration in seconds to HH:MM:SS or MM:SS format."""
    duration = int(duration)
    h = duration // 3600
    m = (duration % 3600) // 60
    s = duration % 60

    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    else:
        return f"{m:02d}:{s:02d}"


def get_mp3_metadata(filepath):
    """
    Reads file size in bytes and duration in seconds/HMS format.
    Requires: 'mutagen' library
    """
    try:
        # File size in bytes
        file_size = os.path.getsize(filepath)

        # Duration using mutagen
        audio = MP3(filepath)
        duration_seconds = audio.info.length
        duration_hms = seconds_to_hms(duration_seconds)

        return file_size, duration_hms
    except Exception as e:
        print(f"Error reading metadata for {filepath}: {e}")
        return None, None


# --- ADDED: Function to load metadata from topics.csv ---
def load_csv_metadata(csv_path):
    """
    Loads metadata from the topics CSV file into a dictionary mapping ID to details.
    Expected columns: ID, Topic, Podcast Description.
    """
    metadata = {}
    if not os.path.exists(csv_path):
        print(f"Warning: Topics CSV file not found at {csv_path}. Cannot enrich metadata.")
        return metadata

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Use .get() for robustness
                id_val = row.get('ID', '').strip()
                category = row.get('Category', '').strip()
                topic = row.get('Topic', '').strip()
                description = row.get('Podcast Description', '').strip()

                if id_val:
                    metadata[id_val] = {
                        'title': topic,
                        # Use the description if it exists, otherwise use a default fallback
                        'description': description if description else f"Topic: {topic}",
                        'category': category if category else ""
                    }
        print(f"Loaded metadata for {len(metadata)} topics from {os.path.basename(csv_path)}.")
        return metadata
    except Exception as e:
        print(f"Error reading or parsing {csv_path}: {e}")
        return {}


def synchronize_feed(channel):
    """
    Synchronizes the feed by removing entries where the corresponding MP3 file
    is missing from the repository root directory (SCRIPT_DIR).
    """
    print("Starting synchronization: Checking for deleted MP3 files...")

    # 1. Get list of actual MP3 files in the repository root
    # Note: We check SCRIPT_DIR for files, excluding the upload temp directory name itself
    actual_mp3_files = {f for f in os.listdir(SCRIPT_DIR) if f.lower().endswith('.mp3') and f != NEW_AUDIO_DIR}

    items_to_remove = []

    # 2. Iterate through items in the feed
    for item in list(channel):
        if item.tag != 'item':
            continue

        enclosure = item.find('enclosure')
        if enclosure is not None:
            url = enclosure.get('url')

            # 3. Extract the filename from the URL and check existence
            if url:
                # Get the actual filename from the end of the URL
                filename = os.path.basename(url)

                if filename not in actual_mp3_files:
                    items_to_remove.append(
                        (item, filename, item.find('title').text if item.find('title') is not None else "Untitled"))

    # 4. Remove missing items from the channel
    if items_to_remove:
        for item, filename, title in items_to_remove:
            channel.remove(item)
            print(f"Removed item '{title}' from feed.xml (MP3 file '{filename}' is missing).")
        return True
    else:
        print("No items needed to be removed from the feed.")
        return False


def update_podcast_feed():
    """
    Main function to process new audio files, update feed.xml, and prepare for Git.
    """
    # Check the upload directory using the absolute path
    if not os.path.exists(NEW_AUDIO_FULL_PATH):
        os.makedirs(NEW_AUDIO_FULL_PATH)
        print(f"Created directory '{NEW_AUDIO_DIR}'. Place MP3s inside it and run again.")
        return False

    # List files from the correct path
    new_files = [f for f in os.listdir(NEW_AUDIO_FULL_PATH) if f.lower().endswith('.mp3')]

    # --- ADDED: Load topic data from CSV ---
    # topic_metadata = load_csv_metadata(TOPICS_CSV_FULL_PATH)

    # Check for feed file existence using the absolute path
    if not os.path.exists(FEED_FILE_FULL_PATH):
        # If feed.xml doesn't exist, create a basic one. Synchronization skipped.
        print(f"'{FEED_FILE}' not found. Creating a minimal new feed structure.")

        root = ET.Element('rss', attrib={'version': '2.0', 'xmlns:itunes': NS_ITUNES, 'xmlns:atom': NS_ATOM})
        channel = ET.SubElement(root, 'channel')

        # Add basic channel metadata (user should ideally customize these manually later)
        ET.SubElement(channel, 'title').text = "My Private History Audio Feed"
        ET.SubElement(channel, 'link').text = BASE_URL
        ET.SubElement(channel, 'description').text = "My personal audio collection."
        ET.SubElement(channel, 'language').text = "en-us"

        # Add atom:link for self-reference
        atom_link = ET.SubElement(channel, f"{{{NS_ATOM}}}link",
                                  attrib={'href': f"{BASE_URL}{FEED_FILE}", 'rel': 'self',
                                          'type': 'application/rss+xml'})

        tree = ET.ElementTree(root)  # Initialize tree for later saving
    else:
        # Load existing XML structure using the absolute path
        tree = ET.parse(FEED_FILE_FULL_PATH)
        root = tree.getroot()
        channel = root.find('channel')

        if channel is None:
            print(f"Error: '{FEED_FILE}' is missing the required '<channel>' tag.")
            return False

        # --- STEP 1: Synchronize Feed (Remove deleted files) ---
        synchronize_feed(channel)

    # --- STEP 2: Add New Files ---
    episodes_added = 0

    # Re-scan existing GUIDs after synchronization, to prevent adding items
    # that were already present and not deleted.
    existing_guids = {item.find('guid').text for item in channel.findall('item') if item.find('guid') is not None}

    for filename in new_files:
        # Use the absolute path for the source file
        local_path = os.path.join(NEW_AUDIO_FULL_PATH, filename)

        # --- Metadata Extraction ---
        file_size, duration_hms = get_mp3_metadata(local_path)
        if file_size is None:
            continue

        # Use filename prefix as a unique GUID (e.g., '104_British_...' -> '104')
        guid = filename.split('_')[0]
        if guid in existing_guids:
            print(f"Skipping '{filename}': GUID '{guid}' already exists in feed.xml.")
            continue

        # --- MODIFIED: Lookup title and description from CSV metadata ---
        """
        topic_data = topic_metadata.get(guid)
        
        if topic_data:
            # 3) Populate <title> from the Topic column of the row
            title = guid + " " + topic_data['category'] + " - " + topic_data['title']
            # 4) Populate <description> from the Podcast Description column of the row
            description = topic_data['description']
            print(f"Matched ID {guid} to Topic: {title}")
        else:
        """
        # Fallback to current script logic (clean filename)
        title = filename.replace('.mp3', '').replace('_', ' ').strip()
        description = f"Automated upload for: {title}"
        print(f"ID {guid} not found in CSV. Using default title/description.")

        # Set publish date to now in RFC 822 format (e.g., Thu, 30 Oct 2025 10:00:00 +0000)
        pub_date = datetime.datetime.now(datetime.timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')

        # --- Create XML Item ---
        item = ET.Element('item')

        ET.SubElement(item, 'title').text = title  # Uses looked-up title
        ET.SubElement(item, 'pubDate').text = pub_date
        ET.SubElement(item, 'description').text = description  # Uses looked-up description

        # Add GUID
        ET.SubElement(item, 'guid', attrib={'isPermaLink': 'false'}).text = guid

        # Add Enclosure (Crucial for podcast apps)
        enclosure_url = f"{BASE_URL}{filename}"
        ET.SubElement(item, 'enclosure',
                      attrib={'url': enclosure_url, 'length': str(file_size), 'type': 'audio/mpeg'})

        # Add iTunes Duration
        ET.SubElement(item, f"{{{NS_ITUNES}}}duration").text = duration_hms
        ET.SubElement(item, f"{{{NS_ITUNES}}}author").text = "My Name"  # Set your preferred author name

        # Insert the new item at the top of the channel (newest episode first)
        first_item = channel.find('item')
        if first_item is not None:
            channel.insert(list(channel).index(first_item), item)
        else:
            channel.append(item)

        episodes_added += 1

        # --- Move File to Repository Root ---
        # Destination path uses the SCRIPT_DIR (the repository root)
        dest_path = os.path.join(SCRIPT_DIR, filename)
        shutil.move(local_path, dest_path)
        print(f"Processed and moved: {filename}")

    # --- STEP 3: Final Save ---

    # Remove old lastBuildDate if it exists
    old_date = channel.find('lastBuildDate')
    if old_date is not None:
        channel.remove(old_date)

    # Update last build date and insert at the top
    last_build_date = ET.Element('lastBuildDate')
    last_build_date.text = datetime.datetime.now(datetime.timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')

    # Find the position of 'language' tag to insert lastBuildDate after it
    language_tag = channel.find('language')
    if language_tag is not None:
        channel.insert(list(channel).index(language_tag) + 1, last_build_date)
    else:
        channel.append(last_build_date)

    # 4. Save the updated XML using the absolute path
    # Prettify the XML (optional but nice)
    from xml.dom import minidom
    xml_string = ET.tostring(root, encoding='utf-8')
    pretty_xml = minidom.parseString(xml_string).toprettyxml(indent="  ")

    # Clean up empty lines created by minidom
    with open(FEED_FILE_FULL_PATH, "w", encoding="utf-8") as f:
        # Write only non-empty lines from prettified XML
        for line in pretty_xml.split('\n'):
            if line.strip():
                f.write(line + '\n')

    print(f"\nSuccessfully updated '{FEED_FILE}' with {episodes_added} new episodes.")
    return True


def run_git_commands():
    """
        Executes git add, commit, and push commands.
        Explicitly sets the current working directory (cwd) to the SCRIPT_DIR
        to ensure Git runs within the repository root.
        """
    try:
        print("\n--- Running Git Commands ---")

        # 1. Stage all changes (new files, moved files, updated feed.xml, deleted files)
        # Use cwd=SCRIPT_DIR
        subprocess.run(['git', 'add', '-A'], check=True, capture_output=True, text=True, cwd=SCRIPT_DIR)
        print("Git: Staged all changes, including removals.")

        # 2. Commit
        commit_message = f"Automated podcast update: Synced feed, added new episodes."
        # Use cwd=SCRIPT_DIR
        subprocess.run(['git', 'commit', '-m', commit_message], check=True, capture_output=True, text=True,
                       cwd=SCRIPT_DIR)
        print("Git: Committed changes.")

        # 3. Push
        print("Git: Pushing to remote...")
        # Use cwd=SCRIPT_DIR
        subprocess.run(['git', 'push', 'origin', 'main'], check=True, capture_output=True, text=True, cwd=SCRIPT_DIR)
        print("Git: Successfully pushed changes to GitHub!")

    except subprocess.CalledProcessError as e:
        print("\n--- GIT ERROR ---")
        print("Failed to execute Git commands. Please check your Git setup (authentication, current branch).")
        print(f"Error output: {e.stderr}")
    except FileNotFoundError:
        print("\n--- GIT ERROR ---")
        print("The 'git' command was not found. Please ensure Git is installed and in your system's PATH.")
    except Exception as e:
        print(f"An unexpected error occurred during Git operations: {e}")


if __name__ == "__main__":

    # 1. Update the XML and move files
    if update_podcast_feed():
        # 2. Commit and push the changes
        run_git_commands()