import os
import json
import telebot
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telebot.types import ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton

# Get the current directory of the script
current_dir = os.path.dirname(os.path.abspath(__file__))

# Replace with your bot token
load_dotenv()
API_TOKEN = os.getenv("API_TOKEN")
FIRMWARE_CHANNEL = int(os.getenv("FIRMWARE_CHANNEL"))
EMERGENCY_CHANNEL = int(os.getenv("EMERGENCY_CHANNEL"))
UPLOAD_CHANNEL = int(os.getenv("UPLOAD_CHANNEL"))
REQUEST_CHANNEL = int(os.getenv("REQUEST_CHANNEL"))
UNBLOCK_CHANNEL = int(os.getenv("UNBLOCK_CHANNEL"))

user_states = {}
bot = telebot.TeleBot(API_TOKEN)

print("bot started running")


def super_admins():
    load_dotenv(override=True)
    return [int(admin_id.strip()) for admin_id in os.getenv("SUPER_ADMIN", "").split(',') if admin_id.strip()]


def load_json(file_name):
    try:
        with open(f'{current_dir}/{file_name}', 'r') as json_file:
            return json.load(json_file)
    except:
        with open(f'{current_dir}/{file_name}', 'w') as json_file:
            json.dump([], json_file, indent=4)
            return []


def dump_json(file_name, data):
    with open(f'{current_dir}/{file_name}', 'w') as json_file:
        return json.dump(data, json_file, indent=4)


def is_user_id_valid(user_id, chat, check_exist=True):
    try:
        int(user_id)
        if check_exist:
            try:
                bot.get_chat(int(user_id))
            except:
                bot.reply_to(chat, "This user ID does not exist.")
                return False

        return True
    except:
        bot.reply_to(chat, "Please enter a valid user ID.")
        return False


def is_user_admin(user):
    admins = load_json('admins.json')
    if any(admin['UserID'] == user.from_user.id for admin in admins) or user.from_user.id in super_admins():
        return True
    else:
        bot.reply_to(user, "You do not have admin privileges to use this request.")
        return False


def is_user_admin_by_id(user_id):
    admins = load_json('admins.json')
    if any(admin['UserID'] == user_id for admin in admins) or user_id in super_admins():
        return True
    else:
        return False


def is_user_blocked(user):
    blocked_users = load_json('blocked.json')
    for blocked_user in blocked_users:
        if blocked_user['UserID'] == user.from_user.id:
            bot.reply_to(user, f"You have been blocked. Use /unblock to request to be unblocked.\n\n<b>"
                               f"Reason:</b> {blocked_user['Reason']}.",
                         parse_mode='HTML')
            return True
    return False


def check_user_limit(user_info):
    time_left = None
    users = load_json('users.json')
    current_time = datetime.now()
    user_requests = next((user for user in users if user['UserID'] == user_info.id), None)

    if user_requests is None:
        user_requests = {'UserID': user_info.id, "Fullname": user_info.full_name,
                         'Username': f"{'@' + user_info.username if user_info.username else ''}",
                         'Bot': user_info.is_bot, 'TotalRequests': 0,
                         'LastRequested': current_time.strftime("%Y-%m-%d %H:%M:%S")}
        users.append(user_requests)
    elif current_time > datetime.strptime(user_requests['LastRequested'], "%Y-%m-%d %H:%M:%S") + timedelta(days=1):
        user_requests['TotalRequests'] = 0  # Reset count for a new day
    else:
        time_left = (datetime.strptime(user_requests['LastRequested'], "%Y-%m-%d %H:%M:%S")
                     + timedelta(days=1) - current_time)

    if user_requests['TotalRequests'] >= 2:
        return False, user_requests, time_left  # Limit reached
    else:
        user_requests['LastRequested'] = current_time.strftime("%Y-%m-%d %H:%M:%S")

    dump_json('users.json', users)

    return True, user_requests, time_left


def save_user_data(user_info):
    users = load_json('users.json')
    user_requests = next((user for user in users if user['UserID'] == user_info.id), None)

    if user_requests is not None:
        user_requests['TotalRequests'] += 1  # Increment the count

    dump_json('users.json', users)


