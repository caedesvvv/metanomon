"""
Animated icon throbber
"""
import gtk
from kiwi.environ import environ

class Throbber(object):
    """
    A throbber controller for a gtkimage.
    """
    def __init__(self, image):
        self._image = image
        path = environ.find_resource('images', 'Throbber-small.png')
        self._image.set_from_file(path)
        self._static_image = self._image.get_pixbuf()
        path = environ.find_resource('images', 'Throbber-small.gif')
        self._animation = gtk.gdk.PixbufAnimation(path)

    def start(self):
        """
        Start throbbling
        """
        self._image.set_from_animation(self._animation)

    def stop(self):
        """
        Stop throbbling
        """
        self._image.set_from_pixbuf(self._static_image)


