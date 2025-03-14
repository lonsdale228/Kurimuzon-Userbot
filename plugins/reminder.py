import datetime
import re

import pytz
from pyrogram import Client, enums, filters
from pyrogram.types import Message

from utils.filters import command
from utils.misc import modules_help
from utils.scripts import with_premium


@Client.on_message(
    ~filters.scheduled & command(["reminder"]) & filters.me & ~filters.forwarded
)
async def reminder(client: Client, message: Message):
    # possible_text0 = "remind to drink a bear / 0d / 2"
    # possible_text0 = "remind to drink a bear / 1h / 3"
    # possible_text = "remind to drink a bear / 1s / 1"
    # possible_text2 = "remind to drink a bear / 10s / 5"
    # possible_text2 = "remind to drink a bear / 10s / 6"
    # possible_text2 = "remind to drink a bear / 1h1s / 6"
    # possible_text2 = "remind to drink a bear / 1h30s / 6"
    # possible_text2 = "remind to drink a bear / 1h10m30s / 6"
    # possible_text2 = "remind to drink a bear / 2d1h10m30s / 6"
    # possible_text2 = "remind to drink a bear / 2d30s / 6"



    try:
        remind_text, interval_raw_text, times = message.text.split("/")
    except ValueError:
        await message.edit("Format error: please use 'text / interval / times'")
        return

    remind_text: str = remind_text.split(".reminder")[1].strip()
    interval_raw_text = interval_raw_text.strip()
    try:
        times = int(times.strip())
    except ValueError:
        await message.edit("Invalid number of times provided.")
        return

    pattern = r"(\d+)([dhms])"
    matches = re.findall(pattern, interval_raw_text)
    if not matches:
        await message.edit("Invalid interval format. Use combinations like '2d1h10m30s'.")
        return

    seconds_map = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    interval_seconds = 0
    for value, unit in matches:
        interval_seconds += int(value) * seconds_map[unit.lower()]

    if interval_seconds <= 0:
        await message.edit("Interval must be greater than zero.")
        return

    # remind_text: str = remind_text.strip()
    # interval_raw_text: str = interval_raw_text.strip()
    # times: int = int(times.strip())
    #
    # time_parts = list(map(int, interval_raw_text.split(":")))
    #
    # match len(time_parts):
    #     case 1:
    #         interval_seconds = time_parts[0] * 3600
    #     case 2:
    #         interval_seconds = time_parts[0] * 3600 + time_parts[1] * 60
    #     case 3:
    #         interval_seconds = time_parts[0] * 3600 + time_parts[1] * 60 + time_parts[2]
    #     case _:
    #         await message.edit("Invalid interval format.")
    #         return

    for i in range(1, times + 1):
        now = datetime.datetime.now(tz=pytz.timezone("Europe/Kyiv"))
        scheduled_time = now + datetime.timedelta(seconds=interval_seconds * i)
        await client.send_message(message.chat.id, remind_text, schedule_date=scheduled_time)

    await message.delete()

module = modules_help.add_module("reminder", __file__)
module.add_command("reminder", "Added reminder to following user with interval in H:M or H:M:S", "[reply]*")
