from math import isnan
import configparser
import aiohttp
import logging
from functools import reduce
import discord
from discord.ext import commands
import io
import string
import json
import requests
import sys
sys.dont_write_bytecode = True

logging.basicConfig(level=logging.INFO)
config = configparser.ConfigParser()
bot = commands.Bot(command_prefix='!')


def getuserid(jsonData, region):
    # Get userid from wargaming API

    request_url = ''
    for stuff in jsonData['vehicles']:
        request_url = request_url + stuff['name'] + ','

    request_url = 'https://api.worldofwarships.' + region + '/wows/account/list/?application_id=2b7fe83ad3455ce47818ecb2cb9d5818&search=' + \
        request_url[:-1] + '&type=exact'
    data = json.loads(requests.get(request_url).text)
    #print(json.dumps(data, indent=4, sort_keys=True))
    return data


def getuserdata(getuserid, region):
    # Get user statistics rrom wargaming API

    request_url = ''
    fields = '&fields=nickname,statistics.pvp.battles,statistics.pvp.wins,hidden_profile'
    for stuff in getuserid['data']:
        request_url = request_url + str(stuff['account_id']) + ','
    request_url = 'https://api.worldofwarships.' + region + '/wows/account/info/?application_id=2b7fe83ad3455ce47818ecb2cb9d5818&account_id=' + \
        request_url[:-1] + fields
    data = json.loads(requests.get(request_url).text)
    return data


def calcwtr(expected, actual):
    def save_div(x, y):
        if(y == 0):
            return 0
        return x / y
    wins = save_div(actual['wins'], expected['wins'])
    damage_dealt = save_div(actual['damage_dealt'], expected['damage_dealt'])
    ship_frags = save_div(actual['frags'], expected['frags'])
    capture_points = save_div(
        actual['capture_points'], expected['capture_points'])
    dropped_capture_points = save_div(
        actual['dropped_capture_points'], expected['dropped_capture_points'])
    planes_killed = save_div(
        actual['planes_killed'], expected['planes_killed'])
    ship_frags_importance_weight = 10
    frags = 1.0

    if(expected['planes_killed'] + expected['frags'] > 0):
        aircraft_frags_coef = expected['planes_killed'] / (
            expected['planes_killed'] + ship_frags_importance_weight * expected['frags'])
        ship_frags_coef = 1 - aircraft_frags_coef
        if(aircraft_frags_coef == 1):
            frags = planes_killed
        elif(ship_frags_coef == 1):
            frags = ship_frags
        else:
            frags = ship_frags * ship_frags_coef + planes_killed * aircraft_frags_coef

    average_level = actual['tier_points'] / actual['battles']
    wins_weight = 0.2
    damage_weight = 0.5
    frags_weight = 0.3
    capture_weight = 0.0
    dropped_capture_weight = 0.0

    def fixNaN(value):
        if(isnan(value)):
            return 0
        else:
            return value

    wtr = (
        (fixNaN(wins) * wins_weight) +
        (fixNaN(damage_dealt) * damage_weight) +
        (fixNaN(frags) * frags_weight) +
        (fixNaN(capture_points) * capture_weight) +
        (fixNaN(dropped_capture_points) * dropped_capture_weight)
    )

    nominal_rating = 1000.0

    def adjust(value, average_level, base):
        neutral_level = 7.5
        per_level_bonus = 0.1
        adjusted_base = min(value, base)
        for_adjusting = max(0, value - base)
        coef = 1 + (average_level - neutral_level) * per_level_bonus
        return adjusted_base + for_adjusting * coef

    return adjust(wtr * nominal_rating, average_level, nominal_rating)


