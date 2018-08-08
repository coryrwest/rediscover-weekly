#!/usr/bin/env python3
import requests
import psycopg2
import logging
import random, string
import hashlib
from xml.dom import minidom
import config
import sys
from dateutil import parser
import time
import Levenshtein
import pymysql.cursors

conn = psycopg2.connect(dbname=config.db['dbname'], user=config.db['user'], password=config.db['password'], host=config.db['host'], port=config.db['port'])
subsonic_conn = pymysql.connect(host=config.subsonicdb['host'],
                             user=config.subsonicdb['user'],
                             password=config.subsonicdb['password'],
                             db=config.subsonicdb['dbname'],
                             charset='utf8mb4',
                             cursorclass=pymysql.cursors.DictCursor)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

list_length = config.playlist_options['length']
# percentage of random songs (0 play count) in the playlist
randomness = config.playlist_options['randomness']
# favoritism settings
# how to pick songs with high play counts
# percentage of songs in the playlist that are considered favorites
# (top 20% of play counts)
degree_of_favorite = 30
num_of_random = int(round((list_length * (randomness / 100))))


def randomword(length):
    return ''.join(random.choice(string.ascii_lowercase) for i in range(length))


# Get the random list for the playlist. 90 songs, ~ 6 hours.
# Needs about 8 hours of listening to start working.
def get_scrobble_list():
    # Get all the songs played and sort them randomly
    cur = conn.cursor()
    cur.execute("""select
          name, artist, album, count(*), trunc(random() * 9 + 1) as random
        from trackscrobbles
        group by name, artist, album
        order by random
        limit %s""" % ((list_length - num_of_random),))
    # TODO: eventually check most played songs and limit their place in the playlist.
    try:
        songs = cur.fetchall()
        return songs
    except Exception as e:
        logger.info('Failed to retrieve scrobbled tracks')
        logger.info(e)
    cur.close()
    conn.close()


# for determining most listened to songs to ensure that there is variety in the playlist.
def get_max_plays():
    cur = conn.cursor()
    cur.execute("""
        select
          count(*), name, artist, album
        from trackscrobbles
        group by name, artist, album
        order by count desc
        limit 1""")
    try:
        song = cur.fetchone()
        return song[0]
    except Exception as e:
        logger.info('Failed to retrieve scrobbled tracks')
        logger.info(e)
    cur.close()
    conn.close()


def build_songid_list(songs):
    # get random least play songs from subsonic db
    newsongs = []
    with subsonic_conn.cursor() as cursor:
        # Read a single record
        sql = '''select id from (
                  SELECT *
                  FROM media_file
                  WHERE type = 'MUSIC'
                  ORDER BY play_count
                  LIMIT 400
                ) as Music
                order by rand() limit ''' + str(num_of_random)
        cursor.execute(sql)
        newsongs = cursor.fetchall()

    # Now we have new songs to add to the list
    for song in songs:
        name = song[0]
        artist = song[1]
        album = song[2]
        try:
            with subsonic_conn.cursor() as cursor:
                # TODO: Fix this injection risk
                sql = "select id, title, artist from media_file where title like '%" + str.replace(name, "'", "\\'") + "%'"
                cursor.execute(sql)
                listsongs = cursor.fetchall()
        except Exception as e:
            logger.info('Failed to search songs by name ' + name)
            logger.info(e)

        for s in listsongs:
            if match_song(s['title'], name, s['artist'], artist):
                thesong = s
                break
        if len(thesong) == 0:
            logger.warn('No song found for %s' % (name,))
        else:
            newsongs.append(thesong)

    return newsongs


def match_song(newSongName, searchSongName, newArtistName, searchedArtistName):
    # ------
    #  SONG
    # ------
    newsong = str(newSongName).lower()
    searchedsong = str(searchSongName).lower()
    songNameMatch = False
    if newsong == searchedsong:
        songNameMatch = True
    # If distance is less than 10% of length then match
    distance = Levenshtein.distance(newsong, searchedsong)
    threshold = int(round((len(searchedsong) * .1)))
    if distance < threshold:
        songNameMatch = True
    # ------
    # ARTIST
    # ------
    newartist = str(newArtistName).lower()
    searchedartist = str(searchedArtistName).lower()
    artistMatch = False
    if newartist == searchedartist:
        artistMatch = True
    # If distance is less than 10% of length then match
    distance = Levenshtein.distance(newartist, searchedartist)
    threshold = int(round((len(searchedartist) * .1)))
    if distance < threshold:
        artistMatch = True

    return songNameMatch and artistMatch


def build_playlist(songidlist):
    logger.info('Songs in playlist: {count}'.format(count=len(songidlist)))
    # Get the playlist id
    with subsonic_conn.cursor() as cursor:
        sql = "select id from playlist where name = 'Rediscover Weekly'"
        cursor.execute(sql)
        playlist = cursor.fetchone()
        sql = "select id from playlist_file order by id desc limit 1"
        cursor.execute(sql)
        id = cursor.fetchone()['id']
        # delete existing songs
        sql = "delete from playlist_file where playlist_id = %s"
        cursor.execute(sql, (playlist['id'],))

    subsonic_conn.commit()

    # We do not have a rediscover, create it
    # build the params
    with subsonic_conn.cursor() as cursor:
        for song in songidlist:
            id += 1
            # Create a new record
            sql = "INSERT INTO playlist_file (id, playlist_id, media_file_id) VALUES (%s, %s, %s)"
            cursor.execute(sql, (id, playlist['id'], song['id']))

    subsonic_conn.commit()


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
        except Exception as e:
            logger.info('FAILED FOR: ' + name + ' | ' + str(date))
            logger.info(e)
            conn.rollback()
        else:
            conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    type = sys.argv[1]
    if type == 'scrobble':
        get_scrobbles()
    else:
        songs = get_scrobble_list()
        songlist = build_songid_list(songs)
        build_playlist(songlist)
