# urandom - A maubot plugin that generates random strings with /dev/urandom.
# Copyright (C) 2019 Tulir Asokan
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from typing import Dict, Union, Tuple, List
from base64 import b64encode, b16encode, b32encode, b85encode
from os import urandom
import random

from base65536 import encode as b65536encode

from mautrix.types import (EventType, RoomTopicStateEventContent, TextMessageEventContent,
                           MessageType)

from maubot import Plugin, MessageEvent
from maubot.handlers import command

Args = Dict[str, Union[bool, str]]
rand = random.SystemRandom()


def parse_args(args: str) -> Tuple[str, Args]:
    args = (arg.split("=", 1)
            for arg in args.split(" ")
            if arg)
    return "", {arg[0].lower(): arg[1] if len(arg) == 2 else True
                for arg in args}


def parse_urange(val: str) -> Tuple[int, int]:
    if "-" not in val:
        if val.startswith("U+"):
            char = int(val[2:], 16)
        else:
            char = _parse_urange_part(val)
        return char, char
    if val.upper().startswith("U+"):
        start, end = val[2:].split("-")
        return int(start, 16), int(end, 16)
    start, end = val.split("-")
    return _parse_urange_part(start), _parse_urange_part(end)


def _parse_urange_part(val: str) -> int:
    if val.startswith("0x"):
        return int(val, 16)
    elif val.startswith("0b"):
        return int(val, 2)
    elif val.startswith("\\u"):
        return ord(val.encode("utf-8").decode("unicode-escape"))
    try:
        return ord(val)
    except TypeError:
        return int(val)


class RandomBot(Plugin):
    @command.new("urandom")
    @command.argument("args", required=False, pass_raw=True, parser=parse_args)
    async def urandom(self, evt: MessageEvent, args: Args) -> None:
        try:
            length = int(args["len"])
        except (KeyError, ValueError):
            length = 64
        if length > 512:
            await evt.reply("Too high length")
            return
        elif length < 0:
            await evt.reply("Invalid length")
            return

        if "alphabet" in args:
            randomness = "".join(rand.choices(args["alphabet"], k=length))
        elif "urange" in args:
            ranges: List[Tuple[int, int]] = []
            weights: List[int] = []
            try:
                for urange in args["urange"].split(","):
                    start, end = parse_urange(urange.strip())
                    ranges.append((start, end + 1))
                    weights.append(end - start + 1)
            except (KeyError, ValueError):
                await evt.reply("Invalid unicode range")
                self.log.exception("Invalid unicode range")
                return
            randomness = "".join(chr(rand.randrange(start, end))
                                 for start, end
                                 in rand.choices(ranges, weights, k=length))
        else:
            randomness = urandom(length)

            base = args.get("base", "64")
            if base == "raw":
                randomness = str(randomness)
            elif base == "16" or base == "hex":
                randomness = b16encode(randomness).decode("utf-8")
            elif base == "32":
                randomness = b32encode(randomness).decode("utf-8").rstrip("=")
            elif base == "64":
                randomness = b64encode(randomness).decode("utf-8").rstrip("=")
            elif base == "85":
                randomness = b85encode(randomness).decode("utf-8")
            elif base == "65536":
                randomness = b65536encode(randomness)
            else:
                await evt.reply("Unknown base")

        if "topic" in args:
            await self.client.send_state_event(evt.room_id, EventType.ROOM_TOPIC,
                                               RoomTopicStateEventContent(topic=randomness))
        elif "noreply" in args or "noreplay" in args:
            await evt.respond(TextMessageEventContent(body=randomness, msgtype=MessageType.NOTICE))
        else:
            await evt.reply(TextMessageEventContent(body=randomness, msgtype=MessageType.NOTICE))
