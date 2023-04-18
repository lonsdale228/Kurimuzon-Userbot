import asyncio
import datetime
import json
import os
import shutil
import typing
from enum import Enum
from io import BytesIO
from subprocess import PIPE, Popen

import arrow
import qrcode
from pyrogram import Client, filters
from pyrogram.types import Message

from utils.filters import command
from utils.misc import modules_help
from utils.scripts import get_args_raw, get_full_name, get_prefix

text_template = (
    "<emoji id=5472164874886846699>✨</emoji> WireGuard конфиг пользователя {0}!\n\n"
    "<b><emoji id=5818865088970362886>❕</b></emoji><b> Инструкция по установке:\n"
    "</b>Android/IOS:\n"
    "1. Скачать приложение из "
    '<a href="https://play.google.com/store/apps/details?id=com.wireguard.android">'
    'Play Market</a> или <a href="https://apps.apple.com/ru/app/wireguard/id1441195209">'
    "App Store</a>\n"
    "2. Нажать на плюсик и импортировать файл конфигурации или отсканировать QR код\n"
    "3. Включить VPN\n\n"
    "Windows/MacOS/Linux:\n"
    '1. Скачать приложение с <a href="https://www.wireguard.com/install/">официального сайта</a>\n'
    "2. Импортировать файл конфигурации\n"
    "3. Включить VPN\n\n"
)


def check_wireguard_installed(func):
    async def wrapped(client: Client, message: Message):
        if os.geteuid() != 0:
            return await message.edit("<b>This command must be run as root!</b>")

        if not shutil.which("wg"):
            return await message.edit_text(
                "<b>WireGuard is not installed!</b>\n"
                f"<b>Use</b> <code>{get_prefix()}wgi</code> <b>to install</b>"
            )

        return await func(client, message)

    return wrapped


def calculate_speed(rx_old, rx_new, tx_old, tx_new, time_elapsed):
    rx_speed = (rx_new - rx_old) / time_elapsed
    tx_speed = (tx_new - tx_old) / time_elapsed
    return format_speed(rx_speed), format_speed(tx_speed)


# Format the speed to human readable format
def format_speed(speed):
    if speed < 1024:
        return f"{speed:.2f}B/s"
    elif speed < 1024 * 1024:
        return f"{speed / 1024:.2f}KB/s"
    elif speed < 1024 * 1024 * 1024:
        return f"{speed / 1024 / 1024:.2f}MB/s"
    else:
        return f"{speed / 1024 / 1024 / 1024:.2f}GB/s"


def sh_exec(cmd: str) -> str:
    cmd_obj = Popen(
        cmd,
        shell=True,
        stdout=PIPE,
        stderr=PIPE,
        text=True,
        executable="/bin/bash",
    )
    stdout, stderr = cmd_obj.communicate()
    return stdout.strip() or stderr.strip()


class ClientErrorType(Enum):
    NAME_REQUIRED = 0
    CLIENT_ID_REQUIRED = 1
    CLIENT_ALREADY_EXIST = 2
    ADDRESS_LIMIT_REACHED = 3