@bot.message_handler(commands=['start'])
def send_welcome(message):
    if is_user_blocked(message):
        return

    users = load_json('users.json')
    user_requests = next((user for user in users if user['UserID'] == message.from_user.id), None)

    if user_requests is None:
        user_requests = {'UserID': message.from_user.id, "Fullname": message.from_user.full_name,
                         'Username': f"{'@' + message.from_user.username if message.from_user.username else ''}",
                         'Bot': message.from_user.is_bot, 'TotalRequests': 0,
                         'LastRequested': datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        users.append(user_requests)

        bot.send_message(message.chat.id,
                         'Hey there <a href="tg://user?id={}">{}</a>, and welcome to the Lumia Firmware Download Bot! '
                         'Use /download to get started with me.'.format(
                             message.from_user.id, message.from_user.first_name), parse_mode='HTML')

        if is_user_admin_by_id(message.from_user.id):
            return

        dump_json('users.json', users)
    else:
        bot.send_message(message.chat.id,
                         'Hey there <a href="tg://user?id={}">{}</a>, '
                         'and welcome back to the Lumia Firmware Download Bot! Use /download to get started with me.'
                         .format(message.from_user.id, message.from_user.first_name), parse_mode='HTML')


@bot.message_handler(commands=['download'])
def download_firmware(message):
    if is_user_blocked(message):
        return

    if not is_user_admin_by_id(message.from_user.id):
        allowed, user_requests, time_left = check_user_limit(message.from_user)
        if not allowed:
            hours, remainder = divmod(time_left.total_seconds(), 3600)
            minutes, seconds = divmod(remainder, 60)
            bot.reply_to(message, f"You have reached your limit of download requests. "
                                  f"You can download again in {int(hours)} hours, {int(minutes) + 1} minutes.",
                         parse_mode='HTML')
            return

    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True, row_width=2)
    devices = load_json('devices.json')
    buttons = [
        KeyboardButton(device['ProductType'])
        for device in devices
        if any(product_codes['DownloadID'] for product_codes in device['ProductCodes'])
    ]
    markup.add(*buttons)
    bot.reply_to(message, "Select your Lumia product type.\nUse /cancel to cancel the action.", reply_markup=markup)

    # Set the user state to indicate they're in the download process
    user_states[message.from_user.id] = 'awaiting_product_type'


@bot.message_handler(commands=['upload'])
def upload_firmware(message):
    if is_user_blocked(message):
        return

    user_states[message.from_user.id] = 'awaiting_upload_firmware'
    bot.reply_to(message, "Please send or forward your firmware package in ZIP format, "
                          "including a caption that specifies the firmware product type and product code. "
                          "You may also include any relevant messages if you wish. "
                          "Packages that do not meet these requirements, such as ZIP format and the necessary caption, "
                          "will be rejected.\n"
                          "Use /cancel to cancel the action.\n\n"
                          "Note that sending or forwarding irrelevant files may result in you being blocked.",
                 reply_markup=ReplyKeyboardRemove())


@bot.message_handler(commands=['request'])
def request_firmware(message):
    if is_user_blocked(message):
        return

    params = message.text.split()

    # Check if the correct number of arguments are provided
    if len(params) < 3:
        bot.reply_to(message,
                     "<b>Usage:</b>\n\t\t/request &lt;ProductType&gt; "
                     "&lt;ProductCode&gt;\n\n<b>Example:</b>\n\t\t<code>/request RM-1085 059X4T0</code>\n\n"
                     "Note that abusing this feature will result in you being blocked.",
                     parse_mode='HTML')
        return

    product_type = params[1].upper()
    product_code = params[2].upper()

    devices = load_json('devices.json')
    device = next((d for d in devices if d['ProductType'] == product_type), None)
    valid_product_type = device is not None
    valid_product_code = False
    already_exists = False

    if valid_product_type:
        product_codes = device['ProductCodes']
        code = next((pc for pc in product_codes if pc['ProductCode'] == product_code), None)
        valid_product_code = code is not None
        already_exists = code['DownloadID'] is not None if code['DownloadID'] else False

    if not valid_product_type:
        bot.reply_to(message, "Please enter a valid product type.")
    elif not valid_product_code:
        bot.reply_to(message, "Please enter a valid product code.")
    elif already_exists:
        bot.reply_to(message, f"The requested firmware for product type `{product_type}` with "
                              f"product code `{product_code}` is already in the repository\.",
                     parse_mode='MarkdownV2')
    else:
        bot.send_message(REQUEST_CHANNEL, f"<b>User ID:</b> <code>{message.from_user.id}</code>\n"
                                          f"<b>Fullname:</b> <code>{message.from_user.full_name}</code>\n"
                                          f"<b>Username:</b> {'@' + message.from_user.username if message.from_user.username else ''}\n"
                                          f"<b>Product Type:</b> <code>{product_type}</code>\n"
                                          f"<b>Product Code:</b> <code>{product_code}</code>",
                         parse_mode='HTML')
        bot.reply_to(message, f"Your request has been accepted\. We will add the firmware for "
                              f"product type `{product_type}` with product code `{product_code}` "
                              f"as soon as possible and will notify you\.",
                     parse_mode='MarkdownV2')


