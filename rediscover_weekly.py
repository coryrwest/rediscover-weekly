#!/usr/bin/env python3
import requests
import psycopg2
from psycopg2 import extras
import logging
import config
import sys
from datetime import datetime
import time
import Levenshtein
import re

conn = psycopg2.connect(dbname=config.scrobbledb['dbname'],
                        user=config.scrobbledb['user'],
                        password=config.scrobbledb['password'],
                        host=config.scrobbledb['host'],
                        port=config.scrobbledb['port'])

subsonic_conn = psycopg2.connect(dbname=config.subsonicdb['dbname'],
                        user=config.subsonicdb['user'],
                        password=config.subsonicdb['password'],
                        host=config.subsonicdb['host'],
                        port=config.subsonicdb['port'])


logger = logging.getLogger('rediscover_weekly_logger')
logging.basicConfig(level=logging.DEBUG)


# Get the random list for the playlist. 90 songs, ~ 6 hours.
# Needs about 8 hours of listening to start working well.
def get_scrobble_list():
    list_length = config.playlist_options['length']
    # percentage of random songs (0 play count) in the playlist
    randomness = config.playlist_options['randomness']
    # favoritism settings
    # how to pick songs with high play counts
    # percentage of songs in the playlist that are considered favorites
    # (top 20% of play counts)
    degree_of_favorite = 30
    num_of_random = int(round((list_length * (randomness / 100))))
    # pad the random songs to make sure we have enough including de-dupe.
    limit = int(round((list_length - num_of_random) * 1.5, 0))
    # Get all the songs played and sort them randomly
    cur = conn.cursor()
    cur.execute("""select
          name, artist, album, count(*), trunc(random() * 9 + 1) as random
        from trackscrobbles
        group by name, artist, album
        order by random
        limit %s""" % (limit,))
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
    cur = conn.cursor(cursor_factory=extras.DictCursor)
    cur.execute("""
        select
          count(*) as plays, name, artist, album
        from trackscrobbles
        group by name, artist, album
        order by count desc
        limit 1""")
    try:
        song = cur.fetchone()
        return song['plays']
    except Exception as e:
        logger.info('Failed to retrieve scrobbled tracks')
        logger.info(e)
    cur.close()
    conn.close()