class WireGuard:
    def __init__(self):
        self.wg_path = "/etc/wireguard"
        self.default_address = "10.13.13.x"

    def get_config(self) -> dict:
        # load config from json file
        try:
            with open(f"{self.wg_path}/wg0.json", "r") as f:
                config = json.load(f)
        except FileNotFoundError:
            config = self.__generate_config()
        return config

    def __generate_config(self):
        private_key = sh_exec("wg genkey")
        public_key = sh_exec(f"echo {private_key} | wg pubkey")
        address = self.default_address.replace("x", "1")

        result = {
            "server": {
                "private_key": private_key,
                "public_key": public_key,
                "address": address,
            },
            "clients": {},
        }

        self.__save_config(result)
        sh_exec("wg-quick down wg0")
        sh_exec("wg-quick up wg0")
        self.__sync_config()

        return result

    def save_config(self, config: dict):
        self.__save_config(config)
        self.__sync_config()

    def __save_config(self, config: dict) -> None:
        result = (
            "# Note: Do not edit this file manually!\n"
            "# Your changes will be overwritten!\n\n"
            "# Server\n"
            "[Interface]\n"
            f"PrivateKey = {config['server']['private_key']}\n"
            f"Address = {config['server']['address']}/24\n"
            "ListenPort = 51820\n"
            "PostUp = iptables -A FORWARD -i %i -j ACCEPT; "
            "iptables -A FORWARD -o %i -j ACCEPT; "
            "iptables -t nat -A POSTROUTING -o eth+ -j MASQUERADE\n"
            "PostDown = iptables -D FORWARD -i %i -j ACCEPT; "
            "iptables -D FORWARD -o %i -j ACCEPT; "
            "iptables -t nat -D POSTROUTING -o eth+ -j MASQUERADE\n\n"
        )

        for client_id, client in config["clients"].items():
            if not client["enabled"]:
                continue

            result += (
                f"# Client: {client['name']} ({client_id})\n"
                "[Peer]\n"
                f"PublicKey = {client['public_key']}\n"
                f"PresharedKey = {client['preshared_key']}\n"
                f"AllowedIPs = {client['address']}/32\n\n"
            )

        with open(f"{self.wg_path}/wg0.json", "w") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        with open(f"{self.wg_path}/wg0.conf", "w") as f:
            f.write(result)

    def __sync_config(self) -> None:
        sh_exec("wg syncconf wg0 <(wg-quick strip wg0)")

    def get_clients(self) -> dict:
        config = self.get_config()
        clients = [
            {
                "id": client_id,
                "name": client.get("name"),
                "enabled": client.get("enabled"),
                "address": client.get("address"),
                "public_key": client.get("public_key"),
                "created_at": datetime.datetime.fromtimestamp(client.get("created_at")),
                "updated_at": datetime.datetime.fromtimestamp(client.get("updated_at")),
                "allowed_ips": client.get("allowed_ips"),
                "persistent_keepalive": None,
                "latest_handshake_at": None,
                "transfer_rx": None,
                "transfer_tx": None,
            }
            for client_id, client in config["clients"].items()
        ]

        dump = sh_exec("wg show wg0 dump")
        for line in dump.splitlines()[1:]:
            (
                public_key,
                preshared_key,
                endpoint,
                allowed_ips,
                latest_handshake_at,
                transfer_rx,
                transfer_tx,
                persistent_keepalive,
            ) = line.split("\t")

            client = next(
                (client for client in clients if client.get("public_key") == public_key), None
            )
            if not client:
                return

            client["endpoint"] = endpoint
            client["latest_handshake_at"] = (
                None
                if latest_handshake_at == "0"
                else datetime.datetime.fromtimestamp(int(latest_handshake_at))
            )
            client["persistent_keepalive"] = persistent_keepalive
            client["transfer_rx"] = int(transfer_rx)
            client["transfer_tx"] = int(transfer_tx)

        return clients

    def get_client(self, client_id: str) -> dict:
        config = self.get_config()
        client = config["clients"].get(client_id)
        if not client:
            return

        return client

    def get_full_client(self, client_id: str) -> dict:
        clients = self.get_clients()
        if not clients:
            return
        return next((client for client in clients if client.get("id") == client_id), None)

    def get_client_configuration(self, client_id: str) -> str:
        config = self.get_config()
        client = config["clients"].get(client_id)
        if not client:
            return

        wg_host = sh_exec("hostname -I | awk '{print $1}'")
        return (
            "[Interface]\n"
            f"PrivateKey = {client['private_key']}\n"
            f"Address = {client['address']}/32\n"
            "DNS = 1.1.1.1, 1.0.0.1\n\n"
            "[Peer]\n"
            f"PublicKey = {config['server']['public_key']}\n"
            f"PresharedKey = {client['preshared_key']}\n"
            f"AllowedIPs = 0.0.0.0/0, ::/0\n"
            "PersistentKeepalive = 0\n"
            f"Endpoint = {wg_host}:51820\n"
        )

    def create_client(self, name: str, client_id: str) -> typing.Union[int, dict]:
        if not name:
            return ClientErrorType.NAME_REQUIRED  # Name is required

        if not client_id:
            return ClientErrorType.CLIENT_ID_REQUIRED  # Client ID is required

        if self.get_client(client_id):
            return ClientErrorType.CLIENT_ALREADY_EXIST  # Client already exists

        config = self.get_config()

        private_key = sh_exec("wg genkey")
        public_key = sh_exec(f"echo {private_key} | wg pubkey")
        preshared_key = sh_exec("wg genpsk")

        # Calculate next available IP address
        address = None
        for i in range(2, 255):
            client = next(
                (
                    client
                    for client in config["clients"].values()
                    if client["address"] == self.default_address.replace("x", str(i))
                ),
                None,
            )

            if not client:
                address = self.default_address.replace("x", str(i))
                break

        if not address:
            return ClientErrorType.ADDRESS_LIMIT_REACHED  # No available IP address

        client = {
            "name": name,
            "address": address,
            "private_key": private_key,
            "public_key": public_key,
            "preshared_key": preshared_key,
            "allowed_ips": "0.0.0.0/0, ::/0",
            "created_at": int(datetime.datetime.now().timestamp()),
            "updated_at": int(datetime.datetime.now().timestamp()),
            "enabled": True,
        }

        config["clients"][client_id] = client

        self.save_config(config)

        return client

    def delete_client(self, client_id: str) -> None:
        config = self.get_config()

        if client_id not in config["clients"]:
            return  # Client does not exist

        del config["clients"][client_id]
        self.save_config(config)

    def enable_client(self, client_id: str) -> None:
        self.__update_client(client_id, "enabled", True)

    def disable_client(self, client_id: str) -> None:
        self.__update_client(client_id, "enabled", False)

    def update_client_name(self, client_id: str, name: str) -> None:
        self.__update_client(client_id, "name", name)

    def __update_client(self, client_id, arg1, arg2):
        config = self.get_config()
        client = self.get_client(client_id)
        client[arg1] = arg2
        client["updated_at"] = int(datetime.datetime.now().timestamp())
        config["clients"][client_id] = client
        self.save_config(config)


