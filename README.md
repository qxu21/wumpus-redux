# wumpus

The only way to fix [Wumpus](https://github.com/qxu21/wumpus) was a full rewrite, and that's just what I did.

[**INVITE WUMPUS TO YOUR SERVER**](https://discord.com/api/oauth2/authorize?client_id=475061072173334539&permissions=68608&scope=bot)

Since processing a server is intensive, you need to open an issue to ask me to run the bot. Alternatively, host Wumpus yourself using the instructions below.

**Wumpus** is a Discord bot that leverages Markov chains to mimic Discord users in the style of /r/SubredditSimulator. The messages generated rarely resemble coherent speech, but it's good for laughs.

The only command usable by users is `wspeak <name>`, where `<name>` is a Discord username, ID, @mention, or nickname, that cannot have any spaces. If `<name>` is omitted, Wumpus will generate a message from the invoking user. Records are kept separately between servers, so if you're in multiple servers with the same host of Wumpus, there won't be any leakage.

## Hosting instructions

Prerequisites:
* Python 3.7
** pip libraries `discord`, `asyncpg`, and their dependencies
* A working PostgreSQL server
* A Discord developer account and an empty bot application

It's recommended to use venv for this.

Clone the repository and create a file called `config.py` in the root directory. It should look something like this:

```python
token = "Insert your Discord token here"
dbc = {
    "database" = "dbname", #name of your database
    "host" = "127.0.0.1", #IP address of your database, probably localhost
    "user" = "username", #i recommend creating a user with CREATE ROLE
    "password" = "PASSWORD"
}
```

Switch to your `postgres` user, run the command line application `psql`, and execute the following:
```sql
CREATE DATABASE wumpus;
CREATE ROLE wumpus WITH LOGIN PASSWORD "SET A GOOD PASSWORD";
GRANT ALL ON DATABASE wumpus TO wumpus;
```

Then run `wumpus.py` and it should work!

## How it works

Let's say you send the messages

```
I like green eggs.
I like green eggs and ham.
```

to a Discord server. The bot would break your messages down word by word, and using `[` and `]` as the special characters for beginning and end of message, the bot would break it down into

* `[` -> `I` x2
* `I` -> `like` x2
* `like` -> `green` x2
* `green` -> `eggs.` x1
* `eggs` -> `]` x1
* `green` -> `eggs` x1
* `eggs` -> `and` x1
* `and` -> `ham.` x1
* `ham.` -> `I` x1

Duplicate pairs, as seen here, increment the count of pairs in the database.

When generating a message, Wumpus randomly chooses from all pairs that start with `[`, weighted according to the count. It then sets its current state to the second word of the pair, then searches for all pairs that have the second word as their first pair. Other sources can explain Markov chains better than I can.
