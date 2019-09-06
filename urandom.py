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
import unicodedata
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


HELP = """**Usage:** `!urandom [args...]`

Output format args:

* `base=<base>` - The base to encode the random data in. Options: `raw`, `16`, `32`, `64`, `65536`.
   The default is `base=64`.
* `alphabet=<str>` - The set of characters to create a random string from.
   Available options: `space=<chr>`, `shuffle`.
* `urange=<range...>` - Unicode character range(s) to create a random string from.

Other args:

* `topic` - Set the result in the room topic instead of responding with a message.
* `reply` - Reply to the command message instead of just sending a plain message.
* `len=<int>` - The length of the string to generate.
* `help[=<arg>]` - View this help page or the sub-help for a specific arg.
"""

HELP_BASE = """**Usage:** `!urandom base=<base> [len=<int>]`

This is the default format if `alphabet` or `urange` isn't specified. The default is base64.
In this mode, `len` specifies the number of bytes to generate, not the length of the output string.
"""

HELP_ALPHABET = """**Usage:** `!urandom alphabet=<str> [space=<char>] [shuffle] [len=<int>]`

This format generates a random string using the letters in the given alphabet.

If `shuffle` is specified, the given alphabet is shuffled instead. `len` is ignored when `shuffle`
is used.

As `<str>` can't contain spaces, you can use `space=<char>` to replace all instances of `<char>`
with a space in the alphabet before generating the string.
"""

HELP_URANGE = """**Usage:** `!urandom urange=<range...> [len=<int>]`

This format generates a random string using the given unicode codepoint ranges.

`<range...>` is a comma-separated list. Each `range` consists of one or two `part`s. If there are
two `part`s, they're separated by a dash (`-`). Each `part` can be: a hex value prefixed by `0x`, a
binary value prefixed by `0b`, a python unicode escape (prefixed by `\\u`), a single character or an
unprefixed base-10 value. Additionally, `part` may be a hex value prefixed by `U+`, but in that
case, the second `part` is not prefixed (e.g. `U+0061-007A`)
"""

HELP_TOPIC = """**Usage:** `!urandom topic [args...]`

This flag makes urandom set the topic to the output string instead of sending a new message with the
output string. It can be used in combination with any output format.
"""

HELP_LEN = """**Usage:** `!urandom len=<int> [args...]`

This flag sets the length of the randomized data. For the `base` output format, this specifies the
length of the random bytes. For other formats, this specifies the length of the output string.
"""

HELP_HELP = """**Usage:** `!urandom help[=<arg>]`

View help for a specific argument. Currently, there are help pages for `base`, `alphabet`, `urange`,
`topic`, `len` and `help`.

Help/command syntax:

* `raw text`.
* `<required argument>`.
* `[optional block/argument]`. If an optional block contains a required argument, the rest of the
   optional block is treated as raw text instead of an argument.
* `argument...` - A list of items.
"""

HELP_UNKNOWN = "See `!urandom help=help` for help on how to use the help command."

helps = {
    True: HELP,
    "base": HELP_BASE,
    "alphabet": HELP_ALPHABET,
    "urange": HELP_URANGE,
    "topic": HELP_TOPIC,
    "len": HELP_LEN,
    "help": HELP_HELP,
}

DEFAULT_LENGTH = 64
DEFAULT_BASE = "64"


class RandomBot(Plugin):
    @command.new("urandom")
    @command.argument("args", required=False, pass_raw=True, parser=parse_args)
    async def urandom(self, evt: MessageEvent, args: Args) -> None:
        evt.disable_reply = "reply" not in args and "replay" not in args
        if "help" in args:
            await evt.reply(helps.get(args["help"], HELP_UNKNOWN))
            return
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
            alphabet = args["alphabet"]
            if "space" in args:
                alphabet = alphabet.replace(args["space"], " ")
            if "permutation" in args or "shuffle" in args:
                data = list(alphabet)
                rand.shuffle(data)
                randomness = "".join(data)
            else:
                randomness = "".join(rand.choices(alphabet, k=length or DEFAULT_LENGTH))
        elif "urange" in args:
            ranges: List[Tuple[int, int]] = []
            weights: List[int] = []
            try:
                lim = range(0x110000)
                for urange in args["urange"].split(","):
                    start, end = parse_urange(urange.strip())
                    if start == 0 or end == 0:
                        await evt.reply(
                            'Exception in thread "main" java.lang.NullPointerException  \n'
                            '    at Tester.main(Urandom.java:194)')
                        return
                    if start not in lim:
                        raise ValueError("range start not in range(0x110000)")
                    elif end not in lim:
                        raise ValueError("range end not in range(0x110000)")
                    ranges.append((start, end + 1))
                    weights.append(end - start + 1)
            except (KeyError, ValueError):
                await evt.reply("Invalid unicode range")
                self.log.exception("Invalid unicode range")
                return
            randomness = "".join(chr(rand.randrange(start, end))
                                 for start, end
                                 in rand.choices(ranges, weights, k=length or DEFAULT_LENGTH))
        else:
            randomness = urandom(length or DEFAULT_LENGTH)

            base = args.get("base", DEFAULT_BASE)
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
        if [c for c in randomness if unicodedata.category(c) == "Cc"]:
            await evt.reply("Output contains non-printable characters")

        if "topic" in args:
            await self.client.send_state_event(evt.room_id, EventType.ROOM_TOPIC,
                                               RoomTopicStateEventContent(topic=randomness))
        else:
            await evt.reply(TextMessageEventContent(body=randomness, msgtype=MessageType.NOTICE))
