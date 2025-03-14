import datetime

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
    await message.edit("Reminder set to ...")

    possible_text0 = "remind to drink a bear / 0d / count"
    possible_text0 = "remind to drink a bear / H / count"
    possible_text = "remind to drink a bear / H:M / count"
    possible_text2 = "remind to drink a bear / H:M:S / count"

    remind_text, interval_raw_text, times = message.text.split("/")

    remind_text: str = remind_text.strip()
    interval_raw_text: str = interval_raw_text.strip()
    times: int = int(times.strip())

    time_parts = list(map(int, interval_raw_text.split(":")))

    match len(time_parts):
        case 1:
            interval_seconds = time_parts[0] * 3600
        case 2:
            interval_seconds = time_parts[0] * 3600 + time_parts[1] * 60
        case 3:
            interval_seconds = time_parts[0] * 3600 + time_parts[1] * 60 + time_parts[2]
        case _:
            await message.edit("Invalid interval format.")
            return

    for i in range(1, times):
        now = datetime.datetime.now(tz=pytz.timezone("Europe/Kyiv"))

        if "d" in interval_raw_text:
            ...
        await client.send_message(message.chat.id, remind_text, schedule_date=now+datetime.timedelta(seconds=interval_seconds*i))



module = modules_help.add_module("reminder", __file__)
module.add_command("reminder", "Added reminder to following user with interval in H:M or H:M:S", "[reply]*")
