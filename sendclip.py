#!/usr/bin/env python

import logging
import os
import platform
import signal
import socket
import tempfile
import threading

import tornado.ioloop
import tornado.web
import tornado.httpclient

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk as gtk, Gdk as gdk
from gi.repository import GdkPixbuf
from gi.repository import AppIndicator3 as appindicator

from udpserver import UDPServer
import rc4
import config

APPINDICATOR_ID = 'SendClip'
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
clipboard = gtk.Clipboard.get(gdk.SELECTION_CLIPBOARD)

base_dir = os.path.abspath(os.path.dirname(__file__))

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.write("SendClip server")

class ClipboardHandler(tornado.web.RequestHandler):

    clipboard = clipboard

    def get(self, clipboard_type):
        # self.set_header("Content-Type", "text/encrypted-plain")
        if clipboard_type == 'text':
            text = self.clipboard.wait_for_text()
            if text:
                self.write(rc4.crypt(text, config.password))
        elif clipboard_type == 'image':
            image = self.clipboard.wait_for_image()
            if image is not None:
                self.set_header("Content-Type", "image/png")
                error, buffer = image.save_to_bufferv('png', '', '')
                self.write(rc4.crypt(buffer, config.password))

def make_app():
    return tornado.web.Application([
        (r"/", MainHandler),
        (r"/clipboard/(.*)", ClipboardHandler),
    ])

def receive_udp_data(data, address):
    lines = data.split('\n')
    if len(lines) < 3:
        return
    to_username, hostname, type_text = lines
    if to_username != config.username:
        return
    if hostname == platform.node():
        return
    clipboard_types = type_text.split(',')
    for clipboard_type in clipboard_types:
        if clipboard_type == 'text':
            http_client = tornado.httpclient.HTTPClient()
            response = http_client.fetch('http://%s:%d/clipboard/text' % (address[0], config.port))
            data = response.body
            clipboard.set_text(rc4.crypt(data, config.password), -1)
        elif clipboard_type == 'image':
            http_client = tornado.httpclient.HTTPClient()
            response = http_client.fetch('http://%s:%d/clipboard/image' % (address[0], config.port))
            data = response.body
            temp = tempfile.NamedTemporaryFile(suffix='.png')
            temp.write(rc4.crypt(data, config.password))
            temp.flush()
            image = GdkPixbuf.Pixbuf.new_from_file(temp.name)
            clipboard.set_image(image)
            temp.close()

def server_thread():
    app = make_app()
    app.listen(config.port)
    server = UDPServer('UDPServer', config.port, on_receive=receive_udp_data)
    tornado.ioloop.IOLoop.current().start()

def send_clipboard(source):
    type_list = []
    if clipboard.wait_is_text_available():
        type_list.append('text')
    if clipboard.wait_is_image_available():
        type_list.append('image')
    if not type_list:
        return
    my_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    my_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    msg = '%s\n%s\n%s' % (config.username, platform.node(), ','.join(type_list))
    my_socket.sendto(msg, ('<broadcast>', config.port))
    my_socket.close()

def quit(source):
    gtk.main_quit()


def build_menu():
    menu = gtk.Menu()

    item_send = gtk.MenuItem('Send')
    item_send.connect('activate', send_clipboard)
    menu.append(item_send)

    item_quit = gtk.MenuItem('Quit')
    item_quit.connect('activate', quit)
    menu.append(item_quit)
    
    menu.show_all()
    return menu

def main():
    indicator = appindicator.Indicator.new(APPINDICATOR_ID, os.path.join(base_dir, 'systray.png'), appindicator.IndicatorCategory.SYSTEM_SERVICES)
    indicator.set_status(appindicator.IndicatorStatus.ACTIVE)
    indicator.set_menu(build_menu())
    gtk.main()

if __name__ == "__main__":

    t = threading.Thread(target=server_thread)
    t.daemon = True
    t.start()
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    main()