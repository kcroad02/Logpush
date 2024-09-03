import os
import re
import json
import requests
from datetime import datetime
from socket import gethostname

# Determine the script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, 'config.json')

def create_default_config(config_path):
    """Create a default configuration file if it doesn't exist."""
    if not os.path.exists(config_path):
        default_config = {
            "paths": {
                "default": {
                    "markdown": "",
                    "output_dir": "",
                    "pushWidget_target": "",
                    "notification_tracker": ""
                }
            },
            "api_key_path": ""
        }
        with open(config_path, 'w') as f:
            json.dump(default_config, f, indent=4)
        print(f'Default configuration file created at {config_path}. Please update it with your markdown file paths and API key path.')

def load_config(config_path):
    """Load configuration from the JSON file."""
    if not os.path.exists(config_path):
        return None
    with open(config_path) as f:
        return json.load(f)

def save_config(config, config_path):
    """Save configuration to the JSON file."""
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)

def prompt_for_paths(paths):
    """Prompt the user to input file paths if they are not already present."""
    home_dir = os.getenv('HOME')
    sync_logseq_path = os.path.join(home_dir, 'Sync', 'Logseq', 'pages', 'Logpush.md')
    default_output_dir = os.path.join(home_dir, 'Sync', 'Logseq', 'assets', 'logpush')

    def get_user_choice():
        choice = input(f"Use default file ({sync_logseq_path}) and directory ({default_output_dir})? (Y/n): ").strip().lower()
        if choice in ['y', '']:
            return sync_logseq_path, default_output_dir
        elif choice == 'n':
            custom_markdown = input("Enter the custom markdown file path: ").strip()
            custom_output_dir = input("Enter the custom output directory path: ").strip()
            return custom_markdown, custom_output_dir
        else:
            print("Invalid choice. Please try again.")
            return get_user_choice()

    if not paths['markdown']:
        paths['markdown'], paths['output_dir'] = get_user_choice()

    output_dir = paths['output_dir']
    paths['pushWidget_target'] = os.path.join(output_dir, 'pushWidget')
    paths['notification_tracker'] = os.path.join(output_dir, 'notification_tracker.txt')

def get_task_file_paths(config):
    """Return file paths based on configuration and prompt user for required inputs."""
    paths = config['paths'].get('default', {})
    prompt_for_paths(paths)
    return paths

def get_api_key(config):
    """Retrieve the API key from the JSON file, or prompt the user to input it."""
    api_key_path = config.get("api_key_path")
    if not api_key_path:
        default_api_key_path = os.path.join(os.getenv('HOME'), 'Sync', 'Logseq', 'assets', 'logpush', 'api_key.json')
        choice = input(f"Do you want to save the API key in the default directory ({default_api_key_path})? (Y/n): ").strip().lower()
        api_key_path = default_api_key_path if choice in ['y', ''] else input("Enter the custom path to save your API key file: ").strip()
        config["api_key_path"] = api_key_path
        save_config(config, CONFIG_PATH)

    if not os.path.exists(api_key_path):
        api_key = input("Enter your Pushbullet API key: ").strip()
        with open(api_key_path, 'w') as f:
            json.dump({"api_key": api_key}, f, indent=4)
        return api_key
    with open(api_key_path) as f:
        api_key = json.load(f).get("api_key")
        if not api_key:
            api_key = input("Enter your Pushbullet API key: ").strip()
            with open(api_key_path, 'w') as f:
                json.dump({"api_key": api_key}, f, indent=4)
        return api_key

def parse_task_line(line):
    """Extract task description from a line."""
    match = re.match(r"- TODO (.+)", line)
    return match.group(1) if match else None

def parse_scheduled_line(line):
    """Extract date and time from a scheduling line."""
    date_match = re.search(r"SCHEDULED: <(\d{4}-\d{2}-\d{2})", line)
    time_match = re.search(r"(\d{2}:\d{2})", line)
    scheduled_date = date_match.group(1) if date_match else None
    scheduled_time = time_match.group(1) if time_match else None
    return scheduled_date, scheduled_time

def write_task_file(task, index, output_dir):
    """Write task information to a file."""
    file_path = os.path.join(output_dir, f"pushWidget{index}.txt")
    with open(file_path, 'w') as f:
        f.write(task)

def send_pushbullet_notification(api_key, title, body):
    """Send a notification using Pushbullet."""
    url = 'https://api.pushbullet.com/v2/pushes'
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    data = {'type': 'note', 'title': title, 'body': body}
    response = requests.post(url, headers=headers, json=data, verify=False)
    return response.status_code == 200

def should_send_notification(tracker_file, task_time):
    """Determine if the notification should be sent based on the last notification time."""
    if os.path.exists(tracker_file):
        with open(tracker_file, 'r') as f:
            last_notification_time = f.read().strip()
        if last_notification_time == task_time:
            return False
    with open(tracker_file, 'w') as f:
        f.write(task_time)
    return True