def getshipwtr(getuserid, jsonData, region):
    playerwtr = {}
    actual = {}
    coefficients = json.load(open('coefficients.json', encoding='utf-8'))
    shipdb = json.load(open('shipdb.json', encoding='utf-8'))
    fields = 'pvp.wins,pvp.battles,pvp.frags,pvp.damage_dealt,pvp.dropped_capture_points,pvp.capture_points,pvp.planes_killed,ship_id'
    for vehicles in jsonData['vehicles']:
        for data in getuserid['data']:
            if(vehicles['name'] == data['nickname']):
                request_url = (
                    'https://api.worldofwarships.' + region + '/wows/ships/stats/?application_id=2b7fe83ad3455ce47818ecb2cb9d5818&' +
                    'account_id=' + str(data['account_id']) +
                    '&ship_id=' + str(vehicles['shipId']) +
                    '&language=en&fields=' + fields
                )
                pvp = json.loads(requests.get(request_url).text)

                for k, v in pvp['data'].items():
                    if v[0]['pvp'] is None:
                        playerwtr[str(k)] = {}
                        playerwtr[str(k)]['wtr'] = 'FSTG'
                        continue
                    for expected in coefficients['expected']:
                        if(expected['ship_id'] == vehicles['shipId']):
                            for o, p in shipdb.items():
                                if(int(o) == vehicles['shipId']):
                                    actual = v[0]['pvp']
                                    actual['tier_points'] = p['tier']
                                    actual['wins'] = actual['wins'] / \
                                        actual['battles']
                                    actual['damage_dealt'] = actual['damage_dealt'] / \
                                        actual['battles']
                                    actual['frags'] = actual['frags'] / \
                                        actual['battles']
                                    actual['planes_killed'] = actual['planes_killed'] / \
                                        actual['battles']
                                    actual['tier_points'] = actual['tier_points'] * \
                                        actual['battles']
                                    playerwtr[str(k)] = {}
                                    playerwtr[str(k)]['wtr'] = int(
                                        round(calcwtr(expected, actual)))
    return playerwtr


def getassembleddata(userdata, jsonData, playerwtr):
    assembleddata = {}
    for k, v in userdata['data'].items():
        assembleddata[k] = {}
        if(v['hidden_profile'] == False):
            assembleddata[k]['WR'] = str(round(
                (v['statistics']['pvp']['wins'] * 100 / v['statistics']['pvp']['battles']), 2))
        else:
            assembleddata[k]['WR'] = '-BURDEN-'
        assembleddata[k]['nickname'] = v['nickname']
    # Rearrange team by putting relation data scrapped from replay
    for stuff in jsonData['vehicles']:
        for k, v in assembleddata.items():
            if(stuff['name'] == assembleddata[k]['nickname']):
                assembleddata[k]['team'] = stuff['relation']
    # Merge current json with playerwtr json
    for i, j in assembleddata.items():
        for x, y in playerwtr.items():
            if i == x:
                j.update(y)
    return assembleddata


def getclaninfo(getuserid, region, owner):
    clantag = []
    request_url = ''
    for stuff in getuserid['data']:
        request_url = request_url + str(stuff['account_id']) + ','
    request_url = 'https://api.worldofwarships.' + region + '/wows/clans/accountinfo/?application_id=2b7fe83ad3455ce47818ecb2cb9d5818&account_id=' + \
        request_url[:-1] + '&language=en&extra=clan'
    data = json.loads(requests.get(request_url).text)

    # sorting team
    for k, v in data['data'].items():
        if(v['clan']['tag'] not in clantag):
            clantag.append(v['clan']['tag'])
        if(owner == v['account_name']):
            if(clantag[1] == v['clan']['tag']):
                clantag[1] = clantag[0]
                clantag[0] = v['clan']['tag']
    return clantag


def getgamemode(gamemode):
    if(gamemode == 7):
        return 'Domination'
    elif(gamemode == 11):
        return 'Standard'
    elif(gamemode == 12):
        return 'Epicenter'
    elif(gamemode == 14):
        return 'Scenario'
    else:
        return 'Unknown'


