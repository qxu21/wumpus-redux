from discord.ext import commands
import discord
import asyncpg
import asyncio
import config
from random import random
import logging

#NOTE: USING PARENTS [SELECT (x,y,z) FROM...] RETURNS A TUPLE INSTEAD OF WHAT I WANT.
#I DON'T EVEN KNOW ANYMORE

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
        self.add_command(speak)

async def run(token):
    db = await asyncpg.create_pool(**config.dbc) # formerly create_pool
    #await db.execute("""
    #    drop table if exists words;
    #    drop table if exists progress;
    #""") # dear lord remove this in prod
    await db.execute("""
        CREATE TABLE IF NOT EXISTS words(
            id varchar,
            special text not null default 'NONE',
            before varchar,
            after varchar,
            count integer not null,
            primary key (id, before, after, special)
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
                insert into words (id, before, after, count, special) values
                ($1, '__placeholder__', $2, 1, 'START')
                on conflict (id, before, after, special) do update
                set count=words.count + 1;
            """),
            "db_word_insert": await conn.prepare("""
                insert into words (id, before, after, count) values
                ($1, $2, $3, 1)
                on conflict (id, before, after, special) do update
                set count=words.count + 1;
            """),
            "db_end_insert": await conn.prepare("""
                insert into words (id, before, after, count, special) values
                ($1, $2, '__placeholder__', 1, 'END')
                on conflict (id, before, after, special) do update
                set count=words.count + 1;
            """),
            "db_progress": await conn.prepare("""
                insert into progress (channel_id, message_id) values
                ($1, $2)
                on conflict (channel_id) do update
                set message_id=$2;
            """),
            "db_fetch": await conn.prepare("""
                select after,count,special from words
                where id=$1
                and before=$2
                and special!='START';
            """)
        }

        wumpus = Wumpus(db=db,preps=preps)
        try:
            await wumpus.start(token)
        except KeyboardInterrupt:
            await db.close()
            await wumpus.logout()

def getuserid(message, ctx):
    return str(message.author.id) + str(ctx.guild.id)

@commands.command()
@commands.is_owner()
async def build(ctx):
    for channel in ctx.guild.text_channels:
        after = None
        while True:
            async for message in channel.history(limit=100,after=after,oldest_first=True):
                words = message.clean_content.split()
                userid = getuserid(message, channel)
                if len(words) < 1:
                    continue
                await ctx.bot.db_start_insert.fetch(userid,words[0])
                await ctx.bot.db_end_insert.fetch(userid,words[-1])
                for (index, word) in enumerate(words[:-1]):
                    await ctx.bot.db_word_insert.fetch(userid,word,words[index+1])
                after = message
            await ctx.bot.db_progress.fetch(channel.id, after.id) 
            logger.debug(f"Processed message at {after.created_at.isoformat(timespec='seconds')} in channel {after.channel.name}.")
            if after.id == channel.last_message_id:
                break
            #await ctx.send(f"Made it to {after.clean_content}")
        logger.debug(f"{channel.name} complete.")
    logger.debug(f"{ctx.guild.name} complete.")
        #await ctx.bot.db.execute("UPDATE progress SET message_id=0 WHERE channel_id=$1",channel.id)

def pick(l):
    total_count = 0
    for i in l:
        total_count += i["count"]
    location = random() * total_count
    progress = 0
    for j in l:
        progress += j["count"]
        if progress >= location:
            return j

@commands.command()
async def speak(ctx, member:discord.Member = None):
    if member == None:
        member = ctx.author
    userid = str(member.id) + str(ctx.guild.id)
    starts = await ctx.bot.db.fetch("""
        select after, count from words
        where id=$1
        and special='START';
    """,userid)
    if not starts:
        await ctx.send("No records for this user.")
        return
    m = [pick(starts)["after"]]
    c = 0
    while True:
        n = pick(await ctx.bot.db_fetch.fetch(userid,m[c]))
        if n["special"] == "END":
            break
        m.append(n["after"])
        c += 1
    await ctx.send(" ".join(m))

@speak.error
async def speak_error(ctx,error):
    if isinstance(error, commands.BadArgument):
        await ctx.send("Cannot parse that member.")
    else:
        raise error

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.FileHandler("wumpus.log"))
#logging.basicConfig(filename="wumpus.log",level=logging.DEBUG,format="%(asctime)s: %(message)s")
loop = asyncio.get_event_loop()
loop.run_until_complete(run(config.token))