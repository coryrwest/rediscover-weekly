#!/usr/bin/env python3
import requests
import psycopg2
from dateutil import parser
import logging
import time
import config
conn = psycopg2.connect(config.db)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_scrobbles():
    key = config.lastfm['key']
    user = config.lastfm['user']
    url = 'http://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user=%s&api_key=%s&format=json&limit=200' % (user, key)
    r = requests.get(url)
    s = r.json()

    cur = conn.cursor()
    for item in s['recenttracks']['track']:
        date = item['date']['#text']
        parseddate = parser.parse(date)
        tick = str(time.mktime(parser.parse(date).timetuple()))
        name = str(item['name'])
        artist = item['artist']['#text']
        album = item['album']['#text']
        cur.execute('select * from trackscrobbles where tick = %s and name = %s', (tick, name))
        try:
            row = cur.fetchone()
            if row is None:
                cur.execute('insert into trackscrobbles (date, tick, name, artist, album) values (%s, %s, %s, %s, %s)', (parseddate, tick, name, artist, album))
            else:
                logger.info('Already have data for ' + name + ' | ' + str(date))
            conn.commit()
        except Exception as e:
            logger.info('FAILED FOR: ' + name + ' | ' + str(date))
            logger.info(e)
    cur.close()
    conn.close()

if __name__ == "__main__":
    get_scrobbles()
