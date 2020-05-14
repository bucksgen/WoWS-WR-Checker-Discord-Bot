from tendo import singleton
from winreg import *
import configparser
import os
import time
import requests
import string
import io
import json
import sys
sys.dont_write_bytecode = True

me = singleton.SingleInstance()
config = configparser.ConfigParser()


def getinstallpath():
    installpath = ''
    t = OpenKey(HKEY_CURRENT_USER,
                r"Software\Wargaming.net\Launcher\Apps\wows", 0, KEY_ALL_ACCESS)
    try:
        count = 0
        while 1:
            name, value, type = EnumValue(t, count)
            if "Warship" in repr(value):
                installpath = repr(value)
            count = count + 1
            # print(installpath)
    except WindowsError:
        return installpath[1:-1]  # removing the quotes


def loadReplay():
    raw_metadata = ""
    safty = 0
    with io.open(installpath + '\\replays\\tempArenaInfo.json', 'r', encoding='ascii', errors='ignore') as infile:
        while (safty < 10 and "clientVersionFromXml" not in raw_metadata):
            raw_metadata = infile.readline()
            safty += 1
    if(safty >= 10):
        print("ERROR failed to load replay: " +
              installpath + '\\replays\\tempArenaInfo.json')
        return False
    printable = set(string.printable)
    # Filters non Ascii chars and Binary Data from string
    raw_metadata = ''.join(filter(lambda x: x in printable, raw_metadata))
    raw_metadata = '{"'+raw_metadata.split('{"', 1)[1]
    raw_metadata = raw_metadata[:raw_metadata.index(
        '"}', raw_metadata.index("playerVehicle"))]+'"}'
    return json.loads(raw_metadata)


installpath = getinstallpath()

if not os.path.isdir(installpath + '\\replays'):
    os.makedirs(installpath + '\\replays')

before = dict([(f, None) for f in os.listdir(installpath + '\\replays')])
while True:
    time.sleep(2)
    after = dict([(f, None) for f in os.listdir(installpath + '\\replays')])
    added = [f for f in after if not f in before]
    removed = [f for f in before if not f in after]
    if added:
        if (", ".join(added) == 'tempArenaInfo.json'):
            config.read('config.ini')
            data = loadReplay()
            data['channel_id'] = config.get('discordwowsbot', 'channel_id')
            if(config.get('discordwowsbot', 'region') == 'na'):
                data['region'] = 'com'
            elif(config.get('discordwowsbot', 'region') == 'asia'):
                data['region'] = 'asia'
            elif(config.get('discordwowsbot', 'region') == 'eu'):
                data['region'] = 'eu'
            elif(config.get('discordwowsbot', 'region') == 'ru'):
                data['region'] = 'ru'
            else:
                data['region'] = 'invalid'
            payload = {'payload_json': json.dumps(data)}

            r = requests.post("YOUR WEBHOOK CHANNEL", files=payload)

    before = after
