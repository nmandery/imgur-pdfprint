#!/usr/bin/env python
# coding: utf8

from jinja2 import Template
import aiohttp

import sys
import os
import os.path
from contextlib import contextmanager
import shutil
import tempfile
import codecs
import re
import subprocess
import asyncio
import struct
import imghdr

img_dir = 'img'
index_md = 'index.asciidoc'

TEMPLATE='''
{% if a.title %}
= {{a.title}}
{% endif %}
:pdf-page-size: A4

{%if a.description %}
{{a.description}}
{% endif %}

{% if a.link %}
From {{a.link}}
{% endif %}



{% for i in a.images%}
image::{{i.file}}[align="center", scaledwidth={{i.scaledwidth}}%, link="{{i.link}}"]
{% if i.title %}
{{i.title}}

{% endif %}
{%if i.description %}
{{i.description}}
{% endif %}

{% endfor %}

{% if a.comments %}
== Comments

{% for c in a.comments%}
{% if c.content %}
[quote, {%if c.author%}{{c.author}}{%else%}unknown{%endif%}]
____
{{c.content}}
____
{% endif %}
{% endfor %}
{% endif %}
'''

def get_env(var_name):
    val = os.environ.get(var_name)
    if not val:
        raise Exception("environment variable {0} must be set".format(var_name))
    return val

def get_image_size(fname):
    '''Determine the image type of fhandle and return its size.
    from draco
    http://stackoverflow.com/questions/8032642/how-to-obtain-image-size-using-standard-python-class-without-using-external-lib'''
    with open(fname, 'rb') as fhandle:
        head = fhandle.read(24)
        if len(head) != 24:
            return
        if imghdr.what(fname) == 'png':
            check = struct.unpack('>i', head[4:8])[0]
            if check != 0x0d0a1a0a:
                return
            width, height = struct.unpack('>ii', head[16:24])
        elif imghdr.what(fname) == 'gif':
            width, height = struct.unpack('<HH', head[6:10])
        elif imghdr.what(fname) == 'jpeg':
            try:
                fhandle.seek(0) # Read 0xff next
                size = 2
                ftype = 0
                while not 0xc0 <= ftype <= 0xcf:
                    fhandle.seek(size, 1)
                    byte = fhandle.read(1)
                    while ord(byte) == 0xff:
                        byte = fhandle.read(1)
                    ftype = ord(byte)
                    size = struct.unpack('>H', fhandle.read(2))[0] - 2
                # We are at a SOFn block
                fhandle.seek(1, 1)  # Skip `precision' byte.
                height, width = struct.unpack('>HH', fhandle.read(4))
            except Exception: #IGNORE:W0703
                return
        else:
            return
        return width, height

def make_imgur_client():
    from imgurpython import ImgurClient

    client_id = get_env("IMGUR_CLIENT_ID")
    client_secret = get_env("IMGUR_CLIENT_SECRET")
    return ImgurClient(client_id, client_secret)

@contextmanager
def temp_work_dir():
    directory = tempfile.mkdtemp(prefix='pdfprint')
    yield directory
    shutil.rmtree(directory, ignore_errors=True)

@contextmanager
def chdir(d):
    old_dir=os.getcwd()
    os.chdir(d)
    yield
    os.chdir(old_dir)

def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]

class BaseObject(object):
    id=None
    title=None
    description=None

class Comment(object):
    author=None
    content=None

class Album(BaseObject):
    images=[]
    comments=[]
    link=None

    @property
    def filename(self):
        title = self.title or self.description
        filename = '{0}-{1}'.format(title, self.id) if title else self.id
        return re.sub(r'_{2,}','_', re.sub(r'[^a-zA-Z0-9_\-]', '_', filename.lower().strip()))

    def apply_to_images(self, fn):
        images_new = []
        for i in self.images:
            i_new = fn(i)
            if i_new is not None:
                images_new.append(i_new)
        self.images = images_new

class Img(BaseObject):
    link = None
    default_scaledwith = 90
    _filename = None

    @property
    def filename(self):
        if self._filename is not None:
            return self._filename
        return self.link[self.link.rindex('/')+1:]

    @property
    def scaledwidth(self):
        def ratio(dims):
            return float(dims[0]) / float(dims[1])
        # scale for best fit in A4 paper
        a4 = (210, 297)
        img_size =get_image_size(os.path.join(img_dir, self.filename))

        sf=1.0
        if ratio(img_size) <= ratio(a4):
            sf = ratio(img_size)/ratio(a4)

        return int(self.default_scaledwith*sf)
	
    @property
    def file(self):
        return os.path.join(img_dir, self.filename)


