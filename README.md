# rediscover-weekly
Rediscover your music (inspired by Spotify's Discover Weekly)


## How it works
Rediscover Weekly will generate a playlist every week of songs that you like and include a random subset of songs that
you haven't listened to in order to create a playlist that you will enjoy as well as help you rediscover your music.

Rediscover weekly uses Subsonic track your play counts and build the playlist for listening, and it uses Last.fm to
track your scrobble.

*Scrobbles are a more reliable measure of whether a song has been listened to. Subsonic's play_count counts a song as
soon as it is loaded, not when it is played all the way through. The subsonic android apps will also preload songs in
an effort to alleviate network interruptions. This results in songs that have not been played accruing a play count.*

## Prerequisites
 - A subsonic instance
 - MariaDB

Subsonic must be set up to use an external database. This does not support Subsonic's internal HSQLDB. This is because there is no other way to access the Play Counts in the DB.

The official Subsonic app for android will not work with this as it does not report play counts back to the server.


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

