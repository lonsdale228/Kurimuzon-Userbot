import datetime
import re

import pytz
from pyrogram import Client, enums, filters
from pyrogram.types import Message

from utils.filters import command
from utils.misc import modules_help


@Client.on_message(
    ~filters.scheduled & command(["remind"]) & filters.me & ~filters.forwarded
)
async def reminder(client: Client, message: Message):
    try:
        remind_text, interval_raw_text, times = message.text.split("/")
    except ValueError:
        await message.edit("Format error: please use 'text / interval / times'")
        return

    remind_text: str = remind_text.split(".remind")[1].strip()
    interval_raw_text = interval_raw_text.strip()
    try:
        times = int(times.strip())
    except ValueError:
        await message.edit("Invalid number of times provided.")
        return

    cron_mode = False
    if interval_raw_text[0]=='c':
        cron_mode = True
        interval_raw_text = interval_raw_text[1:].strip()

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

    day, hour, minute, second = 0, 0, 0, 0
    for value, unit in matches:
        match unit:
            case "d":
                day = int(value)
            case "h":
                hour = int(value)
            case "m":
                minute = int(value)
            case "s":
                second = int(value)


    if cron_mode:
        now = datetime.datetime.now(tz=pytz.timezone("Europe/Kyiv"))
        first_reminder_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now > first_reminder_time:
            first_reminder_time += datetime.timedelta(days=1)
        for i in range(times):
            scheduled_time = first_reminder_time + datetime.timedelta(days=i)
            await client.send_message(message.chat.id, remind_text, schedule_date=scheduled_time)
    else:
        for i in range(1, times + 1):
            now = datetime.datetime.now(tz=pytz.timezone("Europe/Kyiv"))
            scheduled_time = now + datetime.timedelta(seconds=interval_seconds * i)
            await client.send_message(message.chat.id, remind_text, schedule_date=scheduled_time)

    await message.delete()

module = modules_help.add_module("remind", __file__)
module.add_command("remind", "Added reminder to following user with interval in '.remind text/10h10m10s/times' \n"
                             "Example: 'remind to drink a bear / 2d1h10m30s / 6'", "[reply]*")
