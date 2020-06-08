from discord.ext import commands
import discord
import asyncpg
import asyncio
import config
from random import random
import logging
import sys

#NOTE: USING PARENS [SELECT (x,y,z) FROM...] RETURNS A TUPLE INSTEAD OF WHAT I WANT.
#I DON'T EVEN KNOW ANYMORE
#note 2: sometimes there are null bytes in discord messages. why? who knows.

#TODO: continuous updating
#nonblocking wspeaks? that or purposefully block wspeaks, to vore the race condition
#crunch whole db into one user to emulate servers
#don't yell the console every time a command doesn't show
#separate users and IDs, probably
#don't attack 

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
        #self.add_command(erase)
        #self.add_command(fetch)
    
    async def on_command_error(self,ctx,err):
        try:
            if not isinstance(err,discord.ext.commands.errors.CommandNotFound):
                raise err
        except:
            raise

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
            guild_id bigint not null,
            message_id bigint not null
        );
    """)

    async with db.acquire() as conn:
        preps = {
            "db_begin": await conn.prepare("begin;"),
            "db_rollback": await conn.prepare("rollback;"),
            "db_commit": await conn.prepare("commit;"),
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
                insert into progress (channel_id, guild_id, message_id) values
                ($1, $2, $3)
                on conflict (channel_id) do update
                set message_id=$3;
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

bot_id = 475061072173334539

@commands.command()
@commands.is_owner()
async def build(ctx):
    me = ctx.guild.get_member(bot_id)
    for channel in ctx.guild.text_channels:
        perms = channel.permissions_for(me)
        if not perms.read_messages or not perms.read_message_history:
            continue
        afterid = await ctx.bot.db.fetchval("SELECT message_id FROM progress WHERE channel_id=$1;",channel.id)
        if afterid is not None:
            try:
                after = await channel.fetch_message(afterid) #bug caused by having this as ctx
            except:
                after = None
        else:
            after = None
        while True:
            c = True
            await ctx.bot.db_begin.fetch()
            try:
                async for message in channel.history(limit=100,after=after,oldest_first=True):
                    c = False
                    after = message #scope breaks if i deindent
                    #it took 24 hours to learn that i need to sanitize null bytes
                    words = message.clean_content.replace("\u0000","").split()
                    userid = getuserid(message, channel)
                    if len(words) < 1:
                        continue
                    await ctx.bot.db_start_insert.fetch(userid,words[0])
                    await ctx.bot.db_end_insert.fetch(userid,words[-1])
                    for (index, word) in enumerate(words[:-1]):
                        await ctx.bot.db_word_insert.fetch(userid,word,words[index+1])
            except:
                await ctx.bot.db_rollback.fetch()
                raise
            await ctx.bot.db_commit.fetch()
            await ctx.bot.db_progress.fetch(channel.id, ctx.guild.id, after.id)
            #TODO - don't log when after is the last message
            logger.debug(
                f"Processed message at {after.created_at.isoformat(timespec='seconds')} in channel {after.channel.name}."
            ) #may not be the same as channel
            if c:
                break
        logger.debug(f"Channel #{channel.name} complete.")
    logger.debug(f"Guild {ctx.guild.name} complete.")
@commands.command()
@commands.is_owner()
async def erase(ctx):
    for channel in ctx.guild.text_channels:
        await ctx.bot.db.execute("DELETE FROM progress WHERE channel_id=$1;",channel.id)
        logger.debug(f"Deleted progress of channel #{channel.name}")

@commands.command()
@commands.is_owner()
async def fetch(ctx):
    await ctx.send("—\u0000—\u0000")
#async def fetch(ctx,i:int,j:int):
#    await ctx.send(ctx.guild.()).jump_url)
#    m = await ctx.guild.get_channel(i).fetch_message(j)
#    with open("m","w") as f:
#        f.write(m.content)

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
async def speak(ctx, member:discord.Member = None): #FIX PARSING - ALLOW SPACES
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
handler = logging.FileHandler("wumpus.log")
handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
logger.addHandler(handler)
#logging.basicConfig(filename="wumpus.log",level=logging.DEBUG,format="%(asctime)s: %(message)s")
loop = asyncio.get_event_loop()
loop.run_until_complete(run(config.token))