def createtable(assembleddata, playersPerTeam, playerName, clans, matchGroup, gamemode):
    header = ''
    header2 = ''

    chat = '```\n Requested by ' + playerName + '\n'
    chat = chat + '\n Game mode : ' + gamemode

    chat = chat + '\n---------------------------------------------------------------'
    if(matchGroup != 'clan'):
        header = '\n            My Team             |          Enemy Team        '
    else:
        while (len(header) < (15-(int(len(clans[0])/2)))):
            header = header + ' '
        header = header + clans[0]
        while (len(header) < 32):
            header = header + ' '
        header = header + '|'
        while (len(header2) < (15-(int(len(clans[1])/2)))):
            header2 = header2 + ' '
        header2 = header2 + clans[1]
        while (len(header2) < 32):
            header2 = header2 + ' '
        header = '\n' + header + header2

    chat = chat + header
    chat = chat + '\n---------------------------------------------------------------'

    team1name = []
    team1wr = []
    team2name = []
    team2wr = []

    team2wr_avg = []
    team1wr_avg = []
    team2wr_avgwtr = []
    team1wr_avgwtr = []
    part1 = ''
    part2 = ''
    i = 0
    # Sorting by winrate
    sorted_keys = sorted(assembleddata.keys(), key=lambda y: (
        assembleddata[y]['WR']), reverse=True)

    for outer_key in sorted_keys:
        if(len(assembleddata[outer_key]['WR']) == 4):
            assembleddata[outer_key]['WR'] = assembleddata[outer_key]['WR'] + '0'

        if((assembleddata[outer_key]['team'] == 0) or (assembleddata[outer_key]['team'] == 1)):
            team1name.append(assembleddata[outer_key]['nickname'][:13])
            if(assembleddata[outer_key]['WR'] == '-BURDEN-'):
                team1wr.append(assembleddata[outer_key]['WR'])
            else:
                team1wr.append(
                    assembleddata[outer_key]['WR'] + '% | ' + str(assembleddata[outer_key]['wtr']))
                team1wr_avg.append(assembleddata[outer_key]['WR'])
                team1wr_avgwtr.append(assembleddata[outer_key]['wtr'])
        else:
            team2name.append(assembleddata[outer_key]['nickname'][:13])
            if(assembleddata[outer_key]['WR'] == '-BURDEN-'):
                team2wr.append(assembleddata[outer_key]['WR'])
            else:
                team2wr.append(
                    assembleddata[outer_key]['WR'] + '% | ' + str(assembleddata[outer_key]['wtr']))
                team2wr_avg.append(assembleddata[outer_key]['WR'])
                team2wr_avgwtr.append(assembleddata[outer_key]['wtr'])
        i += 1

    for x in range(playersPerTeam):
        while(len(team1name[x]) < 13):
            team1name[x] = team1name[x] + ' '
        while(len(team2name[x]) < 13):
            team2name[x] = team2name[x] + ' '
        part1 = team1name[x] + ' - ' + team1wr[x]
        part2 = ' ' + team2name[x] + ' - ' + team2wr[x]

        while (len(part1) < 32):
            part1 = part1 + ' '
        part1 = part1 + '|'
        while (len(part2) < 32):
            part2 = part2 + ' '

        chat = chat + '\n' + part1 + part2
    chat = chat + '\n---------------------------------------------------------------'
    footer1 = 'Avg           - ' + str(round(float(sum(map(float, team1wr_avg))/len(team1wr_avg)), 2)) + \
        '% | ' + \
        str(round(float(sum(map(float, team2wr_avgwtr))/len(team1wr_avgwtr))))
    footer2 = 'Avg           - ' + str(round(float(sum(map(float, team2wr_avg))/len(team2wr_avg)), 2)) + \
        '% | ' + \
        str(round(float(sum(map(float, team2wr_avgwtr))/len(team2wr_avgwtr))))
    while (len(footer1) < 32):
        footer1 = footer1 + ' '
    footer1 = footer1 + '|'
    footer2 = ' ' + footer2
    while (len(footer2) < 32):
        footer2 = footer2 + ' '

    chat = chat + '\n' + footer1 + footer2
    chat = chat + '```'
    return chat


@bot.event
async def on_ready():
    bot.remove_command("help")
    await bot.change_presence(game=discord.Game(name="!what !howto !cid"))


