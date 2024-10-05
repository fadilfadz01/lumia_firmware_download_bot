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
SUPER_ADMIN = int(os.getenv("SUPER_ADMIN"))
REPO_CHANNEL = int(os.getenv("REPO_CHANNEL"))
UPLOAD_CHANNEL = int(os.getenv("UPLOAD_CHANNEL"))
REQUEST_CHANNEL = int(os.getenv("REQUEST_CHANNEL"))
UNBLOCK_CHANNEL = int(os.getenv("UNBLOCK_CHANNEL"))

user_states = {}
bot = telebot.TeleBot(API_TOKEN)

with open(f'{current_dir}/devices.json', 'r') as devices_file:
    devices = json.load(devices_file)

print("bot started running")


def is_user_admin(user):
    with open(f'{current_dir}/admins.json', 'r') as admins_file:
        admins = json.load(admins_file)

    if user.from_user.id in admins or user.from_user.id == SUPER_ADMIN:
        return True
    else:
        bot.reply_to(user, "You do not have admin privileges to use this request.")
        return False


def is_user_admin_by_id(user_id):
    with open(f'{current_dir}/admins.json', 'r') as admins_file:
        admins = json.load(admins_file)

    if user_id in admins or user_id == SUPER_ADMIN:
        return True
    else:
        return False


def is_user_blocked(user):
    with open(f'{current_dir}/blocked.json', 'r') as blocked_file:
        blocked_users = json.load(blocked_file)

    for blocked_user in blocked_users:
        if blocked_user['UserID'] == user.from_user.id:
            bot.reply_to(user, f"You have been blocked. Use /unblock to request to be unblocked.\n\n<b>"
                               f"Reason:</b> {blocked_user['Reason']}.",
                         parse_mode='HTML')
            return True
    return False


def load_user_data():
    with open(f'{current_dir}/users.json', 'r') as users_file:
        return json.load(users_file)