@Client.on_message(command(["wgi"]) & filters.me & ~filters.forwarded & ~filters.scheduled)
async def wg_install(_: Client, message: Message):
    if os.geteuid() != 0:
        await message.edit("<b>This command must be run as root!</b>")
        return

    prefix = get_prefix()

    if (
        len(message.command) > 1
        and message.command[1] in ["-y", "--yes"]
        or not shutil.which("wg")
    ):
        await message.edit_text("<b>Updating packages...</b>")
        sh_exec("apt update")
        if not shutil.which("wg"):
            await message.edit_text("<b>Installing WireGuard...</b>")
            sh_exec("apt install wireguard -y")

        if not os.path.exists("/etc/wireguard"):
            os.mkdir("/etc/wireguard")

        with open("/etc/sysctl.conf", "r") as f:
            lines = f.readlines()
        with open("/etc/sysctl.conf", "w") as f:
            for line in lines:
                if line.startswith("#net.ipv4.ip_forward=1"):
                    f.write("net.ipv4.ip_forward=1")
                else:
                    f.write(line)

        sh_exec("systemctl enable wg-quick@wg0.service")
        sh_exec("systemctl start wg-quick@wg0.service")

        await message.edit_text("<b>✨ WireGuard installed!</b>")
    else:
        await message.edit_text(
            "<b>Are you sure you want to install WireGuard?</b>\n"
            "<b>This will delete all your current VPN configurations!</b>\n"
            f"<b>Use</b> <code>{prefix}{message.command[0]} -y</code> <b>to confirm</b>"
        )


@Client.on_message(command(["wgr"]) & filters.me & ~filters.forwarded & ~filters.scheduled)
@check_wireguard_installed
async def wg_uninstall(_: Client, message: Message):
    if len(message.command) > 1 and message.command[1] in ["-y", "--yes"]:
        await message.edit_text("Uninstalling WireGuard...")
        sh_exec("systemctl stop wg-quick@wg0.service; systemctl disable wg-quick@wg0.service")
        sh_exec("rm -rf /etc/wireguard")
        sh_exec("apt remove wireguard -y")
        await message.edit_text("✨ WireGuard successfully uninstalled")
    else:
        await message.edit_text(
            "<b>Are you sure you want to uninstall WireGuard?</b>\n"
            "<b>This will delete all your current VPN configurations!</b>\n"
            f"<b>Use</b> <code>{get_prefix()}{message.command[0]} -y</code> <b>to confirm</b>"
        )


@Client.on_message(command(["wgau"]) & filters.me & ~filters.forwarded & ~filters.scheduled)
@check_wireguard_installed
async def wg_add(client: Client, message: Message):
    args = get_args_raw(message)
    wg = WireGuard()

    if len(args.split()) == 2 and args.split()[0].lstrip("-").isdigit():
        user_id = args.split()[0].lstrip("-")
        name = args.split(maxsplit=1)[1]
    else:
        user_id = message.chat.id
        name = get_full_name(message.chat)

    wg_client = wg.create_client(name, str(user_id))
    if wg_client == ClientErrorType.CLIENT_ALREADY_EXIST:  # Client already exists
        return await message.edit_text("<b>Client already exists</b>")
    elif wg_client == ClientErrorType.ADDRESS_LIMIT_REACHED:  # Client limit reached
        return await message.edit_text("<b>Client limit reached</b>")

    client_config = wg.get_client_configuration(str(user_id))
    client_config_binary = BytesIO(client_config.encode("utf-8"))

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=64,
        border=4,
    )
    qr.add_data(client_config)
    qr.make(fit=True)

    client_qr_binary = BytesIO()

    qr.make_image(fill_color="black", back_color="white").save(client_qr_binary)

    await client.send_photo(
        message.chat.id,
        client_qr_binary,
        caption=text_template.format(wg_client["name"]),
    )
    await client.send_document(message.chat.id, client_config_binary, file_name="vpn.conf")