def fetch_imgur(url):
    from imgurpython.helpers.error import ImgurClientError

    album = Album()
    album_id = url.split('/')[-1].split('#')[0]
    client = make_imgur_client()
    g = None
    imgur_path = None
    try:
        imgur_path = 'gallery/album/%s' % album_id
        g = client.make_request('GET', imgur_path)
    except ImgurClientError as e:
        if e.status_code == 404:
            imgur_path = 'album/%s' % album_id
            g = client.make_request('GET', imgur_path)
        else:
            raise
    album.link = 'http://imgur.com/' + imgur_path

    album.id = g.get('id')
    album.title = g.get('title')
    album.description = g.get('description')
    for i in g.get('images', []):
        img = Img()
        img.id = i.get('id')
        img.title = i.get('title')
        img.description = i.get('description')
        img.link = i.get('link')
        album.images.append(img)

    try:
        g = client.make_request('GET', imgur_path+'/comments')
        if g:
            for c in g:
                comment = Comment()
                comment.content = c.get('comment')
                comment.author = c.get('author')
                album.comments.append(comment)
    except ImgurClientError as e:
        if e.status_code != 404:
            raise
            
    return album


def fetch_simplecove(url):
    album = Album()
    album.link = url
    album.id = url.split('/')[3]

    def text_agg(elements, seperator='\n\n'):
        ts = []
        if elements is not None:
            for e in elements:
                if e is not None:
                    txt = (e.text or '').strip()
                    if txt:
                        ts.append(txt)
        return seperator.join(ts) or ''

    from pyquery import PyQuery as pq
    doc = pq(url=url)
    album.title = text_agg(doc(".titlearea h1"), seperator=' ')
    album.description = text_agg(doc(".projectdescriptioncontainer p"))

    for galleryid in ('projectphotosgalleryview', 'buildphotosgalleryview'):
        for ie in doc("#{0} div".format(galleryid)):
            ie_class = ie.get('class')
            ieq = pq(ie)
            if 'imagecontainerstretch' in ie_class:
                for ieu in ieq('img'):
                    img = Img()
                    img.id = ieu.get('src')
                    img.link = 'http://www.simplecove.com' + ieu.get('src')
                    album.images.append(img)
            elif 'imagelistcontainer' in ie_class:
                if album.images:
                    descs = []
                    if album.images[-1].description:
                        descs.append(img.description)
                    descs.append(text_agg(ieq('.imagenotes p')))
                    album.images[-1].description = '\n\n'.join(descs)

    return album

def fetch(url):
    if 'simplecove.com' in url:
        return fetch_simplecove(url)
    else: # imgur
        a = fetch_imgur(url)

        def choose_supported_format(img):
            if img.link.endswith('.gifv'):
                img.link = img.link.rstrip('v')
            return img
        a.apply_to_images(choose_supported_format)
        return a

async def download_to(session, url, filename):
    chunk_size = 60 * 1024
    with aiohttp.Timeout(120):
        async with session.get(url) as response:
            if response.status >= 400:
                raise Exception("Could not download {0}: HTTP status {1}".format(url, response.status))
            with open(filename, 'wb') as fd:
                while True:
                    chunk = await response.content.read(chunk_size)
                    if not chunk:
                        break
                    #print("writing {0} bytes to {1}".format(len(chunk), filename))
                    fd.write(chunk)

def convert_to_known_format(img):
    fwoext, ext = os.path.splitext(img.filename)
    if ext.lower() not in ('.jpg', '.jpeg', '.png'):
        new_filename = "{0}.{1}".format(fwoext, 'png')
        print('Converting {0} to {1}'.format(img.filename, new_filename))
        
        subprocess.check_call(['convert',
                os.path.join(img_dir, img.filename) + '[0]', # only first frame of animated gifs etc
                os.path.join(img_dir, new_filename)], 
                stdout=sys.stdout, stderr=sys.stderr)
        img._filename = new_filename
    return img

def convert(url):
    print('Converting {0}'.format(url))
    a = fetch(url)

    with temp_work_dir() as work_dir:
        os.makedirs(os.path.join(work_dir, img_dir))

        loop = asyncio.get_event_loop()
        with aiohttp.ClientSession(loop=loop) as session:
            count_img = len(a.images)
            for chnk in chunks(list(enumerate(a.images)), 10):
                futures = []
                for idx, i in chnk:
                    msg = 'Downloading {0}/{1}: {2}'.format(idx+1, count_img, i.link)
                    print(msg)

                    futures.append(download_to(session, i.link, os.path.join(work_dir, img_dir, i.filename)))
                if futures:
                    outer = asyncio.gather(*futures)
                    loop.run_until_complete(outer)
        loop.close()

        pdf_file = os.path.join(os.getcwd(), '{0}.pdf'.format(a.filename))
        with chdir(work_dir):
            a.apply_to_images(convert_to_known_format)
            with codecs.open(index_md, 'w', 'utf8') as fh:
                fh.write(Template(TEMPLATE).render(a=a))
                fh.flush()
                
                print('Rendering')
                subprocess.check_call(['asciidoctor-pdf', '-o', pdf_file, index_md], 
                        stdout=sys.stdout, stderr=sys.stderr)
                print("Created {0}".format(pdf_file))


if __name__ == '__main__':
    for url in sys.argv[1:]:
        convert(url)
