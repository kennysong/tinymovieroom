import jinja2
import logging
import os
import random
import string
import webapp2

from google.appengine.ext import db
from google.appengine.api import channel

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir), autoescape=True)

CLOUDFRONT_DOMAIN = 'http://ddmm37kppyxwy.cloudfront.net/'

class Rooms(db.Model):
	message = db.StringProperty()
	room_id = db.StringProperty()
	client_ids = db.StringListProperty()

class Movies(db.Model):
	url = db.StringProperty()
	name = db.StringProperty()

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
    		room = Rooms(room_id=room_id, client_ids=[client_id])
    		room.put()
    	else:
			# add user to existing room
			room = get_room_by_room_id(room_id)
			room.client_ids.append(client_id)
			room.put()

        self.render('index.html', {'client_id':client_id, 'room_id':room_id, 'token':token})

class UpdateHandler(BaseHandler):
	def post(self):
		room_id = self.rget('room_id')
		message = self.rget('message')

		# change on db
		room = get_room_by_room_id(room_id)
		room.message = message
		room.put()

		# push to clients
		for client_id in room.client_ids:
			channel.send_message(client_id, message)

class UploadHandler(BaseHandler):
	def get(self):
		self.render('upload.html')

	def post(self):
		filename = self.rget('filename')
		url = CLOUDFRONT_DOMAIN + filename
		name = self.rget('moviename')
		movie = Movies(url=url, name=name)
		movie.put()

		self.write('Uploaded!')

class ConnectHandler(BaseHandler):
	def post(self):
		client_id = self.request.get('from')
		room = get_room_by_client_id(client_id)

		for client_id in room.client_ids:
			channel.send_message(client_id, 'User %s has connected.'%client_id)


class DisconnectHandler(BaseHandler):
	def post(self):
		client_id = self.rget('from')
		room = get_room_by_client_id(client_id)

		for client_id in room.client_ids:
			channel.send_message(client_id, 'User %s has disconnected.'%client_id)

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
							   ('/update', UpdateHandler),
							   ('/_ah/channel/connected/', ConnectHandler),
							   ('/_ah/channel/disconnected/', DisconnectHandler),
							  ], debug=True)
