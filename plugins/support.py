#  Dragon-Userbot - telegram userbot
#  Copyright (C) 2020-present Dragon Userbot Organization
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.

#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

from pyrogram import Client, filters
from pyrogram.types import Message

from utils.misc import modules_help, prefix, userbot_version, python_version


@Client.on_message(filters.command(["support", "repo"], prefix) & filters.me)
async def support(_, message: Message):
    await message.edit(
        f"<b>Dragon-Userbot\n"
        "GitHub: <a href=https://github.com/Dragon-Userbot/Dragon-Userbot>Dragon-Userbot/Dragon-Userbot</a>\n"
        "Custom modules repository: <a href=https://github.com/Dragon-Userbot/custom_modules>"
        "Dragon-Userbot/custom_modules</a>\n"
        "License: <a href=https://github.com/Dragon-Userbot/Dragon-Userbot/blob/master/LICENSE>GNU GPL v3</a>\n\n"
        "Channel: @Dragon_Userbot\n"
        "Custom modules: @Dragon_Userbot_modules\n"
        "Chat [RU]: @Dragon_Userbot_chat\n"
        "Chat [EN]: @Dragon_Userbot_chat_en\n"
        "Main developers: @john_phonk, @thefsch, @nalinor\n\n"
        f"Python version: {python_version}\n"
        f"Modules count: {len(modules_help) / 1}\n</b>",
        disable_web_page_preview=True,
    )


@Client.on_message(filters.command(["version", "ver"], prefix) & filters.me)
async def version(client: Client, message: Message):
    changelog = ""
    async for m in client.search_messages("dRaGoN_uB_cHaNgElOg", query=userbot_version):
        if userbot_version in m.text:
            changelog = m.message_id

    await message.delete()
    await message.reply(
        f"<b>Dragon Userbot version: {userbot_version}\n"
        f"Changelog </b><i><a href=https://t.me/dRaGoN_uB_cHaNgElOg/{changelog}>in channel</a></i>.<b>\n"
        f"Changelogs are written by </b><i>"
        f"<a href=tg://user?id=318865588>\u2060</a>"
        f"<a href=tg://user?id=293490416>♿️</a>"
        f"<a href=https://t.me/LKRinternationalrunetcomphinc>asphuy</a>"
        f"<a href=https://t.me/artemjj2>♿️</a></i>",
    )


modules_help.append(
    {
        "support": [
            {"support": "Information about userbot"},
            {"version": "Check userbot version"},
        ]
    }
)