def check_user_limit(user_info):
    time_left = None
    users = load_user_data()
    current_time = datetime.now()
    user_requests = next((user for user in users if user['UserID'] == user_info.id), None)

    if user_requests is None:
        user_requests = {'UserID': user_info.id, "FullName": user_info.full_name, "UserName": user_info.username,
                         "Bot": user_info.is_bot, 'TotalRequests': 0,
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

    with open(f'{current_dir}/users.json', 'w') as json_file:
        json.dump(users, json_file, indent=4)

    return True, user_requests, time_left


def save_user_data(user_info):
    users = load_user_data()
    user_requests = next((user for user in users if user['UserID'] == user_info.id), None)

    if user_requests is not None:
        user_requests['TotalRequests'] += 1  # Increment the count
    with open(f'{current_dir}/users.json', 'w') as json_file:
        json.dump(users, json_file, indent=4)


@bot.message_handler(commands=['start'])
def send_welcome(message):
    if is_user_blocked(message):
        return

    users = load_user_data()
    user_requests = next((user for user in users if user['UserID'] == message.from_user.id), None)

    if user_requests is None and not is_user_admin_by_id(message.from_user.id):
        user_requests = {'UserID': message.from_user.id, "FullName": message.from_user.full_name,
                         "UserName": message.from_user.username,
                         "Bot": message.from_user.is_bot, 'TotalRequests': 0,
                         'LastRequested': datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        users.append(user_requests)

        with open(f'{current_dir}/users.json', 'w') as json_file:
            json.dump(users, json_file, indent=4)

        bot.send_message(message.chat.id,
                         'Hey there <a href="tg://user?id={}">{}</a>, and welcome to the Lumia Firmware Download Bot! '
                         'Use /download to get started with me.'.format(
                             message.from_user.id, message.from_user.first_name), parse_mode='HTML')
    else:
        bot.send_message(message.chat.id,
                         'Hey there <a href="tg://user?id={}">{}</a>, '
                         'and welcome back to the Lumia Firmware Download Bot! Use /download to get started with me.'
                         .format(message.from_user.id, message.from_user.first_name), parse_mode='HTML')


@bot.message_handler(commands=['download'])
def download_file(message):
    if is_user_blocked(message):
        return

    if not is_user_admin_by_id(message.from_user.id):
        allowed, user_requests, time_left = check_user_limit(message.from_user)
        if not allowed:
            hours, remainder = divmod(time_left.total_seconds(), 3600)
            minutes, seconds = divmod(remainder, 60)
            bot.reply_to(message, f"You have reached your daily limit of download requests. "
                                  f"You can download again in {int(hours)} hours, {int(minutes) + 1} minutes.",
                         parse_mode='HTML')
            return

    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton(device['ProductType'])
        for device in devices
        if any(product_codes.get('DownloadID', None) for product_codes in device['ProductCodes'])
    ]
    markup.add(*buttons)
    bot.reply_to(message, "Select your Lumia product type.\nUse /cancel to cancel the action.", reply_markup=markup)

    # Set the user state to indicate they're in the download process
    user_states[message.from_user.id] = 'awaiting_product_type'


@bot.message_handler(commands=['upload'])
def upload_file(message):
    if is_user_blocked(message):
        return

    user_states[message.from_user.id] = 'awaiting_upload_firmware'
    bot.reply_to(message, "Please send or forward your firmware package in ZIP format. Otherwise, it will be rejected. "
                          "You can also optionally include a caption about the firmware or any message for the "
                          "moderator.\nUse /cancel to cancel the action.\n\n"
                          "Note that sending or forwarding irrelevant files may result in you being blocked.",
                 reply_markup=ReplyKeyboardRemove())


@bot.message_handler(commands=['request'])
def request_file(message):
    if is_user_blocked(message):
        return

    params = message.text.split()

    # Check if the correct number of arguments are provided
    if len(params) < 3:
        bot.reply_to(message,
                     "<b>Usage:</b>\n\t/request &lt;ProductType&gt; "
                     "&lt;ProductCode&gt;\n\n<b>Example:</b>\n\t\t<code>/request RM-1085 059X4T0</code>\n\n"
                     "Note that abusing this feature will result in you being blocked.",
                     parse_mode='HTML')
        return

    product_type = params[1].upper()
    product_code = params[2].upper()

    device = next((d for d in devices if d['ProductType'] == product_type), None)
    valid_product_type = device is not None
    valid_product_code = False
    already_exists = False

    if valid_product_type:
        product_codes = device['ProductCodes']
        code = next((pc for pc in product_codes if pc['ProductCode'] == product_code), None)
        valid_product_code = code is not None
        already_exists = code.get('DownloadID') is not None if code else False

    if not valid_product_type:
        bot.reply_to(message, "Please type a valid product type.")
    elif not valid_product_code:
        bot.reply_to(message, "Please type a valid product code.")
    elif already_exists:
        bot.reply_to(message, f"The requested firmware for product type `{product_type}` with "
                              f"product code `{product_code}` is already in the repository\.",
                     parse_mode='MarkdownV2')
    else:
        bot.send_message(REQUEST_CHANNEL, f"<b>User ID:</b> {message.from_user.id}\n"
                                          f"<b>Fullname:</b> {message.from_user.full_name}\n"
                                          f"<b>Username:</b> {message.from_user.username}\n"
                                          f"<b>Product Type:</b> {product_type}\n"
                                          f"<b>Product Code:</b> {product_code}",
                         parse_mode='HTML')
        bot.reply_to(message, f"Your request has been successfully accepted\. We will add the firmware for "
                              f"product type `{product_type}` with product code `{product_code}` as soon as possible\.",
                     parse_mode='MarkdownV2')


@bot.message_handler(commands=['unblock'])
def request_unblock(message):
    params = message.text.split()

    # Check if the correct number of arguments are provided
    if len(params) < 2:
        bot.reply_to(message,
                     "<b>Usage:</b>\n\t/unblock &lt;Reason&gt;\n\n"
                     "<b>Example:</b>\n\t\t<code>/unblock Sorry, I will never abuse the bot again.</code>",
                     parse_mode='HTML')
        return

    bot.send_message(UNBLOCK_CHANNEL, f"<b>User ID:</b> {message.from_user.id}\n"
                                      f"<b>Fullname:</b> {message.from_user.full_name}\n"
                                      f"<b>Username:</b> {message.from_user.username}\n"
                                      f"<b>Reason:</b> {message.text.split(' ', 1)[1]}",
                     parse_mode='HTML')


@bot.message_handler(commands=['add_admin'])
def add_admin(message):
    if not message.chat.id == SUPER_ADMIN:
        bot.reply_to(message, "Only super admin can use this request.")
        return

    params = message.text.split()

    if len(params) < 2:
        bot.reply_to(message, "<b>Usage:</b>\n\t/add_admin &lt;UserID&gt;\n\n"
                              "<b>Example:</b>\n\t\t<code>/add_admin 1234567890</code>",
                     parse_mode='HTML')
        return

    with open(f'{current_dir}/admins.json', 'r') as json_file:
        admins = json.load(json_file)

    try:
        int(params[1])
    except:
        bot.reply_to(message, "Please type a valid user ID.")
        return
    if not int(params[1]) in admins and not int(params[1]) == SUPER_ADMIN:
        admins.append(int(params[1]))
        with open(f'{current_dir}/admins.json', 'w') as json_file:
            json.dump(admins, json_file, indent=4)

        bot.reply_to(message, "The user has been promoted to admin privileges.")
    else:
        bot.reply_to(message, "The user is already an admin.")


@bot.message_handler(commands=['remove_admin'])
def remove_admin(message):
    if not message.chat.id == SUPER_ADMIN:
        bot.reply_to(message, "Only super admin can use this request.")
        return
    bot.reply_to(message, "Coming soon...")


@bot.message_handler(commands=['get_id'])
def get_user_id(message):
    if not is_user_admin(message):
        return

    user_states[message.from_user.id] = 'awaiting_forward_message'
    bot.reply_to(message, "Please forward a message from the user you wish to retrieve their user ID.\n"
                          "Use /cancel to cancel the action.", reply_markup=ReplyKeyboardRemove())


@bot.message_handler(commands=['block_user'])
def block_user(message):
    if not is_user_admin(message):
        return

    params = message.text.split()

    if len(params) < 3:
        bot.reply_to(message, "<b>Usage:</b>\n\t/block_user &lt;UserID&gt; &lt;Reason&gt;\n\n"
                              "<b>Example:</b>\n\t\t<code>/block_user 1234567890 For abusing the bot.</code>",
                     parse_mode='HTML')
        return

    try:
        int(params[1])
    except:
        bot.reply_to(message, "Please type a valid user ID.")
        return

    if is_user_admin_by_id(int(params[1])):
        bot.reply_to(message, "You're unable to block an admin.")
        return

    with open(f'{current_dir}/blocked.json', 'r') as json_file:
        blocked_users = json.load(json_file)

    for blocked_user in blocked_users:
        if blocked_user['UserID'] == int(params[1]):
            bot.reply_to(message, "The user has already been blocked.")
            return

    blocked_users.append({"UserID": int(params[1]), "Reason": " ".join(message.text.split()[2:])})
    with open(f'{current_dir}/blocked.json', 'w') as json_file:
        json.dump(blocked_users, json_file, indent=4)

    bot.reply_to(message, f"Successfully blocked the user ID `{params[1]}`", parse_mode='MarkdownV2')


@bot.message_handler(commands=['unblock_user'])
def unblock_user(message):
    if not is_user_admin(message):
        return

    params = message.text.split()

    if len(params) < 2:
        bot.reply_to(message, "<b>Usage:</b>\n\t/unblock_user &lt;UserID&gt;\n\n"
                              "<b>Example:</b>\n\t\t<code>/unblock_user 1234567890</code>",
                     parse_mode='HTML')
        return

    with open(f'{current_dir}/blocked.json', 'r') as json_file:
        blocked_users = json.load(json_file)

    try:
        int(params[1])
    except:
        bot.reply_to(message, "Please type a valid user ID.")
        return

    blocked_users = [user for user in blocked_users if user["UserID"] != int(params[1])]
    with open(f'{current_dir}/blocked.json', 'w') as json_file:
        json.dump(blocked_users, json_file, indent=4)

    bot.reply_to(message, f"Successfully unblocked the user ID `{params[1]}`", parse_mode='MarkdownV2')


@bot.message_handler(commands=['blocked_users'])
def blocked_users_list(message):
    if not is_user_admin(message):
        return

    with open(f'{current_dir}/blocked.json', 'r') as json_file:
        blocked_users = json.load(json_file)

    content = str()
    for blocked_user in blocked_users:
        content += f"UserID: <code>{blocked_user['UserID']}</code>,  Reason: <code>{blocked_user['Reason']}</code>\n"
    if blocked_users:
        bot.reply_to(message, f"<b>Blocked Users</b>\n\n{content}", parse_mode='HTML')
    else:
        bot.reply_to(message, "<b>Blocked Users</b>\n\nThere are no blocked users in the list.", parse_mode='HTML')


@bot.message_handler(commands=['administrators'])
def bot_administrators(message):
    if is_user_admin(message):
        bot.reply_to(message, "<b>Admin Commands</b>\n\n"
                              "/add_admin - Promote a user to admin privileges.\n"
                              "/remove_admin - Demote a user from admin privileges.\n"
                              "/get_id - Retrieve the user ID of a user.\n"
                              "/block_user - Block a user from using the bot.\n"
                              "/unblock_user - Unblock a user from using the bot.\n"
                              "/blocked_users - Display the list of blocked user.", parse_mode='HTML')


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
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True, row_width=2)

    if any(device['ProductType'] == message.text.upper() for device in devices):
        buttons = [
            KeyboardButton(product_codes['ProductCode'])
            for device in devices
            if device['ProductType'] == message.text.upper()  # Filter based on ProductType
            for product_codes in device['ProductCodes']
            if product_codes.get('DownloadID', None)
        ]

        if len(buttons) > 0:
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
        bot.reply_to(message, "Please select a valid product type.")