def build_songid_list(songs):
    # same calculation as above.
    list_length = config.playlist_options['length']
    randomness = config.playlist_options['randomness']
    user = config.playlist_options['subsonic_user']
    num_of_random = int(round((list_length * (randomness / 100))))
    # get random least play songs from subsonic db
    newsongs = []
    with subsonic_conn.cursor(cursor_factory=extras.DictCursor) as cursor:
        # Make sure to only get songs that this user can access
        sql = '''select id from (
                  SELECT *
                  FROM media_file
                  WHERE type = 'MUSIC' and folder in (
                    select path from music_folder mf
                    where mf.id in (select music_folder_id from music_folder_user where username = '%s')
                  )
                  ORDER BY play_count
                  LIMIT 400
                ) as Music
                order by RANDOM () limit %s''' % (user, num_of_random)
        cursor.execute(sql)
        newsongs = cursor.fetchall()

    # Now we have new songs to add to the list
    for song in songs:
        name = song[0].encode('UTF-8')
        artist = song[1].encode('UTF-8')
        album = song[2]
        try:
            with subsonic_conn.cursor(cursor_factory=extras.DictCursor) as cursor:
                # TODO: Fix this injection risk
                sql = """SELECT id, title, artist
                    FROM media_file
                    WHERE type = 'MUSIC' and folder in (
                      select path from music_folder mf
                      where mf.id in (select music_folder_id from music_folder_user where username = '%s')
                    ) and title like """ % (user,)
                escaped = name.decode('UTF-8').replace("'", "''")
                sql = f"{sql} '%{escaped}%'"
                cursor.execute(sql)
                existing_songs = cursor.fetchall()
        except Exception as e:
            logger.info('Failed to search songs by name ' + name)
            logger.info(e)

        thesong = None
        for s in existing_songs:
            if match_song(s['title'].encode('UTF-8'), name, s['artist'].encode('UTF-8'), artist):
                thesong = s
                break
        if thesong is None or len(thesong) == 0:
            logger.warning('No song found for %s - %s' % (name, artist))
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
    if not songNameMatch:
        distance = Levenshtein.distance(newsong, searchedsong)
        threshold = int(round((len(searchedsong) * .1)))
        if distance <= threshold:
            songNameMatch = True
    # Try removing parens
    if not songNameMatch:
        noParensSearched = re.sub(r'\([^)]*\)', '', searchedsong)
        noParensNew = re.sub(r'\([^)]*\)', '', newsong)
        distance = Levenshtein.distance(noParensNew, noParensSearched)
        threshold = int(round((len(noParensSearched) * .1)))
        if distance <= threshold:
            songNameMatch = True
    # Try clearing text after -
    if not songNameMatch:
        searchedSplit = searchedsong.split('-', 1)[0]
        newSplit = newsong.split('-', 1)[0]
        distance = Levenshtein.distance(newSplit, searchedSplit)
        threshold = int(round((len(searchedSplit) * .1)))
        if distance <= threshold:
            songNameMatch = True
    # Try clearing text after feat.
    if not songNameMatch:
        searchedFeat = searchedsong.split('feat', 1)[0]
        newFeat = newsong.split('feat', 1)[0]
        distance = Levenshtein.distance(newFeat, searchedFeat)
        threshold = int(round((len(searchedFeat) * .1)))
        if distance <= threshold:
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
    if not artistMatch:
        distance = Levenshtein.distance(newartist, searchedartist)
        threshold = int(round((len(searchedartist) * .1)))
        if distance <= threshold:
            artistMatch = True
    # Try clearing text after feat.
    if not artistMatch:
        searchedSplit = searchedartist.split('feat', 1)[0]
        newSplit = newartist.split('feat', 1)[0]
        distance = Levenshtein.distance(newSplit, searchedSplit)
        threshold = int(round((len(searchedSplit) * .1)))
        if distance <= threshold:
            artistMatch = True

    return songNameMatch and artistMatch


def build_playlist(songidlist):
    logger.info('Songs in playlist: {count}'.format(count=len(songidlist)))
    # Get the playlist id
    with subsonic_conn.cursor(cursor_factory=extras.DictCursor) as cursor:
        sql = "select id from playlist where name = 'Rediscover Weekly'"
        cursor.execute(sql)
        playlist = cursor.fetchone()
        sql = "select id from playlist_file order by id desc limit 1"
        cursor.execute(sql)
        # get the current ID to keep the sequence correct for insert
        latest = cursor.fetchone()
        id = 1 if latest is None else latest['id']
        # delete existing songs
        sql = "delete from playlist_file where playlist_id = %s"
        cursor.execute(sql, (playlist['id'],))

    subsonic_conn.commit()

    # We do not have a rediscover, create it
    # build the params
    with subsonic_conn.cursor(cursor_factory=extras.DictCursor) as cursor:
        for song in songidlist:
            id += 1
            # Create a new record
            sql = "INSERT INTO playlist_file (id, playlist_id, media_file_id) VALUES (%s, %s, %s)"
            cursor.execute(sql, (id, playlist['id'], song['id']))

    subsonic_conn.commit()


def get_scrobbles():
    key = config.lastfm['key']
    user = config.lastfm['user']
    url = 'http://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user=%s&api_key=%s&format=json&limit=300' % (user, key)
    r = requests.get(url)
    s = r.json()
    if not r.ok:
        logger.error(r.text)
        return

    cur = conn.cursor(cursor_factory=extras.DictCursor)
    for item in s['recenttracks']['track']:
        if 'date' not in item:
            continue
        date = item['date']['#text']
        parseddate = datetime.strptime(date, "%d %b %Y, %H:%M")
        tick = str(time.mktime(parseddate.timetuple()))
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
