# Rediscover Weekly
Rediscover your music (inspired by Spotify's Discover Weekly)

## How it works
Rediscover Weekly will generate a playlist every week of songs that you like and include a random subset of songs that
you haven't listened to in order to create a playlist that you will enjoy as well as help you rediscover your music.

Rediscover weekly uses Subsonic to track your play counts and build the playlist for listening, and Last.fm to track
your scrobbles.

*Scrobbles are a more reliable measure of whether a song has been listened to. Subsonic's play_count counts a song as
soon as it is loaded, not when it is played all the way through. The subsonic android apps will also preload songs in
an effort to alleviate network interruptions. This results in songs that have not been played accruing a play count.*

## Prerequisites
 - Python 3.5
 - A subsonic instance
 - MariaDB
 - PostgreSQL

Subsonic must be set up to use an external database. This does not support Subsonic's internal HSQLDB.
This is because there is no other way to access the Play Counts in the DB.

The official Subsonic app for android will not work with this (unless it is set to scrobble tracks) as it does not
report play counts back to the server.

## Setup
Setup is entirely manual for now. You must build the database manually and create the table using the provided script.
Since this is just a simple python script, it is trivial to set this up via a cron job.

### Example Cron
```
# Retrieve new scrobbles every day
0 0   * * *   USER    python3 /path/to/rediscover_weekly.py scrobble
# Make new playlist every week on Sunday
0 0   * * 0   USER    python3 /path/to/rediscover_weekly.py playlist
```

## Usage
### Download scrobbles
```
python ./rediscover_weekly.py scrobble
```

### Build playlist
This will overwrite the current Rediscover Weekly playlist.
```
python ./rediscover_weekly.py playlist
```

## Future Features
 - Take play counts into account instead of just checking that they aren't 0
 - Move scrobbles to subsonic db and get rid of postgres requirement

*With enough data this can be used to weed out portions of your music library that you no longer enjoy*

