from os import listdir
from re import compile
from ..structures import Bloxlink # pylint: disable=import-error, no-name-in-module
from ..exceptions import RobloxAPIError, RobloxDown, RobloxNotFound, CancelCommand # pylint: disable=import-error, no-name-in-module
from config import PREFIX # pylint: disable=import-error, no-name-in-module
from ..constants import RELEASE, HTTP_RETRY_LIMIT # pylint: disable=import-error, no-name-in-module
from ..secrets import PROXY_URL # pylint: disable=import-error, no-name-in-module
from discord.errors import NotFound, Forbidden
from discord import Embed
from aiohttp.client_exceptions import ClientOSError, ServerDisconnectedError
from requests.utils import requote_uri
from async_timeout import timeout as a_timeout
import asyncio
import aiohttp

is_patron = Bloxlink.get_module("patreon", attrs="is_patron")
get_guild_value = Bloxlink.get_module("cache", attrs=["get_guild_value"])

@Bloxlink.module
class Utils(Bloxlink.Module):
    def __init__(self):
        self.option_regex = compile("(.+):(.+)")
        self.timeout = aiohttp.ClientTimeout(total=20)


    @staticmethod
    def get_files(directory):
        return [name for name in listdir(directory) if name[:1] != "." and name[:2] != "__" and name != "_DS_Store"]


    @staticmethod
    def coro_async(corofn, *args):
        # https://stackoverflow.com/questions/46074841/why-coroutines-cannot-be-used-with-run-in-executor
        loop = asyncio.new_event_loop()

        try:
            coro = corofn(*args)
            asyncio.set_event_loop(loop)

            return loop.run_until_complete(coro)

        finally:
            loop.close()


    async def post_event(self, guild, guild_data, event_name, text, color=None):
        if guild_data:
            log_channels = guild_data.get("logChannels")
        else:
            log_channels = await get_guild_value(guild, "logChannels")

        log_channels = log_channels or {}
        log_channel  = log_channels.get(event_name) or log_channels.get("all")

        if log_channel:
            text_channel = guild.get_channel(int(log_channel))

            if text_channel:
                embed = Embed(title=f"{event_name.title()} Event", description=text)
                embed.colour = color

                try:
                    await text_channel.send(embed=embed)
                except (Forbidden, NotFound):
                    pass

    async def fetch(self, url, method="GET", params=None, headers=None, body=None, text=True, json=True, bytes=False, raise_on_failure=True, retry=HTTP_RETRY_LIMIT, timeout=20):
        params  = params or {}
        headers = headers or {}
        new_json = {}
        proxied = False

        if PROXY_URL and "roblox.com" in url:
            old_url = url
            new_json["url"] = url
            new_json["data"] = body or {}
            url = PROXY_URL
            proxied = True
            method = "POST"

            if RELEASE == "LOCAL":
                print(f"{old_url} -> {url}")
        else:
            if RELEASE == "LOCAL":
                print(f"Making request to {url} with method {method}")

            new_json = body
            old_url = url

        url = requote_uri(url)

        for k, v in params.items():
            if isinstance(v, bool):
                params[k] = "true" if v else "false"

        try:
            async with a_timeout(timeout): # I noticed sometimes the aiohttp timeout parameter doesn't work. This is added as a backup.
                async with self.session.request(method, url, json=new_json, params=params, headers=headers, timeout=timeout) as response:
                    if proxied:
                        response_json = await response.json()
                        response_body = response_json["req"]["body"]
                        response_status = response_json["req"]["status"]
                        response.status = response_status

                        if raise_on_failure:
                            if response_status == 503:
                                raise RobloxDown
                            elif response_status == 404:
                                raise RobloxNotFound
                            elif response_status >= 400:
                                raise RobloxAPIError

                        if json:
                            if isinstance(response_body, dict):
                                return response_body, response
                            else:
                                return {}, response

                        return response_body, response

                    if text:
                        text = await response.text()

                        return text, response

                    elif json:
                        try:
                            json = await response.json()
                        except aiohttp.client_exceptions.ContentTypeError:
                            print(await response.text(), flush=True)

                            raise

                        return json, response

                    return response

        except asyncio.TimeoutError:
            print(f"URL {old_url} timed out", flush=True)
            raise RobloxDown


    async def get_prefix(self, guild=None, trello_board=None):
        if RELEASE == "PRO" and guild:
            prefix = await get_guild_value(guild, "proPrefix")

            if prefix:
                return prefix, None

        if trello_board:
            try:
                List = await trello_board.get_list(lambda L: L.name == "Bloxlink Settings")

                if List:
                    card = await List.get_card(lambda c: c.name[:6] == "prefix")

                    if card:
                        if card.name == "prefix":
                            if card.desc:
                                return card.desc.strip(), card

                        else:
                            match = self.option_regex.search(card.name)

                            if match:
                                return match.group(2), card

            except asyncio.TimeoutError:
                pass

        prefix = guild and await get_guild_value(guild, ["prefix", PREFIX])

        return prefix or PREFIX, None
