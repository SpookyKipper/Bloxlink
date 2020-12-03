from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error
from resources.exceptions import (Error, UserNotVerified, Message, BloxlinkBypass, PermissionError, RobloxAPIError, # pylint: disable=import-error
                                  RobloxNotFound, CancelCommand, Blacklisted, RobloxDown)
from config import VERIFYALL_MAX_SCAN # pylint: disable=no-name-in-module
from resources.constants import RELEASE # pylint: disable=import-error
from discord.errors import Forbidden, NotFound
import heapq
import asyncio
import math

loop = asyncio.get_event_loop()

guild_obligations = Bloxlink.get_module("roblox", attrs=["guild_obligations"])


class Comparable:
    def __init__(self, guild_id):
        self.id = guild_id

    def __lt__(self, other):
        return self.id < other.id


@Bloxlink.command
class VerifyAllCommand(Bloxlink.Module):
    """force update everyone in the server"""

    def __init__(self):
        self.permissions = Bloxlink.Permissions().build("BLOXLINK_UPDATER")
        self.arguments = [
            {
                "prompt": "Would you like members' **roles** to be updated, their **nickname**, or **both**?\n"
                          "Please specify one of: ``roles``, ``nickname``, or ``both``.",
                "type": "choice",
                "name": "update_what",
                "choices": ("roles", "nickname", "both")
            }
        ]
        self.category = "Premium"

        self.queue = []
        self.queue_loop_running = False
        self.REDIS_COOLDOWN_KEY = "guild_scan:{id}"

    async def process_guild(self, guild, author=None, roles=True, nickname=True, guild_data=None, trello_board=None, response=None):
        if not guild.chunked:
            try:
                await guild.chunk()
            except:
                pass

        if response:
            if author:
                await response.send(f"{author.mention}, your server is now being scanned.")
            else:
                await response.send(f"Your server is now being scanned.")

        redis_cooldown_key = self.REDIS_COOLDOWN_KEY.format(release=RELEASE, id=guild.id)
        await self.redis.set(redis_cooldown_key, 2, ex=86400)

        failed_attempts = 0

        try:
            for member in guild.members:
                if failed_attempts == 5:
                    await response.error("Roblox appears to be down, so this scan has been cancelled. retries=5")
                    break

                if not member.bot:
                    try:
                        added, removed, nickname, errors, roblox_user = await guild_obligations(
                            member,
                            guild             = guild,
                            guild_data        = guild_data,
                            trello_board      = trello_board,
                            roles             = roles,
                            nickname          = nickname,
                            dm                = False,
                            exceptions        = ("BloxlinkBypass", "UserNotVerified", "PermissionError", "RobloxNotFound",
                                                "Forbidden", "RobloxAPIError", "CancelCommand", "Blacklisted", "NotFound", "Error", "RobloxDown")
                        )

                    except (BloxlinkBypass, UserNotVerified, PermissionError, RobloxNotFound, Forbidden, RobloxAPIError, CancelCommand, Blacklisted):
                        pass

                    except NotFound:
                        await response.error("Please do not delete roles/channels while a scan is going on... This scan is now cancelled.")
                        break

                    except Error as e:
                        await response.error(f"Encountered an error: ``{e}``. Scan cancelled.")
                        break

                    except RobloxDown:
                        failed_attempts += 1

            await response.success("This server's scan has finished.")

        finally:
            len_members = len(guild.members)

            cooldown_1 = math.ceil((len_members / 1000) * 120)
            cooldown_2 = 120

            cooldown = max(cooldown_1, cooldown_2)

            if self.redis:
                await self.redis.set(redis_cooldown_key, 3, ex=cooldown * 60)


    async def start_queue(self):
        if not self.queue_loop_running:
            self.queue_loop_running = True
        else:
            return

        while self.queue:
            tasks = []

            for _ in range(VERIFYALL_MAX_SCAN):
                if self.queue:
                    data = heapq.heappop(self.queue)
                    guild = data[2]
                    author = data[3]
                    response = data[4]
                    trello_board = data[5]
                    update_roles = data[6]
                    update_nickname = data[7]
                    guild_data = data[8]

                    if guild:
                        tasks.append(self.process_guild(guild, author=author, roles=update_roles, nickname=update_nickname, guild_data=guild_data, trello_board=trello_board, response=response))

            await asyncio.wait(tasks)

        self.queue_loop_running = False

    async def __main__(self, CommandArgs):
        response = CommandArgs.response
        update_what = CommandArgs.parsed_args["update_what"]

        guild = CommandArgs.message.guild
        guild_data = CommandArgs.guild_data

        author = CommandArgs.message.author

        trello_board = CommandArgs.trello_board

        if self.redis:
            redis_cooldown_key = self.REDIS_COOLDOWN_KEY.format(release=RELEASE, id=guild.id)
            on_cooldown = await self.redis.get(redis_cooldown_key)

            if on_cooldown:
                cooldown_time = math.ceil(await self.redis.ttl(redis_cooldown_key)/60)

                if not cooldown_time or cooldown_time == -1:
                    await self.redis.delete(redis_cooldown_key)
                    on_cooldown = None

                if on_cooldown:
                    if on_cooldown == 1:
                        raise Message(f"This server is still queued.")
                    elif on_cooldown == 2:
                        raise Message("This server's scan is currently running.")
                    elif on_cooldown == 3:
                        cooldown_time = math.ceil(await self.redis.ttl(redis_cooldown_key)/60)

                        raise Message(f"This server has an ongoing cooldown! You must wait **{cooldown_time}** more minutes.")

            await self.redis.set(redis_cooldown_key, 1, ex=86400)

            update_roles    = update_what in ("roles", "both")
            update_nickname = update_what in ("nickname", "both")

            t = (len(guild.members), Comparable(guild.id), guild, author, response, trello_board, update_roles, update_nickname, guild_data)

            heapq.heappush(self.queue, t)

            if not self.queue_loop_running:
                loop.create_task(self.start_queue())
                await response.send("Your server will be scanned momentarily.")
            else:
                await response.send("Your server is now queued for full-member updating.")