def truncate_task_description(task_description, trunc_length):
    """Truncate the task description without cutting off words improperly and ensuring ellipsis fit."""
    if len(task_description) <= trunc_length:
        return task_description
    end = trunc_length
    while end > 0 and task_description[end] != ' ':
        end -= 1
    if end == 0:  # No space found, just truncate normally
        truncated = task_description[:trunc_length - 3].strip()
        return truncated + '...'
    truncated = task_description[:end].strip()
    while len(truncated) + 3 > trunc_length:
        truncated = truncated[:len(truncated) - 1].strip()
    return truncated + '...'

def format_date(dt):
    """Format the date without leading zeros in the month and day."""
    return dt.strftime(f'%-m/%-d/%y')

def pad_task_description_with_date(description, formatted_date, total_length):
    """Pad the task description with spaces to ensure it and the date fit to the specified total length."""
    space_needed = total_length - len(description) - len(formatted_date) - 3  # account for ' ()'
    padded_description = description + ' ' * space_needed
    return f'{padded_description} ({formatted_date})'

def create_symlink():
    """Create a symlink if user agrees."""
    home_dir = os.getenv('HOME')
    target = os.path.join(home_dir, 'storage', 'shared', 'Downloads', 'logpush')
    link_name = os.path.join(home_dir, 'logpush')

    if not os.path.exists(target):
        print(f"Target directory {target} does not exist.")
        return

    if os.path.exists(link_name):
        print(f"Symlink {link_name} already exists.")
        return

    os.symlink(target, link_name)
    print(f"Symlink created: {link_name} -> {target}")

def main():
    if gethostname() == 'localhost':
        is_termux_user = input("Are you using Termux on an Android device? (Y/n): ").strip().lower()
        if is_termux_user in ['y', '']:
            create_symlink_option = input("Would you like to create a symlink in your $HOME directory for easier access? (Y/n): ").strip().lower()
            if create_symlink_option in ['y', '']:
                create_symlink()

    config_path = CONFIG_PATH
    create_default_config(config_path)
    config = load_config(config_path)
    if not config:
        print("Configuration file not found and default configuration created.")
        config = load_config(config_path)

    if 'paths' not in config or 'default' not in config['paths']:
        print("Configuration paths are missing. Please provide the necessary paths.")
        config['paths'] = {
            'default': {
                "markdown": "",
                "output_dir": "",
                "pushwidget_target": "",
                "notification_tracker": ""
            }
        }
        save_config(config, config_path)

    paths = get_task_file_paths(config)
    if not paths or not all(paths.values()):
        print('Configuration paths are missing. Please provide the necessary paths.')
        prompt_for_paths(config['paths']['default'])
        save_config(config, config_path)
        paths = config['paths']['default']

    markdown_file = paths['markdown']
    output_dir = paths['output_dir']
    pushWidget_target = paths['pushWidget_target']
    notification_tracker = paths['notification_tracker']

    if not markdown_file or not output_dir or not pushWidget_target or not notification_tracker:
        print("One or more required paths are not set. Please check your configuration.")
        return

    save_config(config, config_path)

    pushbullet_api_key = get_api_key(config)
    if not pushbullet_api_key:
        return

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(pushWidget_target, exist_ok=True)

    now = datetime.now()

    if not os.path.exists(markdown_file):
        print(f"Markdown file not found at {markdown_file}.")
        return

    with open(markdown_file) as f:
        lines = f.readlines()

    max_tasks = 5
    total_length = 40  # Total length (you can adjust this value)
    tasks = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('- TODO'):
            task_description = parse_task_line(line)
            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ''
            if 'SCHEDULED:' in next_line:
                scheduled_date, scheduled_time = parse_scheduled_line(next_line)
                if scheduled_date:
                    scheduled_date_time = datetime.strptime(f'{scheduled_date} {scheduled_time}', '%Y-%m-%d %H:%M') if scheduled_time else datetime.strptime(scheduled_date, '%Y-%m-%d')
                    tasks.append((task_description, scheduled_date_time))
                    i += 1
                else:
                    tasks.append((task_description, None))
            else:
                tasks.append((task_description, None))
        i += 1

    # Sorting tasks by due date, tasks with no dates go to the end
    tasks.sort(key=lambda x: (x[1] is None, x[1] or datetime.max))

    for i in range(max_tasks):
        if i < len(tasks):
            task_description, scheduled_date_time = tasks[i]
            if scheduled_date_time:
                formatted_date = format_date(scheduled_date_time)
                date_length = len(formatted_date) + 3  # Length of formatted date including parentheses
                trunc_length_with_date = total_length - date_length  # Adjust length for description part
                truncated_task = truncate_task_description(task_description, trunc_length_with_date)
                display_task = pad_task_description_with_date(truncated_task, formatted_date, total_length)

                time_difference = scheduled_date_time - now
                if 0 <= time_difference.total_seconds() <= 180:
                    if should_send_notification(notification_tracker, scheduled_date_time.isoformat()):
                        title = 'Task Notification'
                        body = f'{display_task} is due soon!'
                        send_pushbullet_notification(pushbullet_api_key, title, body)
            else:
                truncated_task = truncate_task_description(task_description, total_length)
                display_task = truncated_task.ljust(total_length)
        else:
            display_task = ' ' * total_length  # Empty task with spaces to ensure consistent length
        write_task_file(display_task, i, pushWidget_target)

if __name__ == '__main__':
    main()