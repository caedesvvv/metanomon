"""
Animated icon throbber
"""
import gtk

class Throbber(object):
    """
    A throbber controller for a gtkimage.
    """
    def __init__(self, image):
        self._image = image
        self._image.set_from_file('images/Throbber-small.png')
        self._static_image = self._image.get_pixbuf()
        self._animation = gtk.gdk.PixbufAnimation('images/Throbber-small.gif')

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


