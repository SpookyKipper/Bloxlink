from discord.errors import Forbidden, NotFound
from resources.exceptions import CancelCommand, Error
from resources.structures import Bloxlink
from asyncio import TimeoutError

class Paginate:
    """Smart paginator for Discord embeds"""

    def __init__(self, message, channel, embed, response=None, field_limit=25, pages=None):
        self.message = message
        self.author = message.author
        self.embed = embed
        self.response = response
        self.field_limit = field_limit
        self.channel = channel
        self._pages = pages

        self.sent_message = None

    @staticmethod
    def get_pages(embed, fields, field_limit=25):
        pages = []
        i = 1

        len_fields = len(fields)

        while True:
            remaining = 5500
            field = fields[i-1]
            current_page = []

            while remaining > 0 and i < len_fields + 1:
                if field_limit and len(current_page) >= field_limit:
                    remaining = 0

                # get first 1024 characters, append, remove from old field
                # if the old field is gone, increment i
                # if it's 6000, append to pages and clear current_page, and reset remaining

                # check to see if there's room on the current page
                len_field_name = len(field.name)
                len_description = len(embed.description)

                if remaining > (len_field_name + len_description + 1):
                    # get first 1024 characters with respect to remaining
                    chars = field.value[0:min(1000, remaining - len_field_name - len_description)]
                    len_chars = len(chars)
                    current_page.append({"name": field.name, "value": chars})
                    remaining -= len_chars - len_field_name - len_description
                    field.value = field.value[len_chars:] # remove characters

                    if not field.value:
                        # no more field, so get next one. there's still room for more, though
                        if i < len_fields:
                            i += 1
                            field = fields[i-1]
                        else:
                            break
                else:
                    # page is done
                    pages.append(current_page)
                    if not field.value:
                        i += 1

                    break

            if len_fields <= i:
                pages.append(current_page)
                break


        return pages

    async def turn_page(self, i, pages):
        self.embed.clear_fields()

        for field in pages[i]:
            self.embed.add_field(name=field["name"], value=field["value"], inline=False)

        if self.sent_message:
            try:
                await self.sent_message.edit(embed=self.embed)
            except (NotFound, Forbidden):
                raise CancelCommand
        else:
            self.sent_message = await self.response.send(embed=self.embed, channel_override=self.channel, ignore_http_check=True)

            if not self.sent_message:
                raise CancelCommand

    async def __call__(self):
        pages = self._pages or Paginate.get_pages(self.embed, self.embed.fields, self.field_limit)
        len_pages = len(pages)

        i = 0

        await self.turn_page(i, pages)

        if len_pages > 1:
            reactions = {'\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}': lambda: 0,
                        '\N{BLACK LEFT-POINTING TRIANGLE}': lambda: i - 1 >= 0 and i - 1,
                        '\N{BLACK RIGHT-POINTING TRIANGLE}': lambda: i + 1 < len_pages and i + 1,
                        '\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}': lambda: len_pages - 1,
                        }

            for reaction in reactions:
                try:
                    await self.sent_message.add_reaction(reaction)
                except Forbidden:
                    raise Error("I'm missing the ``Add Reactions`` permission.")

            while True:
                try:
                    reaction, user = await Bloxlink.wait_for("reaction_add", check=lambda r, u: str(r) in reactions and u == self.author and \
                                                                                                r.message.id == self.sent_message.id, timeout=120)
                except TimeoutError:
                    try:
                        await self.sent_message.clear_reactions()
                    except Forbidden:
                        raise Error("I'm missing the ``Manage Messages`` permission.")
                    except NotFound:
                        raise CancelCommand

                emoji = str(reaction)
                fn = reactions[emoji]
                x = fn()

                if x is not False:
                    i = x
                    await self.turn_page(i, pages)

                try:
                    await self.sent_message.remove_reaction(emoji, user)
                except Forbidden:
                    raise Error("I'm missing the ``Manage Messages`` permission.")
                except NotFound:
                    raise CancelCommand


        return self.sent_message