@bot.message_handler(commands=['emergency_files'])
def get_emergency_files(message):
    if is_user_blocked(message):
        return

    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True, row_width=2)
    devices = load_json('devices.json')
    buttons = [
        KeyboardButton(device['ProductType'])
        for device in devices
        if device['Emergency']["DownloadID"]
    ]
    markup.add(*buttons)
    bot.reply_to(message, "Select your Lumia product type.\nUse /cancel to cancel the action.", reply_markup=markup)

    # Set the user state to indicate they're in the download process
    user_states[message.from_user.id] = 'awaiting_emergency_files'


@bot.message_handler(commands=['unblock'])
def request_unblock(message):
    params = message.text.split()

    # Check if the correct number of arguments are provided
    if len(params) < 2:
        bot.reply_to(message,
                     "<b>Usage:</b>\n\t\t/unblock &lt;Reason&gt;\n\n"
                     "<b>Example:</b>\n\t\t<code>/unblock Sorry, I will never abuse the bot again.</code>",
                     parse_mode='HTML')
        return

    bot.send_message(UNBLOCK_CHANNEL, f"<b>User ID:</b> <code>{message.from_user.id}</code>\n"
                                      f"<b>Fullname:</b> <code>{message.from_user.full_name}</code>\n"
                                      f"<b>Username:</b> {'@' + message.from_user.username if message.from_user.username else ''}\n"
                                      f"<b>Reason:</b> <code>{message.text.split(' ', 1)[1]}</code>",
                     parse_mode='HTML')


@bot.message_handler(commands=['add_admin'])
def add_admin(message):
    if message.chat.id not in super_admins():
        bot.reply_to(message, "Only super admin can use this request.")
        return

    params = message.text.split()

    if len(params) < 2:
        bot.reply_to(message, "<b>Usage:</b>\n\t\t/add_admin &lt;UserID&gt;\n\n"
                              "<b>Example:</b>\n\t\t<code>/add_admin 1234567890</code>",
                     parse_mode='HTML')
        return

    admins = load_json('admins.json')

    if not is_user_id_valid(params[1], message):
        return

    user_id = int(params[1])

    blocked_users = load_json('blocked.json')
    if any(blocked_user["UserID"] == user_id for blocked_user in blocked_users):
        bot.reply_to(message, "You cannot promote a user who is blocked from using the bot.")
        return

    if user_id not in admins and user_id not in super_admins():
        user = bot.get_chat(user_id)

        admins.append({'UserID': user.id,
                       'Fullname': f"{user.first_name}{' ' + user.last_name if user.last_name else ''}",
                       'Username': f"{'@' + user.username if user.username else ''}"})
        dump_json('admins.json', admins)

        bot.reply_to(message, "The user has been promoted to admin privileges.")
    else:
        bot.reply_to(message, "The user is already an admin.")


@bot.message_handler(commands=['remove_admin'])
def remove_admin(message):
    if message.chat.id not in super_admins():
        bot.reply_to(message, "Only super admin can use this request.")
        return

    params = message.text.split()

    if len(params) < 2:
        bot.reply_to(message, "<b>Usage:</b>\n\t\t/remove_admin &lt;UserID&gt;\n\n"
                              "<b>Example:</b>\n\t\t<code>/remove_admin 1234567890</code>",
                     parse_mode='HTML')
        return

    admins = load_json('admins.json')

    if not is_user_id_valid(params[1], message, False):
        return

    user_id = int(params[1])

    if user_id in super_admins():
        bot.reply_to(message, "You cannot demote a super admin.")
        return
    elif any(admin['UserID'] == user_id for admin in admins):
        admins = [admin for admin in admins if admin['UserID'] != user_id]
        dump_json('admins.json', admins)

        bot.reply_to(message, "The user has been demoted from admin privileges.")
    else:
        bot.reply_to(message, "The user is already not an admin.")


