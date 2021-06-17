from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error
from resources.exceptions import UserNotVerified, Message, Error # pylint: disable=import-error

get_user, get_binds = Bloxlink.get_module("roblox", attrs=["get_user", "get_binds"])


class GetinfoCommand(Bloxlink.Module):
    """retrieve the Roblox information for a member"""

    def __init__(self):
        self.aliases = ["whois", "get-info"]
        self.arguments = [
            {
                "prompt": "Please specify the user.",
                "type": "user",
                "name": "user",
                "optional": True
            }
        ]

        self.examples = [
            "justin",
            "@justin",
            "84117866944663552",
            "@justin --avatar",
            "@justin --avatar --groups"
        ]
        self.cooldown      = 5
        self.dm_allowed    = True
        self.slash_enabled = True
        self.slash_ack     = True

    @Bloxlink.flags
    async def __main__(self, CommandArgs):
        target   = CommandArgs.parsed_args["user"] or CommandArgs.author
        flags    = CommandArgs.flags
        guild    = CommandArgs.guild
        response = CommandArgs.response
        prefix   = CommandArgs.prefix

        if target.bot:
            raise Message("Bots can't have Roblox accounts!", type="info")

        valid_flags = ["username", "id", "avatar", "premium", "badges", "groups", "description", "age", "banned", "devforum"]

        if not all(f in valid_flags for f in flags.keys()):
            raise Error(f"Invalid flag! Valid flags are: `{', '.join(valid_flags)}`")

        #async with response.loading():
        if guild:
            role_binds, group_ids, _ = await get_binds(guild_data=CommandArgs.guild_data, trello_board=CommandArgs.trello_board)
        else:
            role_binds, group_ids = {}, {}

        try:
            account, accounts = await get_user(*flags.keys(), author=target, guild=guild, group_ids=(group_ids, role_binds), send_embed=True, response=response, everything=not bool(flags), basic_details=not bool(flags))
        except UserNotVerified:
            raise Error(f"**{target}** is not linked to Bloxlink.")
        else:
            if not account:
                raise Message(f"This Discord user has no primary account set! They may use `{prefix}switchuser` to set one.", type="info")