@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[
    message.from_user.id] == 'awaiting_product_code')
def handle_product_code(message):
    if any(product_codes['ProductCode'] == message.text.upper()
           for device in devices
           for product_codes in device['ProductCodes']):

        # Clear the user's state after handling the request
        del user_states[message.from_user.id]

        matching_device = [device for device in devices
                           if any(product_codes['ProductCode'] == message.text.upper()
                                  for product_codes in device['ProductCodes'])][0]

        download_id = [
            product_codes.get('DownloadID', None)
            for product_codes in matching_device['ProductCodes']
            if product_codes['ProductCode'] == message.text.upper()
        ][0]

        if download_id:
            #bot.copy_message(message.chat.id, CHANNEL_ID, download_id, protect_content=True, reply_markup=ReplyKeyboardRemove())
            msg = bot.send_message(message.chat.id, "Please wait...", reply_markup=ReplyKeyboardRemove())
            bot.forward_message(message.chat.id, REPO_CHANNEL, download_id, protect_content=True)
            bot.delete_message(message.chat.id, msg.message_id)

            if not is_user_admin_by_id(message.from_user.id):
                save_user_data(message.from_user)
        else:
            bot.reply_to(message, f"There is no firmware available in the repository for "
                                  f"product type `{matching_device['ProductType']}` with "
                                  f"product code `{message.text}`, but you can request it using /request\.",
                         parse_mode='MarkdownV2', reply_markup=ReplyKeyboardRemove())

    else:
        bot.reply_to(message, "Please select a valid product code.")