@bot.message_handler(commands=['text_user'])
def text_user(message):
    if message.chat.id not in super_admins():
        bot.reply_to(message, "Only super admin can use this request.")
        return

    params = message.text.split()

    if len(params) < 3:
        bot.reply_to(message, "<b>Usage:</b>\n\t\t/text_user &lt;UserID&gt &lt;Message&gt;\n\n"
                              "<b>Example:</b>\n\t\t<code>/text_user 1234567890 "
                              "Hi! Hope you find using the bot useful.</code>",
                     parse_mode='HTML')
        return

    if not is_user_id_valid(params[1], message):
        return

    user_id = int(params[1])

    bot.send_message(user_id, " ".join(message.text.split()[2:]))
    bot.reply_to(message, "The user has been notified.")


@bot.message_handler(commands=['notify_all'])
def notify_users(message):
    if message.chat.id not in super_admins():
        bot.reply_to(message, "Only super admin can use this request.")
        return

    user_states[message.from_user.id] = 'awaiting_forward_message'
    bot.reply_to(message, "Send or forward the message you would like to notify.\nUse /cancel to cancel the action.",
                 reply_markup=ReplyKeyboardRemove())


@bot.message_handler(commands=['list_admins'])
def list_admins(message):
    if not is_user_admin(message):
        return

    admins = load_json('admins.json')

    content = str()
    for admin in admins:
        content += (f"UserID: <code>{admin['UserID']}</code>\n"
                    f"Fullname: <code>{admin['Fullname']}</code>\n"
                    f"Username: {admin['Username']}\n\n")

    if admins:
        bot.reply_to(message, f"<b>Admin Users</b>\n{content}\nNote that super admins will not be listed here.",
                     parse_mode='HTML')
    else:
        bot.reply_to(message, "<b>Admin Users</b>\nThere are currently no admins to display.\n"
                              "Super admins will not be listed here.", parse_mode='HTML')


@bot.message_handler(commands=['get_id'])
def get_user_id(message):
    if not is_user_admin(message):
        return

    user_states[message.from_user.id] = 'awaiting_user_message'
    bot.reply_to(message, "Please forward a message from the user you wish to retrieve their user ID.\n"
                          "Use /cancel to cancel the action.", reply_markup=ReplyKeyboardRemove())


@bot.message_handler(commands=['get_info'])
def get_user_info(message):
    if not is_user_admin(message):
        return

    params = message.text.split()

    if len(params) < 2:
        bot.reply_to(message, "<b>Usage:</b>\n\t\t/get_info &lt;UserID&gt;\n\n"
                              "<b>Example:</b>\n\t\t<code>/get_info 1234567890</code>",
                     parse_mode='HTML')
        return

    if not is_user_id_valid(params[1], message):
        return

    user_id = int(params[1])

    user = bot.get_chat(user_id)
    bot.reply_to(message,
                 f"<b>Fullname:</b> <code>{user.first_name}{' ' + user.last_name if user.last_name else ''}</code>\n"
                 f"<b>Username:</b> {'@' + user.username if user.username else ''}\n"
                 f"<b>Type:</b> {user.type}\n"
                 f"<b>Bio:</b> <code>{user.bio}</code>\n", parse_mode='HTML')


@bot.message_handler(commands=['block_user'])
def block_user(message):
    if not is_user_admin(message):
        return

    params = message.text.split()

    if len(params) < 3:
        bot.reply_to(message, "<b>Usage:</b>\n\t\t/block_user &lt;UserID&gt; &lt;Reason&gt;\n\n"
                              "<b>Example:</b>\n\t\t<code>/block_user 1234567890 For abusing the bot.</code>",
                     parse_mode='HTML')
        return

    if not is_user_id_valid(params[1], message):
        return

    user_id = int(params[1])

    if is_user_admin_by_id(user_id):
        bot.reply_to(message, "You're unable to block an admin.")
        return

    blocked_users = load_json('blocked.json')

    for blocked_user in blocked_users:
        if blocked_user['UserID'] == user_id:
            bot.reply_to(message, "The user has already been blocked.")
            return

    user = bot.get_chat(user_id)
    blocked_users.append({'UserID': user.id,
                          'Fullname': f"{user.first_name}{' ' + user.last_name if user.last_name else ''}",
                          'Username': f"{'@' + user.username if user.username else ''}",
                          'Reason': " ".join(message.text.split()[2:])})
    dump_json('blocked.json', blocked_users)

    bot.reply_to(message, f"Successfully blocked the user ID `{params[1]}`", parse_mode='MarkdownV2')


