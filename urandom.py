from os import urandom
from base64 import b64encode

from maubot import Plugin, MessageEvent
from maubot.handlers import command


class RandomBot(Plugin):
    @command.new("urandom")
    async def urandom(self, evt: MessageEvent) -> None:
        await evt.reply(b64encode(urandom(64)).decode("utf-8"))