@bot.message_handler(content_types=['document'],
                     func=lambda message: message.from_user.id in user_states and user_states[
                         message.from_user.id] == 'awaiting_upload_firmware')
def handle_upload_file(message):
    """print(message.document.file_id)
    print(message.document.file_unique_id)
    print(message.document.file_size)
    print(message.document.file_name)
    print(message.document.mime_type)"""
    if message.document.mime_type == "application/zip" and message.document.file_name.lower().endswith(".zip"):
        # Clear the user's state after handling the request
        del user_states[message.from_user.id]

        bot.forward_message(UPLOAD_CHANNEL, message.chat.id, message.message_id)
        bot.reply_to(message, "Thank you for helping us extend the repository. "
                              "We will review this firmware package and add it to the repository soon.")
    else:
        bot.reply_to(message, "Sorry, the firmware package must be in ZIP format.")


@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[
    message.from_user.id] == 'awaiting_forward_message')
def handle_user_id(message):
    if message.forward_from:
        bot.reply_to(message, f"User ID: `{message.forward_from.id}`", parse_mode='MarkdownV2')

        # Clear the user's state after handling the request
        del user_states[message.from_user.id]
    else:
        bot.reply_to(message, "Couldn't retrieve the user ID.\nThis may be because you are forwarding a message"
                              " from a hidden user, or you are not forwarding a message at all.")


# Start polling
#bot.polling()
while True:
    try:
        bot.polling()
    except Exception as e:
        print(e)
        print("bot restarted.")