@bot.message_handler(commands=['unblock_user'])
def unblock_user(message):
    if not is_user_admin(message):
        return

    params = message.text.split()

    if len(params) < 2:
        bot.reply_to(message, "<b>Usage:</b>\n\t\t/unblock_user &lt;UserID&gt;\n\n"
                              "<b>Example:</b>\n\t\t<code>/unblock_user 1234567890</code>",
                     parse_mode='HTML')
        return

    blocked_users = load_json('blocked.json')

    if not is_user_id_valid(params[1], message, False):
        return

    user_id = int(params[1])

    if not any(blocked_user["UserID"] == user_id for blocked_user in blocked_users):
        bot.reply_to(message, "The user is not blocked, so there is no need to unblock them.")
        return

    blocked_users = [blocked_user for blocked_user in blocked_users if blocked_user["UserID"] != user_id]
    dump_json('blocked.json', blocked_users)

    bot.reply_to(message, f"Successfully unblocked the user ID `{params[1]}`", parse_mode='MarkdownV2')


@bot.message_handler(commands=['blocked_users'])
def blocked_users_list(message):
    if not is_user_admin(message):
        return

    blocked_users = load_json('blocked.json')

    content = str()
    for blocked_user in blocked_users:
        content += (f"UserID: <code>{blocked_user['UserID']}</code>\n"
                    f"Fullname: <code>{blocked_user['Fullname']}</code>\n"
                    f"Username: {blocked_user['Username']}\n"
                    f"Reason: <code>{blocked_user['Reason']}</code>\n\n")

    if blocked_users:
        bot.reply_to(message, f"<b>Blocked Users</b>\n{content}", parse_mode='HTML')
    else:
        bot.reply_to(message, "<b>Blocked Users</b>\nThere are no blocked users yet.", parse_mode='HTML')


@bot.message_handler(commands=['administrators'])
def bot_administrators(message):
    if is_user_admin(message):
        bot.reply_to(message, "<b>Super Admin Commands</b>\n"
                              "/add_admin - Promote a user to admin privileges.\n"
                              "/remove_admin - Demote a user from admin privileges.\n"
                              "/text_user - Send a message to a bot user.\n"
                              "/notify_all - Send a message to all the bot users.\n\n"
                              "<b>Admin Commands</b>\n"
                              "/list_admins - Display the list of admins.\n"
                              "/get_id - Retrieve the user ID of a user.\n"
                              "/get_info - Retrieve the user info of a user.\n"
                              "/block_user - Block a user from using the bot.\n"
                              "/unblock_user - Unblock a user from using the bot.\n"
                              "/blocked_users - Display the list of blocked users.", parse_mode='HTML')


@bot.message_handler(commands=['cancel'])
def cancel_process(message):
    if is_user_blocked(message):
        return

    # Clear the user's state if they are in the process
    if message.from_user.id in user_states:
        del user_states[message.from_user.id]
        bot.reply_to(message, "The action has been cancelled.", reply_markup=ReplyKeyboardRemove())
    else:
        bot.reply_to(message, "There is no ongoing action to cancel.", reply_markup=ReplyKeyboardRemove())


@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[
    message.from_user.id] == 'awaiting_product_type')
def handle_product_type(message):
    devices = load_json('devices.json')

    if any(device['ProductType'] == message.text.upper() for device in devices):
        buttons = [
            KeyboardButton(product_codes['ProductCode'])
            for device in devices
            if device['ProductType'] == message.text.upper()  # Filter based on ProductType
            for product_codes in device['ProductCodes']
            if product_codes['DownloadID']
        ]

        if len(buttons) > 0:
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True, row_width=2)
            markup.add(*buttons)
            bot.reply_to(message, "Select your Lumia product code.\nUse /cancel to cancel the action.",
                         reply_markup=markup)

            # Update the user state
            user_states[message.from_user.id] = 'awaiting_product_code'
        else:
            bot.reply_to(message,
                         f"There is no firmware available in the repository for product type `{message.text}`, "
                         f"but you can request it using /request\.",
                         parse_mode='MarkdownV2', reply_markup=ReplyKeyboardRemove())

    else:
        bot.reply_to(message, "Please select a valid product type.\nUse /cancel to cancel the action.")


@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[
    message.from_user.id] == 'awaiting_product_code')
