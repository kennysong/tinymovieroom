
import jinja2
import logging
import os
import random
import string
import urllib
import webapp2

from django.utils import simplejson

from google.appengine.ext import db
from google.appengine.api import channel
from google.appengine.api import urlfetch

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir), autoescape=True)

CLOUDFRONT_DOMAIN = 'http://ddmm37kppyxwy.cloudfront.net/'
TMDB_SEARCH_URL = 'http://api.themoviedb.org/3/search/movie?api_key=fc45f4e0c19068d8253cb0dcb0a1774e&query='
TMDB_IMG_URL = 'http://d3gtl9l2a4fn1j.cloudfront.net/t/p/w185'

class Rooms(db.Model):
	message = db.StringProperty()
	room_id = db.StringProperty()
	client_ids = db.StringListProperty()
	paused = db.BooleanProperty()

class Movies(db.Model):
	url = db.StringProperty()
	name = db.StringProperty()
	img_url = db.StringProperty()

class BaseHandler(webapp2.RequestHandler):
	'''Parent class for all handlers'''
	def write(self, content):
		return self.response.out.write(content)

	def rget(self, name):
		'''Gets a HTTP parameter'''
		return self.request.get(name)

	def render(self, template, params={}):
		template = jinja_env.get_template(template)
		self.response.out.write(template.render(params))

	def set_cookie(self, cookie):
		self.response.headers.add_header('Set-Cookie', cookie)

	def delete_cookie(self, cookie):
		self.response.headers.add_header('Set-Cookie', '%s=; Path=/' % cookie)

class MainHandler(BaseHandler):
	def get(self):
		client_id = rand_str(10)
		token = channel.create_channel(client_id, duration_minutes=24*60)
		room_id = self.rget('room_id')
		if not room_id: 
			# create new room
			room_id = rand_str(5)
			room = Rooms(room_id=room_id, client_ids=[client_id], paused=True)
			room.put()
		else:
			# add user to existing room
			room = get_room_by_room_id(room_id)
			room.client_ids.append(client_id)
			room.put()

		# random movie
		movie = Movies.all().get()
		url = movie.url
		img_url = movie.img_url

		self.render('index.html', {'client_id':client_id, 'room_id':room_id, 'token':token, 'img_url':img_url, 'url':url})

class UploadHandler(BaseHandler):
	def get(self):
		self.render('upload.html')

	def post(self):
		filename = self.rget('filename')
		url = CLOUDFRONT_DOMAIN + filename
		name = self.rget('moviename')

		# find movie cover
		search_name = urllib.quote(name)

		fetched = urlfetch.fetch(TMDB_SEARCH_URL+search_name, headers={'Accept': 'application/json'})
		json = simplejson.loads(fetched.content)
		entry = json['results'][0]

		img_path = entry['poster_path']
		img_url = TMDB_IMG_URL + img_path

		movie = Movies(url=url, name=name, img_url=img_url)
		movie.put()

		self.write('Uploaded!')

class ConnectHandler(BaseHandler):
	def post(self):
		client_id = self.request.get('from')
		logging.error(client_id)
		room = get_room_by_client_id(client_id)

		d = {'type':'presence', 'client_id':client_id, 'connect':1}

		for c_id in room.client_ids:
			channel.send_message(c_id, simplejson.dumps(d))


class DisconnectHandler(BaseHandler):
	def post(self):
		client_id = self.rget('from')
		room = get_room_by_client_id(client_id)

		d = {'type':'presence', 'client_id':client_id, 'connect':0}

		for c_id in room.client_ids:
			channel.send_message(c_id, simplejson.dumps(d))

class PausedHandler(BaseHandler):
	def post(self):
		client_id = self.rget('client_id')
		room_id = self.rget('room_id')
		paused = bool(int(self.rget('paused')))
		room = get_room_by_room_id(room_id)

		d = {'type':'paused', 'client_id':client_id, 'paused':int(paused)}

		if room.paused != paused:
			room.paused = paused
			room.put()
			for c_id in room.client_ids:
				if paused:
					channel.send_message(c_id, simplejson.dumps(d))
				else:
					channel.send_message(c_id, simplejson.dumps(d))

class SeekHandler(BaseHandler):
	def post(self):
		client_id = self.rget('client_id')
		room_id = self.rget('room_id')
		time = float(self.rget('time'))

		room = get_room_by_room_id(room_id)
		d = {'type':'seek', 'client_id':client_id, 'time':time}

		for c_id in room.client_ids:
			channel.send_message(c_id, simplejson.dumps(d))


def rand_str(n):
	return ''.join(random.choice(string.ascii_lowercase) for x in range(n))

def get_room_by_room_id(room_id):
	q = Rooms.all()
	q.filter('room_id =', room_id)
	return q.get()

def get_room_by_client_id(client_id):
	q = Rooms.all()
	q.filter('client_ids =', client_id)
	return q.get()

app = webapp2.WSGIApplication([('/', MainHandler),
							   ('/upload', UploadHandler),
							   ('/paused', PausedHandler),
							   ('/seek', SeekHandler),
							   ('/_ah/channel/connected/', ConnectHandler),
							   ('/_ah/channel/disconnected/', DisconnectHandler),
							  ], debug=True)
