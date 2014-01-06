#!/usr/bin/python

import struct
import sys
import os
import base64
import zlib

try:
    from xmlrpc.client import ServerProxy, Error
except ImportError:
    from xmlrpclib import ServerProxy, Error

MOVIE_EXTS = (".avi", ".mkv", ".mp4", ".wmv")
SUB_EXTS = (".srt", ".sub", ".mpl")

def find_movies(movie_dir):
    # Traverse the directory tree and select all movie files
    movies = []
    subtitles = set()

    for root, _, files in os.walk(movie_dir):
        for f in files:
            name, ext = os.path.splitext(f)
            if ext.lower() in SUB_EXTS:
                subtitles.add(os.path.join(root, name))
            if ext.lower() in MOVIE_EXTS:
                movies.append(os.path.join(root, f))

    return filter(lambda m : os.path.splitext(m)[0] not in subtitles, movies)

class SubtitleDownload:
    '''Traverses a directory and all subdirectories and downloads subtitles.

    Relies on an undocumented OpenSubtitles feature where subtitles seems to be
    sorted by filehash and popularity.
    '''

    api_url = 'http://api.opensubtitles.org/xml-rpc'
    login_token = None
    server = None
    moviefiles = []

    def __init__(self, file_list, lang = "eng"):
        print("OpenSubtitles Subtitle Downloader".center(78))
        print("===================================".center(78))
        if len(file_list) == 0 :
            print "no files found"
            return

        self.server = ServerProxy(self.api_url, verbose=False)
        self.lang_id = lang

        for file_path in file_list:
            print("Found: " + file_path)
            filehash = self.hashFile(file_path)
            filesize = os.path.getsize(file_path)
            self.moviefiles.append({'file': file_path,
                                    'hash': filehash,
                                    'size': filesize,
                                    'subtitleid': None})

        try:
            print("Login...")
            self.login()

            print("Searching for subtitles...")
            self.search_subtitles()

            print("Logout...")
            self.logout()
        except Error as e:
            print("XML-RPC error:", e)
        except UserWarning as uw:
            print(uw)


    def login(self):
        '''Log in to OpenSubtitles'''
        resp = self.server.LogIn('', '', 'en', 'OS Test User Agent')
        self.check_status(resp)
        self.login_token = resp['token']

    def logout(self):
        '''Log out from OpenSubtitles'''
        resp = self.server.LogOut(self.login_token)
        self.check_status(resp)

    def search_subtitles(self):
        '''Search OpenSubtitles for matching subtitles'''
        search = []
        for movie in self.moviefiles:
            search.append({'sublanguageid': self.lang_id,
                           'moviehash': movie['hash'],
                           'moviebytesize': str(movie['size'])})

        # fixes weird problem where subs aren't found when only searching
        # for one movie.
        if len(search) == 1:
            search.append(search[0])

        resp = self.server.SearchSubtitles(self.login_token, search)
        self.check_status(resp)

        if resp['data'] == False:
            print("No subtitles found")
            return

        subtitles = []
        for result in resp['data']:
            if int(result['SubBad']) != 1:
                subtitles.append({'subid': result['IDSubtitleFile'],
                                  'hash': result['MovieHash']})

        downloadable_subs = subtitles[:]
        hash = None
        for s in subtitles:
            if hash == s['hash']:
                downloadable_subs.remove(s)
            hash = s['hash']

        for ds in downloadable_subs:
            sub = self.download_subtitles(ds)
            for movie in self.moviefiles:
                if movie['hash'] == ds['hash']:
                    print("Saving subtitle for: " + movie['file'])
                    filename = os.path.splitext(movie['file'])[0] + ".srt"
                    file = open(filename, "wb")
                    file.write(sub)
                    file.close()

    def download_subtitles(self, subtitle):
        resp = self.server.DownloadSubtitles(self.login_token, [subtitle['subid']])
        self.check_status(resp)
        decoded = base64.standard_b64decode(resp['data'][0]['data'].encode('ascii'))
        decompressed = zlib.decompress(decoded, 15 + 32)
        return decompressed

    def check_status(self, resp):
        '''Check the return status of the request.

        Anything other than "200 OK" raises a UserWarning
        '''
        if resp['status'].upper() != '200 OK':
            raise UserWarning("Response error from " + self.api_url + ". Response status was: " + resp['status'])

    def hashFile(self, name):
        '''Calculates the hash value of a movie.

        Copied from OpenSubtitles own examples:
            http://trac.opensubtitles.org/projects/opensubtitles/wiki/HashSourceCodes
        '''
        try:
            longlongformat = 'q'  # long long
            bytesize = struct.calcsize(longlongformat)

            f = open(name, "rb")

            filesize = os.path.getsize(name)
            hash = filesize

            if filesize < 65536 * 2:
                return "SizeError"

            for x in range(65536//bytesize):
                buffer = f.read(bytesize)
                (l_value,)= struct.unpack(longlongformat, buffer)
                hash += l_value
                hash = hash & 0xFFFFFFFFFFFFFFFF #to remain as 64bit number

            f.seek(max(0,filesize-65536),0)
            for x in range(65536//bytesize):
                buffer = f.read(bytesize)
                (l_value,)= struct.unpack(longlongformat, buffer)
                hash += l_value
                hash = hash & 0xFFFFFFFFFFFFFFFF

            f.close()
            returnedhash =  "%016x" % hash
            return returnedhash
        except(IOError):
            return "IOError"


if __name__ == '__main__':
    cwd = os.getcwd()
    if len(sys.argv) > 1:
        cwd = sys.argv[1]
    # in order to download non english subtitles add second argument
    # second language argument such as 'fre' or 'pol'
    file_list = find_movies(cwd)
    downloader = SubtitleDownload(file_list)