def handle_product_code(message):
    devices = load_json('devices.json')
    if any(product_codes['ProductCode'] == message.text.upper()
           for device in devices
           for product_codes in device['ProductCodes']):

        # Clear the user's state after handling the request
        del user_states[message.from_user.id]

        matching_device = [device for device in devices
                           if any(product_codes['ProductCode'] == message.text.upper()
                                  for product_codes in device['ProductCodes'])][0]

        download_id = [
            product_codes['DownloadID']
            for product_codes in matching_device['ProductCodes']
            if product_codes['ProductCode'] == message.text.upper()
        ][0]

        if len(download_id) == 1:
            bot.copy_message(message.chat.id, FIRMWARE_CHANNEL, download_id[0], reply_to_message_id=message.message_id,
                             protect_content=True, reply_markup=ReplyKeyboardRemove())
        elif len(download_id) > 1:
            msg = bot.send_message(message.chat.id, "Please wait...", reply_markup=ReplyKeyboardRemove())
            bot.delete_message(message.chat.id, msg.message_id)
            bot.copy_messages(message.chat.id, FIRMWARE_CHANNEL, download_id, protect_content=True)
        else:
            bot.reply_to(message, f"There is no firmware available in the repository for "
                                  f"product type `{matching_device['ProductType']}` with "
                                  f"product code `{message.text}`, but you can request it using /request\.",
                         parse_mode='MarkdownV2', reply_markup=ReplyKeyboardRemove())
            return

        if not is_user_admin_by_id(message.from_user.id):
            save_user_data(message.from_user)
    else:
        bot.reply_to(message, "Please select a valid product code.\nUse /cancel to cancel the action.")


@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[
    message.from_user.id] == 'awaiting_emergency_files')
def handle_emergency_files(message):
    devices = load_json('devices.json')

    if any(device['ProductType'] == message.text.upper() for device in devices):
        del user_states[message.from_user.id]

        download_id = next((device['Emergency']['DownloadID'] for device in devices
                            if device['ProductType'] == message.text.upper()
                            if device['Emergency']['DownloadID']), None)

        if download_id:
            bot.copy_message(message.chat.id, EMERGENCY_CHANNEL, download_id, reply_to_message_id=message.message_id,
                             protect_content=True, reply_markup=ReplyKeyboardRemove())
        else:
            bot.reply_to(message, f"There is no emergency flash files available in the repository "
                                  f"for product type `{message.text}`\.",
                         parse_mode="MarkdownV2", reply_markup=ReplyKeyboardRemove())
    else:
        bot.reply_to(message, "Please select a valid product type.\nUse /cancel to cancel the action.")


@bot.message_handler(content_types=['document'],
                     func=lambda message: message.from_user.id in user_states and user_states[
                         message.from_user.id] == 'awaiting_upload_firmware')
def handle_upload_file(message):
    """print(message.document.file_id)
    print(message.document.file_unique_id)
    print(message.document.file_size)
    print(message.document.file_name)
    print(message.document.mime_type)"""

    bot.forward_message(UPLOAD_CHANNEL, message.chat.id, message.message_id)

    if message.document.mime_type == "application/zip" and message.document.file_name.lower().endswith(".zip"):
        # Clear the user's state after handling the request
        del user_states[message.from_user.id]

        bot.reply_to(message, "Thank you for helping us extend the repository. "
                              "We will review this firmware package and add it to the repository soon.")
    else:
        bot.reply_to(message, "Sorry, the firmware package must be in ZIP format. Please send a new one.\n"
                              "Use /cancel to cancel the action.")


@bot.message_handler(content_types=['text', 'document', 'photo', 'video', 'sticker', 'animation'],
                     func=lambda message: message.from_user.id in user_states and user_states[
                         message.from_user.id] == 'awaiting_forward_message')
def handle_forward_message(message):
    users = load_json('users.json')
    admins = load_json('admins.json')

    # Clear the user's state after handling the request
    del user_states[message.from_user.id]

    # Function to send messages
    def send_message(target_id, source_id, content):
        try:
            bot.get_chat(target_id)
            bot.copy_message(target_id, source_id, content)
        except:
            pass

    msg = bot.send_message(message.chat.id, "Notifying users... please hold on.")

    # Notify all users and admins
    for target in users + admins:
        send_message(target["UserID"], message.chat.id, message.message_id)

    bot.delete_message(message.chat.id, msg.message_id)
    bot.reply_to(message, "All users have been notified.")


@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[
    message.from_user.id] == 'awaiting_user_message')
def handle_user_id(message):
    # Clear the user's state after handling the request
    del user_states[message.from_user.id]

    if message.forward_from:
        bot.reply_to(message, f"User ID: `{message.forward_from.id}`", parse_mode='MarkdownV2')
    else:
        bot.reply_to(message, "Couldn't retrieve the user ID.\nThis may be because you are forwarding a message "
                              "from a hidden user, or you are not forwarding a message at all.")


# Start polling
bot.infinity_polling()
