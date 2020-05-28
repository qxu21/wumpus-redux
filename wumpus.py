from discord.ext import commands
import asyncpg
import asyncio
import config


class Wumpus(commands.Bot):
    def __init__(self, db, preps):
        super().__init__(
            command_prefix="w"
        )
        self.db = db
        for (key, val) in preps.items():
            setattr(self ,key ,val)
        
        self.remove_command("help")
        self.add_command(build)

async def run(token):
    db = await asyncpg.create_pool(**config.dbc)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS words(
            id varchar not null,
            before varchar,
            after varchar,
            count integer not null,
            primary key (id, before, after)
        );
    """)

    await db.execute("""
        create table if not exists progress(
            channel_id bigint primary key,
            message_id bigint not null
        );
    """)
    async with db.acquire() as conn:
        preps = {
            "db_start_insert": await conn.prepare("""
                insert into words (id, before, after, count) values
                ($1, NULL, $2, 1)
                on conflict (id, before, after) do update 
                set count=words.count + 1;
            """),
            "db_word_insert": await conn.prepare("""
                insert into words (id, before, after, count) values
                ($1, $2, $3, 1)
                on conflict (id, before) do update 
                set count=words.count + 1;
            """),
            "db_end_insert": await conn.prepare("""
                insert into words (id, before, after, count) values
                ($1, $2, NULL, 1)
                on conflict (id, before) do update 
                set count=words.count + 1;
            """),
            "db_progress": await conn.prepare("""
                insert into progress (channel_id, message_id) values
                ($1, $2)
                on conflict (channel_id) do update
                set message_id=$2;
            """)
        }
    wumpus = Wumpus(db=db,preps=preps)
    try:
        await wumpus.start(token)
    except KeyboardInterrupt:
        await db.close()
        await wumpus.logout()

def getuserid(message, ctx):
    return str(message.user.id) + str(ctx.guild.id)

@commands.command()
async def build(ctx):
    for channel in ctx.guild.text_channels[0]: #TESTING - REMOVE [1]
        after = None
        while True:
            async for message in channel.history(limit=100,after=after,oldest_first=True):
                words = message.split()
                userid = getuserid(message, channel)
                #insert the first word of the message
                await ctx.bot.db_start_insert.fetch(userid,words[0])
                await ctx.bot.db_end_insert.fetch(userid,words[-1])
                for (index, word) in enumerate(words[:-1]):
                    await ctx.bot.db_word_insert.fetch(userid,word,words[index+1])
                after = message
            await ctx.send(f"Made it to {after.clean_content}")
            break #TESTING
            if after.id == channel.last_message_id:
                break
            ctx.bot.db_progress.fetch(channel.id, after.id)
        await ctx.bot.db.execute("UPDATE progress SET message_id=0 WHERE channel_id=$1",channel.id)
        

loop = asyncio.get_event_loop()
loop.run_until_complete(run(config.token))