@bot.event
async def on_message(message):
    if (message.channel.id == '400226989321093121'):
        convert = reduce(lambda r, d: r.update(
            d) or r, message.attachments, {})
        websocket = convert.get('url')
        r = await aiohttp.get(websocket)
        jsonData = await r.json()
        playersPerTeam = int(len(jsonData['vehicles']) / 2)
        channel_id = jsonData['channel_id']
        owner = jsonData['playerName']
        region = jsonData['region']
        gamemode = getgamemode(jsonData['gameMode'])
        matchGroup = jsonData['matchGroup']
        if(jsonData['region'] != 'invalid'):
            if((matchGroup != 'pve')):
                clans = []
                userid = getuserid(jsonData, region)
                userdata = getuserdata(userid, region)
                playerwtr = getshipwtr(userid, jsonData, region)
                assembleddata = getassembleddata(userdata, jsonData, playerwtr)
                if(matchGroup == 'clan'):
                    clans = getclaninfo(userid, region, owner)
                await bot.send_message(bot.get_channel(channel_id), createtable(assembleddata, playersPerTeam, owner, clans, matchGroup, gamemode))
                if (owner != 'bucksgen'):
                    await bot.send_message(bot.get_channel('405077159221395466'), '→\n[' + bot.get_channel(channel_id).server.name + '](' + bot.get_channel(channel_id).server.id + ')\n' +
                                           '[' + bot.get_channel(channel_id).name + '](' + bot.get_channel(channel_id).id + ')\n' + owner + '\n' + 'WR request')

    await bot.process_commands(message)


def logstring(ctx):
    return ('→\n[' + str(ctx.message.channel.server) + '] (' + ctx.message.channel.server.id +
            ')\n[' + ctx.message.channel.name + '] (' + ctx.message.channel.id +
            ')\n[' + ctx.message.author.name + '] {' + str(ctx.message.author) + '} (' + ctx.message.author.id +
            ')\n' + ctx.message.content)


@bot.command(pass_context=True)
async def cid(ctx):
    if (ctx.message.author.id != '114881658045464581'):
        await bot.say(ctx.message.channel.id)
        await bot.send_message(bot.get_channel('405077159221395466'), logstring(ctx))


@bot.command(pass_context=True)
async def what(ctx):
    if (ctx.message.author.id != '114881658045464581'):
        embed = discord.Embed(title='WoWs Win Rate Checker',
                              description='This bot will post your team and enemy players win rate table when you start a new match. Developed by <@114881658045464581>. !howto for instruction to use the bot.', color=0x9d2ca7)
        await bot.say(embed=embed)
        await bot.send_message(bot.get_channel('405077159221395466'), logstring(ctx))


@bot.command(pass_context=True)
async def howto(ctx):
    if (ctx.message.author.id != '114881658045464581'):
        config.read('serverconfig.ini')
        invitelink = config.get('links', 'invitelink')
        downloadlink = config.get('links', 'downloadlink')
        howto = "\
1. Invite the bot to your server if the bot not in the server already.\n\
2. Download the client app and extract it anywhere you want.\n\
3. Go to channel you want the bot to post the win rate table, use !cid command and copy the numbers.\n\
4. Open the folder you've extracted and open config.ini.\n\
5. Fill the region field with na/eu/asia/ru and channel_id with the numbers you copied earlier. See image below for example.\n\
6. Run client.exe and you're all set! Play the game and the bot will post the table automatically."

        note = "\
1. You must enable replay on your WoWS client to use the bot.\n\
2. The client.exe don't have any user interface and run in the background, you must use task manager to close it."

        embed = discord.Embed(title='How to Use',
                              description='', color=0x00ff00)
        embed.add_field(name='Invite link', value=invitelink, inline=False)
        embed.add_field(name='Download link', value=downloadlink, inline=False)
        embed.add_field(name='Instruction', value=howto, inline=False)
        embed.set_image(
            url='https://cdn.discordapp.com/attachments/397637547154472962/401357785868140554/unknown.png')
        embed.add_field(name='Note', value=note, inline=False)
        await bot.say(embed=embed)
        await bot.send_message(bot.get_channel('405077159221395466'), logstring(ctx))

bot.run('YOUR BOT TOKEN HERE')