@Client.on_message(command(["wgru"]) & filters.me & ~filters.forwarded & ~filters.scheduled)
@check_wireguard_installed
async def wg_remove(_: Client, message: Message):
    wg = WireGuard()

    args = get_args_raw(message)
    if args and args.split()[0].lstrip("-").isdigit():
        user_id = args.split()[0]
    else:
        user_id = message.chat.id

    if not wg.get_client(str(user_id)):
        return await message.edit_text("<b>User does not exist</b>")

    wg.delete_client(str(user_id))
    await message.edit_text(f"<b>User ID: {user_id} removed from WireGuard</b>")


@Client.on_message(command(["wgc"]) & filters.me & ~filters.forwarded & ~filters.scheduled)
@check_wireguard_installed
async def wg_show(client: Client, message: Message):
    wg = WireGuard()

    user_id = message.chat.id
    args = get_args_raw(message)

    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    if args and args.split(maxsplit=1)[0].lstrip("-").isdigit():
        user_id = args

    wg_client = wg.get_client(str(user_id))
    if not wg_client:
        return await message.edit_text("<b>User does not exist</b>")

    client_config = wg.get_client_configuration(str(user_id))
    client_config_binary = BytesIO(client_config.encode("utf-8"))

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=64,
        border=4,
    )
    qr.add_data(client_config)
    qr.make(fit=True)

    client_qr_binary = BytesIO()

    qr.make_image(fill_color="black", back_color="white").save(client_qr_binary)

    await client.send_photo(
        message.chat.id,
        client_qr_binary,
        caption=text_template.format(wg_client["name"]),
    )
    await client.send_document(message.chat.id, client_config_binary, file_name="vpn.conf")


@Client.on_message(command(["wge"]) & filters.me & ~filters.forwarded & ~filters.scheduled)
@check_wireguard_installed
async def wg_enable(_: Client, message: Message):
    wg = WireGuard()

    args = get_args_raw(message)

    if not args:
        return await message.edit_text("<b>Invalid arguments</b>")

    if message.reply_to_message:
        if len(args.split()) != 1:
            return await message.edit_text("<b>Invalid arguments</b>")
        if args.split()[0] in ("true", "1", "on"):
            wg.enable_client(str(message.reply_to_message.from_user.id))
            return await message.edit_text(
                f"<b>WireGuard: Enabled for {message.reply_to_message.from_user.id}</b>"
            )
        elif args.split()[0] in ("false", "0", "off"):
            wg.disable_client(str(message.reply_to_message.from_user.id))
            return await message.edit_text(
                f"<b>WireGuard: Disabled for {message.reply_to_message.from_user.id}</b>"
            )
        else:
            return await message.edit_text("<b>Invalid arguments</b>")
    elif len(args.split()) == 1:
        if args.split()[0] in ("true", "1", "on"):
            wg.enable_client(str(message.chat.id))
            return await message.edit_text(f"<b>WireGuard: Enabled for {message.chat.id}</b>")
        elif args.split()[0] in ("false", "0", "off"):
            wg.disable_client(str(message.chat.id))
            return await message.edit_text(f"<b>WireGuard: Disabled for {message.chat.id}</b>")
        else:
            return await message.edit_text("<b>Invalid arguments</b>")
    elif len(args.split()) == 2:
        if args.split()[1] in ("true", "1", "on") and args.split()[0].lstrip("-").isdigit():
            wg.enable_client(args.split()[0])
            return await message.edit_text(f"<b>WireGuard: Enabled for {args.split()[0]}</b>")
        elif args.split()[1] in ("false", "0", "off") and args.split()[0].lstrip("-").isdigit():
            wg.disable_client(args.split()[0])
            return await message.edit_text(f"<b>WireGuard: Disabled for {args.split()[0]}</b>")
        else:
            return await message.edit_text("<b>Invalid arguments</b>")


