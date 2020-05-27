from discord.ext import commands
import asyncpg
import asyncio
import config


class Wumpus(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(
            command_prefix="w"
        )
        self.db = kwargs.pop("db")
        
        self.db_start_insert = self.db.prepare("""
            insert into words (id, after, count) values
            ($1, $2, 1)
            on conflict do update 
            set count=count + 1;
        """)
        self.db_word_insert = self.db.prepare("""
            insert into words (id, before, after, count) values
            ($1, $2, $3, 1)
            on conflict do update 
            set count=count + 1;
        """)
        self.db_end_insert = self.db.prepare("""
            insert into words (id, before, count) values
            ($1, $2, 1)
            on conflict do update 
            set count=count + 1;
        """)
        self.db_progress = self.db.prepare("""
            insert into progress (channel_id, message_id) values
            ($1,$2)
            on conflict do update
            set message_id=$2;
        """)
        self.remove_command("help")

async def run(token):
    db = await asyncpg.create_pool(**config.dbc)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS words(
            id varchar,
            before varchar,
            after varchar,
            count integer,
            primary key (id, before, after)
        );
    """)

    await db.execute("""
        create table if not exists progress(
            channel_id bigint not null primary key,
            message_id bigint not null
        );
    """)
    wumpus = Wumpus(db=db)
    try:
        await wumpus.start(token)
    except KeyboardInterrupt:
        await db.close()
        await wumpus.logout()

def getuserid(message, ctx):
    return str(message.user.id) + str(ctx.guild.id)

@commands.command()
async def build(ctx):
    for channel in ctx.guild.text_channels[1]: #TESTING - REMOVE [1]
        after = None
        while True:
            async for message in channel.history(limit=100,after=after,oldest_first=True):
                words = message.split()
                userid = getuserid(message, channel)
                #insert the first word of the message
                await db_start_insert.fetch(userid,words[0])
                await db_end_insert.fetch(userid,words[-1])
                for (index, word) in enumerate(words[:-1]):
                    await db_word_insert.fetch(userid,word,words[index+1])
                after = message
            break #TESTING
            if after.id == channel.last_message_id:
                break
            db_progress.fetch(channel.id,after.id)
        await db.execute("UPDATE progress SET message_id=0 WHERE channel_id=$1",channel.id)
        

loop = asyncio.get_event_loop()
loop.run_until_complete(run(config.token))