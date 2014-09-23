#!/usr/bin/env python
__author__ = 'Joe Totaro'

import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
import musicbrainzngs
import mutagen
from mutagen.easyid3 import EasyID3
from mutagen.easymp4 import EasyMP4
from mutagen.oggvorbis import OggVorbis
from mutagen.flac import FLAC
from optparse import OptionParser
import os
import smtplib
import urllib

musicbrainzngs.set_useragent(
    "new_music_finder.py",
    "0.2",
    "https://joetotaro.net",
)
musicbrainzngs.set_rate_limit(limit_or_interval=1.0, new_requests=1)
FORMAT = '%(asctime)s %(levelname)s %(funcName)s:%(lineno)d %(message)s'


def find_releases(artists_set, year_month):
    good = u""
    questionable = u""

    for artist in artists_set:
        result = musicbrainzngs.search_releases(
            query=u"artist:\"{}\" AND date:{}-?? AND status:official AND primarytype:album".format(artist, year_month))

        if not result['release-list']:
            Logger.debug("no release found for artist %s", artist)

        music_brains_links = u""
        for (idx, rel) in enumerate(result['release-list'], start=1):
            log_album(artist, rel, idx)
            music_brains_links += u'<a href="http://musicbrainz.org/release/{}">{}</a> '\
                .format(rel['id'], rel.get('country', 'NONE'))
            if idx < len(result['release-list']) and rel['title'] == result['release-list'][idx]['title']:
                continue

            album_info = u"<b>{}</b>".format(artist)
            if artist != rel["artist-credit-phrase"]:
                album_info += u"({})".format(rel["artist-credit-phrase"])

            album_info += u" - {} - Released {} in {}<br/>\n".format(rel['title'], rel['date'], music_brains_links)
            music_brains_links = u""
            album_info += u'Links: <a href="https://play.google.com/music/listen#/sr/{0}">Google Music</a> ' \
                          u'<a href="http://www.emusic.com/search/music/?s={0}">eMusic</a> ' \
                          u'<br/><br/>'.format(urllib.quote_plus(rel['title'].encode('utf8')))

            if artist.lower() == rel["artist-credit-phrase"].lower():
                good += album_info
            else:
                questionable += album_info

    return good + questionable


def log_album(artist, rel, idx):
    album_info = u"{}({})#{} - {}\n".format(artist, rel["artist-credit-phrase"], idx, rel['title'])
    if 'date' in rel:
        album_info += u"Released {} in {}, ID:{}".format(rel['date'], rel.get('country', 'NONE'),
                                                         rel['id'])
    if rel['ext:score'] < 100:
        album_info += " *Abnormal Score of {}*".format(rel['ext:score'])
    if rel['status'] != "Official":
        album_info += u" *Abnormal Status of {}*".format(rel['status'])
    album_info += "\n"
    Logger.info(album_info)


def read_artists(path):
    artist_set = set()

    total_count = 0
    unreadable_count = 0
    for root, dirs, files in os.walk(path, topdown=False):
        file_count = 0
        for file_count, filename in enumerate(files, start=1):
            path = root + "/" + filename
            ext = os.path.splitext(path)[1]

            # skip some common file extensions that may be found in music folders
            if filename.startswith(".") or ext == ".jpg" or ext == ".m3u" or ext == ".txt":
                continue
            try:
                # guess the file type by extension. this is faster than looking at file contents
                if ext == ".m4v" or ext == ".mp4" or ext == ".m4a":
                    audio = EasyMP4(path)
                elif ext == ".ogg":
                    audio = OggVorbis(path)
                elif ext == ".flac":
                    audio = FLAC(path)
                else:
                    audio = EasyID3(path)

            except Exception as e:
                Logger.debug(e)
                # try slower magic number/tag lookup if filename based guess doesn't work.
                audio = mutagen.File(path, easy=True)

            if audio is not None and 'artist' in audio:
                for artist in audio['artist']:
                    if len(artist) != 0 and not artist.lower().startswith("various") and not artist.lower().startswith(
                            "unknown"):
                        artist_set.add(artist)
            else:
                unreadable_count += 1

        total_count += file_count
    Logger.info("Total files %i, Total unreadable %i", total_count, unreadable_count)
    Logger.info("Total artist count %i", len(artist_set))
    Logger.debug(artist_set)

    return artist_set


def mail_results(sender_email, recipient_email, html_body, year_month):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = "Music Releases - {}".format(year_month)
    msg['From'] = sender_email
    msg['To'] = recipient_email

    part = MIMEText(html_body, 'html', 'utf-8')

    msg.attach(part)
    s = smtplib.SMTP('localhost')

    s.sendmail(sender_email, recipient_email.split(','), msg.as_string())
    s.quit()


if __name__ == '__main__':

    parser = OptionParser(usage="%prog [options] MUSIC-DIRECTORY")
    parser.add_option("-t", "--to", metavar="TO-ADDRESS", help="Email address where the report should be sent")
    parser.add_option("-f", "--from", default="mailer@localhost", metavar="FROM-ADDRESS", dest="sender",
                      help="Optional email address for the 'from' field")
    parser.add_option("-l", "--logfile", metavar="LOG-LOCATION",
                      help="Set the location of the log file, otherwise logging will go to the console")

    (options, args) = parser.parse_args()
    if not args:
        parser.error("no music directory specified")
    music_dir = args.pop(0)
    if not options.to:
        parser.error("no 'to' email address specified")
    if not options.logfile:
        logging.basicConfig(format=FORMAT)
    else:
        logging.basicConfig(filename=options.logfile, format=FORMAT)
    Logger = logging.getLogger("NewMusicFinder")
    Logger.setLevel(logging.INFO)

    artists = read_artists(music_dir)
    # artists = set(["Queen"])
    this_month = datetime.date.today().strftime("%Y-%m")
    html_results = find_releases(artists, this_month)
    # Logger.info(html_results)

    mail_results(options.sender, options.to, html_results, this_month)