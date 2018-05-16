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

conn = psycopg2.connect(dbname=config.db['dbname'], user=config.db['user'], password=config.db['password'], host=config.db['host'], port=config.db['port'])
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
url = '{base}/rest/{resource}?u={user}&t={password}&s={salt}&v=1.2.0&c=rediscoverweekly{query}'
user = config.subsonic['user']
base = config.subsonic['baseurl']
passwd = config.subsonic['password']


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


def get_url(resource, query):
    salt = randomword(6)
    salted = passwd + salt
    password = hashlib.md5(salted.encode('utf-8')).hexdigest()
    fullurl = url.format(base=base, user=user, password=password, salt=salt, resource=resource, query=query)
    return fullurl


def build_songid_list(songs):
    r = requests.get(get_url('getRandomSongs', '&size=400'))
    s = r.content
    x = minidom.parseString(s)
    randomsongs = x.getElementsByTagName('song')
    newsongs = []

    for song in randomsongs:
        count = song.attributes['playCount'].value
        if int(count) == 0 and len(newsongs) < num_of_random:
            songid = song.attributes['id'].value
            newsongs.append(songid)

    if len(newsongs) < num_of_random:
        logger.warn('not enough random songs')

    # Now we have new songs to add to the list
    for song in songs:
        name = song[0]
        artist = song[1]
        album = song[2]
        r = requests.get(get_url('search2', '&query=%s' % (name,)))
        s = r.content
        list = minidom.parseString(s)
        listsongs = list.getElementsByTagName('song')
        thesong = []
        for s in listsongs:
            if match_song(s.attributes['title'].value, name, s.attributes['artist'].value, artist):
                thesong = [s]
                break
        if len(thesong) == 0:
            logger.warn('No song found for %s' % (name,))
            break
        newsongs.append(thesong[0].attributes['id'].value)

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
    # Get the playlists to see if we already made a rediscover
    r = requests.get(get_url('getPlaylists', ''))
    s = r.content
    x = minidom.parseString(s)
    playlists = x.getElementsByTagName('playlist')
    rediscover = [i for i in playlists if str(i.attributes['name'].value) == 'Rediscover Weekly']

    if len(rediscover) != 0:
        # Delete the playlist
        id = rediscover[0].attributes['id'].value
        r = requests.get(get_url('deletePlaylist', '&id=%s' % (id,)))

    # We do not have a rediscover, create it
    # build the params
    params = '&songId='.join([str(x) for x in songidlist])
    r = requests.get(get_url('createPlaylist', '&name=Rediscover%20Weekly&songId={}'.format(params)))
    s = r.content
    x = minidom.parseString(s)


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
    type = sys.argv[1]
    if type == 'scrobble':
        get_scrobbles()
    else:
        songs = get_scrobble_list()
        songlist = build_songid_list(songs)
        #build_playlist(songlist)