@Client.on_message(command(["wgn"]) & filters.me & ~filters.forwarded & ~filters.scheduled)
@check_wireguard_installed
async def wg_update_user(_: Client, message: Message):
    args = get_args_raw(message)
    wg = WireGuard()

    if not args:
        user_id = str(message.chat.id)
    elif args.lstrip("-").isdigit():
        user_id = args.split()[0]
        user_name = message.chat.first_name
    elif len(args.split()) >= 2 and args.split()[0].lstrip("-").isdigit():
        user_id = args.split()[0]
        user_name = args.split(maxsplit=1)[1]
    else:
        return await message.edit_text("<b>Invalid arguments</b>")

    if not wg.get_client(str(user_id)):
        return await message.edit_text("<b>User does not exist</b>")

    wg.update_client_name(str(user_id), str(user_name))

    await message.edit_text(f"<b>WireGuard: Updated user {user_id} with name {user_name}</b>")


@Client.on_message(command(["wgl"]) & filters.me & ~filters.forwarded & ~filters.scheduled)
@check_wireguard_installed
async def wg_list(_: Client, message: Message):
    args = get_args_raw(message)
    wg = WireGuard()

    clients = wg.get_clients()
    if not clients:
        return await message.edit_text("<b>No users found</b>")

    if not args or args.lstrip("-").isdigit():
        user_id = args if args.lstrip("-").isdigit() else str(message.chat.id)
        client = wg.get_client(user_id)
        if not client:
            return await message.edit_text("<b>User does not exist</b>")

        full_client_old = wg.get_full_client(user_id)
        await asyncio.sleep(1)
        full_client_new = wg.get_full_client(user_id)

        latest_handshake_at = full_client_new.get("latest_handshake_at")

        if latest_handshake_at:
            rx, tx = calculate_speed(
                full_client_old.get("transfer_rx"),
                full_client_new.get("transfer_rx"),
                full_client_old.get("transfer_tx"),
                full_client_new.get("transfer_tx"),
                1,
            )

        result = f"<b>Information about user: {full_client_new.get('name')}</b> (<code>{full_client_new.get('id')}</code>)\n"
        result += (
            f"<b>Enabled:</b> {'🟢' if full_client_new.get('enabled') else '🔴'}\n"
            f"<b>Address:</b> <code>{full_client_new.get('address')}</code>\n"
            f"<b>Endpoint:</b> <code>{full_client_new.get('endpoint').split(':')[0]}</code>\n"
            f"<b>Created at:</b> {full_client_new.get('created_at')} "
            f"({arrow.get(full_client_new.get('created_at').timestamp()).humanize()})\n"
            f"<b>Updated at:</b> {full_client_new.get('updated_at')} "
            f"({arrow.get(full_client_new.get('updated_at').timestamp()).humanize()})\n"
        )

        if latest_handshake_at:
            delta = datetime.datetime.now() - latest_handshake_at
            result += (
                f"<b>Speed:</b> ⬇️{rx} ⬆️{tx}\n"
                if delta.total_seconds() < 300
                else f"<b>Last handshake:</b> {latest_handshake_at} ({arrow.get(latest_handshake_at.timestamp()).humanize()})\n"
            )
    elif args == "all":
        old_clients = wg.get_clients()
        await asyncio.sleep(1)
        new_clients = wg.get_clients()

        result = "🗓️ <b>Information about all users:</b>\n"
        for count, client in enumerate(new_clients, start=1):
            latest_handshake_at = client.get("latest_handshake_at")
            if latest_handshake_at:
                rx, tx = calculate_speed(
                    old_clients[count - 1].get("transfer_rx"),
                    client.get("transfer_rx"),
                    old_clients[count - 1].get("transfer_tx"),
                    client.get("transfer_tx"),
                    1,
                )

            result += f"{count}. {'🟢' if client.get('enabled') else '🔴'} <code>{client.get('id')}</code> "
            if latest_handshake_at:
                delta = datetime.datetime.now() - latest_handshake_at
                result += (
                    f"- ⬇️{rx} ⬆️{tx}\n"
                    if delta.total_seconds() < 300
                    else f"- 🤝 {arrow.get(latest_handshake_at.timestamp()).humanize()}\n"
                )
            else:
                result += "\n"
    else:
        return await message.edit_text("<b>Invalid command usage</b>")

    await message.edit_text(result)


modules_help["wireguard"] = {
    "wgi": "Install WireGuard",
    "wgr": "Remove WireGuard from your system",
    "wgau [user_id|reply]": "Add user to WireGuard and send config",
    "wgru [user_id|reply]": "Remove user from WireGuard",
    "wgn [user_id] [name]": "Update WireGuard user name",
    "wge [user_id|reply] [on|off]": "Enable/Disable WireGuard for user",
    "wgl [user_id|all]": "Show info about user",
    "wgc [user_id|reply]": "Send WireGuard config",
}
