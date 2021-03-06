#!/usr/bin/env python
"""
A dokuwiki browser and editor.
"""
import user
import os
import gtk
import pango
import time
import traceback

from kiwi.ui.delegates import GladeDelegate
from kiwi.ui.objectlist import ObjectList, Column, ObjectTree
import kiwi.ui.proxywidget # XXX needed for pixbuf

from kiwi.environ import environ

from xmlrpclib import ServerProxy
from urllib import urlencode
    
import gtkmozembed
import gtksourceview
#import gtkhtml2
#import simplebrowser

from buffer import DokuwikiBuffer
from throbber import Throbber

from twisted.internet import gtk2reactor
gtk2reactor.install()
from twisted.internet import threads, reactor

from metamodel import SubscribableModel as Model
from metamodel import Property, Password
from metamodel.datasources.filesource import FileDataSource

dialog_buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT,
                  gtk.STOCK_OK, gtk.RESPONSE_ACCEPT)

class ModalDialog(gtk.Dialog):
    """
    A simple modal dialog to ask confirmation.
    """
    def __init__(self, title):
        gtk.Dialog.__init__(self, title = title,
                            flags = gtk.DIALOG_MODAL, 
                            buttons = dialog_buttons)

class Dokuwiki(Model):
    url = Property(str, '')
    user = Property(str, '')
    password = Password('')
    current = Property(str, '')

class WikiList(Model):
    builds = ['Dokuwiki']

nomondir = os.path.join(user.home,'.nomon')
if not os.path.exists(nomondir):
    os.mkdir(nomondir)
cfg = FileDataSource(file=os.path.join(nomondir,'config.caf'))
cfg.save()

page_icon = gtk.gdk.pixbuf_new_from_file("/usr/share/icons/gnome/16x16/mimetypes/ascii.png")
section_icon = gtk.gdk.pixbuf_new_from_file("/usr/share/icons/gnome/16x16/places/folder.png")

# wrappers for kiwi treeview widgets
class Section(object):
    def __init__(self, name, id=None):
        self.name = name
        self.icon = section_icon
        if id:
            self.id = id
        else:
            self.id = name

class DictWrapper(object):
    def __init__(self, obj, id=None):
        self._obj = obj
        self.icon = page_icon
        if id:
            self.name = id
    def __getattr__(self, name):
        try:
            return self._obj[name]
        except:
            raise AttributeError

# funtion to setup some simple style tags
def setup_tags(table):
    for i, tag in enumerate(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        tag_h1 = gtk.TextTag(tag)
        tag_h1.set_property('size-points', 20-i*2)
        tag_h1.set_property('weight', 700)
        table.add(tag_h1)

    tag_bold = gtk.TextTag('bold')
    tag_bold.set_property('weight', 700)
    table.add(tag_bold)

    tag_italic = gtk.TextTag('italic')
    tag_italic.set_property('style', pango.STYLE_ITALIC)
    table.add(tag_italic)


# setup the tag table
#table = gtk.TextTagTable()
table = gtksourceview.SourceTagTable()
setup_tags(table)


# main application classes
class DokuwikiView(GladeDelegate):
    """
    A dokuwiki editor window
    """
    def __init__(self):
        GladeDelegate.__init__(self, gladefile="pydoku",
                          delete_handler=self.quit_if_last)
        self._icons = {}
        self.throbber_icon = Throbber(self.view.throbber)
        self.setup_wikitree()
        self.setup_wikislist()
        self.setup_attachments()
        self.setup_lastchanges()
        self.setup_side()
        self.setup_sourceview()
        self.setup_htmlview()
        self.page_edit = self.view.notebook1.get_nth_page(0)
        self.page_view = self.view.notebook1.get_nth_page(1)
        self.page_attach = self.view.notebook1.get_nth_page(2)
        self.show_all()
        if len(cfg.getChildren()):
            wiki = cfg.getChildren()[0]
            self.connect(wiki.url, wiki.user, wiki.password)
            self.wiki = wiki
            if wiki.current:
                self.load_page(wiki.current)

    # quit override to work with twisted
    def quit_if_last(self, *args):
        self.htmlview.destroy() # for some reason has to be deleted explicitly
        windows = [toplevel
               for toplevel in gtk.window_list_toplevels()
                   if toplevel.get_property('type') == gtk.WINDOW_TOPLEVEL]
        if len(windows) == 1:
            reactor.stop()

    # general interface functions
    def post(self, text):
        id = self.view.statusbar.get_context_id("zap")
        self.view.statusbar.push(id, text)

    # setup functions
    def setup_wikislist(self):
        columns = [Column('url',format_func=self.get_favicon,data_type=gtk.gdk.Pixbuf,icon_size=gtk.ICON_SIZE_SMALL_TOOLBAR)]
        self.wikislist = ObjectList(columns)
        columns.append(Column('url', title='Wiki', column='url'))
        self.wikislist.set_columns(columns)
        self.view.vbox2.pack_start(self.wikislist)
        self.view.vbox2.reorder_child(self.wikislist, 0)
        self.wikislist.add_list(cfg.getChildren())
        self.wikislist.connect("selection-changed", self.wiki_selected)
        threads.deferToThread(self.download_favicons, cfg)

    def download_favicons(self, cfg):
        for wiki in cfg.getChildren():
            self.download_favicon(wiki)

    def download_favicon(self, wiki):
        import urllib
        icon_url = wiki.url+"/lib/tpl/sidebar/images/favicon.ico"
        filename, headers = urllib.urlretrieve(icon_url, "/tmp/ico.ico")
        if headers["Content-Type"] == 'image/x-icon':
            self.add_favicon(wiki, filename)

    def get_favicon(self, wiki_url):
        return self._icons.get(wiki_url, page_icon)

    def add_favicon(self, wiki, filename):
        pixbuf = gtk.gdk.pixbuf_new_from_file(filename)
        pixbuf = pixbuf.scale_simple(16,16,gtk.gdk.INTERP_BILINEAR)
        self._icons[wiki.url] = pixbuf
        self.objectlist.refresh()

    def setup_side(self):
        columns = ['sum', 'user', 'type', 'version', 'ip']
        columns = [Column(s) for s in columns]
        self.versionlist = ObjectList(columns)

        self.view.side_vbox.pack_start(gtk.Label('Version Log:'), False, False)
        self.view.side_vbox.add(self.versionlist)
        self.versionlist.connect("selection-changed", self.version_selected)

        self.view.side_vbox.pack_start(gtk.Label('BackLinks:'), False, False)
        self.backlinks = ObjectList([Column('name')])
        self.backlinks.connect("selection-changed", self.change_selected)
        self.view.side_vbox.add(self.backlinks)

    def setup_attachments(self):
        columns = ['id', 'size', 'lastModified', 'writable', 'isimg', 'perms']
        columns = [Column(s) for s in columns]
        self.attachmentlist = ObjectList(columns)

        self.view.attachments_vbox.add(self.attachmentlist)

    def setup_lastchanges(self):
        columns = ['name', 'author', 'lastModified', 'perms', 'version', 'size']
        columns = [Column(s) for s in columns]
        columns.append(Column('lastModified', sorted=True, order=gtk.SORT_DESCENDING))
        self.lastchangeslist = ObjectList(columns)
        self.lastchangeslist.connect("selection-changed", self.change_selected)

        self.view.side_vbox.add(self.lastchangeslist)


    def setup_wikitree(self):
        columns = ['id', 'lastModified', 'perms', 'size']
        columns = [Column(s) for s in columns]
        columns.insert(0, Column('icon', title='name', data_type=gtk.gdk.Pixbuf))
        self.objectlist = ObjectTree(columns)
        columns.insert(1, Column('name', column='icon'))
        self.objectlist.set_columns(columns)

        self.objectlist.connect("selection-changed", self.selected)
        self.view.vbox2.add(self.objectlist)

    def html_realized(self, widget):
        if self.wiki and self.wiki.current:
            self.get_htmlview(self.wiki.current)

    def setup_htmlview(self):
        self.htmlview = gtkmozembed.MozEmbed()
        self.view.html_scrolledwindow.add_with_viewport(self.htmlview)
        self.htmlview.connect('realize', self.html_realized)
        #self.htmlview.set_size_request(800,600)
        #self.htmlview.realize()
        #self.view.html_scrolledwindow.show_all()
        #self.htmlview.show()

    def setup_sourceview(self):
        self.buffer = DokuwikiBuffer(table)
        self.editor = gtksourceview.SourceView(self.buffer)
        #self.editor.set_show_line_numbers(True)
        accel_group = gtk.AccelGroup()
        self.get_toplevel().add_accel_group(accel_group)
        self.editor.add_accelerator("paste-clipboard", accel_group, ord('v'), gtk.gdk.CONTROL_MASK, 0)
        self.editor.add_accelerator("copy-clipboard", accel_group, ord('c'), gtk.gdk.CONTROL_MASK, 0)
        self.editor.add_accelerator("cut-clipboard", accel_group, ord('x'), gtk.gdk.CONTROL_MASK, 0)
        #self.editor = gtk.TextView(self.buffer)
        self.editor.set_left_margin(5)
        self.editor.set_right_margin(5)
        self.editor.set_wrap_mode(gtk.WRAP_WORD_CHAR)
        self.view.scrolledwindow1.add(self.editor)

        lm = gtksourceview.SourceLanguagesManager()
        langs = lm.get_available_languages()
        lang_diffs = filter(lambda s: s.get_name() == 'Diff', langs)
        if lang_diffs:
            self.buffer.set_language(lang_diffs[0])

    # dokuwiki operations
    def _getVersion(self):
        return self._rpc.dokuwiki.getVersion()

    def get_version(self):
        return threads.deferToThread(self._getVersion)

    def get_pagelist(self):
        print "getpagelist1"
        pages = self._rpc.wiki.getAllPages()
        self._sections = {}
        self.objectlist.clear()
        print "getpagelist1.5"
        print "PAGES",pages
        for page in pages:
            self.add_page(page)
        print "getpagelist2"
        self.view.new_page.set_sensitive(True)
        self.view.delete_page.set_sensitive(True)
        if self.wiki.current:
            self.set_selection(self.wiki.current)
        print "getpagelist3"
        # XXX
        self.get_recent_changes()
        print "getpagelist2"

    def _getRecentChanges(self):
        return self._rpc.wiki.getRecentChanges(int(time.time()-(60*60*24*7*12)))

    def _gotRecentChanges(self, changes):
        changes = [DictWrapper(s) for s in changes]
        self.lastchangeslist.add_list(changes)

    def get_recent_changes(self):
        self.callDeferred(self._getRecentChanges, self._gotRecentChanges)

    def get_attachments(self, ns):
        attachments = self._rpc.wiki.getAttachments(ns, {})
        attachments = [DictWrapper(s) for s in attachments]
        self.attachmentlist.add_list(attachments)

    def _getBackLinks(self, pagename):
        return self._rpc.wiki.getBackLinks(pagename)

    def _gotBackLinks(self, backlinks):
        backlinks = [Section(s) for s in backlinks]
        self.backlinks.add_list(backlinks)

    def get_backlinks(self, pagename):
        self.callDeferred(self._getBackLinks, self._gotBackLinks, pagename)

    def _getVersions(self, pagename):
        return self._rpc.wiki.getPageVersions(pagename, 0)

    def _gotVersions(self, versionlist):
        versionlist = [DictWrapper(s) for s in versionlist]
        self.versionlist.add_list(versionlist)

    def get_versions(self, pagename):
        self.callDeferred(self._getVersions, self._gotVersions, pagename)

    def _getHtmlData(self, pagename):
        text = self._rpc.wiki.getPageHTML(pagename)
        return text

    def _gotHtmlData(self, text):
        self.throbber_icon.stop()
        if not self.htmlview.window:
            return
        text = """<head><meta http-equiv="Content-Type" content="text/html;  charset=utf-8" />
        </head><body>"""+text+"</body>"
        self.htmlview.render_data(text, len(text), self.wiki.url, 'text/html')
        self.htmlview.realize()
        self.htmlview.show()

    def get_htmlview(self, pagename):
        self.throbber_icon.start()
        self.callDeferred(self._getHtmlData, self._gotHtmlData, pagename)
        #d.addErrback(self.someError)

        # XXX following is for gtkhtml (not used)
        #self.document.clear()
        #self.document.open_stream('text/html')
        #self.document.write_stream(text)
        #self.document.close_stream()

    def callDeferred(self, get_func, got_func, *args):
        d = threads.deferToThread(get_func, *args)
        d.addCallback(got_func)

    def _getEditText(self, pagename):
        return self._rpc.wiki.getPage(pagename)

    def _gotEditText(self, text):
        self.throbber_icon.stop()
        self.buffer.set_highlight(False)
        self.editor.set_editable(True)
        self.buffer.add_text(text)

    def _getDiffText(self, pagename, version, idx):
        return self._rpc.wiki.getPageVersion(pagename, version), idx

    def _gotDiffText(self, data):
        import difflib
        import StringIO
        text, idx = data
        self.textstack[idx] = text
        if not None in self.textstack:
            fromlines = self.textstack[0].split("\n")
            tolines = self.textstack[1].split("\n")
            diff_text = difflib.unified_diff(fromlines, tolines, "a", "b",
                                        self.versions[0],
                                        self.versions[1])
            self.throbber_icon.stop()
            self.buffer.clear()
            str_buffer = StringIO.StringIO()
            for line in diff_text:
                str_buffer.write(line+'\n')
            str_buffer.seek(0)
            self.buffer.add_text(str_buffer.read())
            self.buffer.set_highlight(True)
            self.editor.set_editable(False)

    def get_difftext(self, pagename, version, prev_version):
        self.throbber_icon.start()
        self.textstack = [None, None]
        self.versions = [version, prev_version]
        self.callDeferred(self._getDiffText, self._gotDiffText,
                                  pagename, prev_version, 0)
        self.callDeferred(self._getDiffText, self._gotDiffText,
                                  pagename, version, 1)


    def get_edittext(self, pagename):
        self.throbber_icon.start()
        self.callDeferred(self._getEditText, self._gotEditText, pagename)

    def put_page(self, text, summary, minor):
        pars = {}
        if summary:
            pars['sum'] = summary
        if minor:
            pars['minor'] = minor
        d = threads.deferToThread(self._rpc.wiki.putPage, self.wiki.current, text, pars)
        return d

    # put a page into the page tree
    def add_page(self, page):
      print page
      try:
        name = page["id"]
        path = name.split(":")
        prev = None
        for i, pathm in enumerate(path):
            if i == len(path)-1: # a page
                new = DictWrapper(page, pathm)
                self._sections[name] = new
                self.objectlist.append(prev, new, False)
            else: # a namespace
                part_path = ":".join(path[:i+1])
                if not part_path in self._sections:
                    new = Section(pathm, part_path)
                    self._sections[part_path] = new
                    self.objectlist.append(prev, new, False)
                else:
                    new = self._sections[part_path]
            prev = new
      except:
        traceback.print_exc()

    def expand_to(self, pagename):
        path = pagename.split(":")
        for i, pathm in enumerate(path):
            if not i == len(path)-1:
                section = self._sections[":".join(path[:i+1])]
                self.view.objectlist.expand(section)

    def set_selection(self, pagename):
        obj = self._sections[pagename]
        self.expand_to(pagename)
        self.view.objectlist.select(obj, True)
        #self.selected(widget, obj)

    # page selected callback
    def wiki_selected(self, widget, wiki):
        self.connect(wiki.url, wiki.user, wiki.password)
        self.objectlist.clear()
        self.versionlist.clear()
        self.lastchangeslist.clear()
        self.backlinks.clear()
        self._sections = {}
        self.wiki = wiki
        self.buffer.clear()
        if wiki.current:
            self.load_page(wiki.current)

    def version_selected(self, widget, object):
        # yes, the previous item is the next in the widget
        if object == None:
            return
        previous = widget.get_next(object)
        if not previous:
            return
        prev_version = previous.version
        self.get_difftext(self.wiki.current, int(object.version),
                          int(prev_version))

    def change_selected(self, widget, object):
        if not object:
            return
        self.set_selection(object.name)

    def selected(self, widget, object):
        if not object:
            return
        if isinstance(object, Section):
            self.get_attachments(object.id)
        if not isinstance(object, DictWrapper):
            return
        self.wiki.current = object.id
        cfg.save()
        self.load_page(object.id)

    def load_page(self, pagename):
        self.get_edittext(pagename)
        self.get_htmlview(pagename)
        self.get_backlinks(pagename)
        self.get_versions(pagename)

    # kiwi interface callbacks
    def on_view_edit__toggled(self, widget):
        if widget.get_active():
            self.notebook1.insert_page(self.page_edit, gtk.Label('edit'), 0)
        else:
            self.notebook1.remove_page(self.notebook1.page_num(self.page_edit))

    def on_view_view__toggled(self, widget):
        if widget.get_active():
            self.notebook1.insert_page(self.page_view, gtk.Label('view'), 1)
        else:
            self.notebook1.remove_page(self.notebook1.page_num(self.page_view))

    def on_view_attachments__toggled(self, widget):
        if widget.get_active():
            self.notebook1.insert_page(self.page_attach, gtk.Label('attach'))
        else:
            self.notebook1.remove_page(self.notebook1.page_num(self.page_attach))

    def on_view_extra__toggled(self, widget):
        if widget.get_active():
            self.backlinks.show()
            self.versionlist.show()
            self.view.hpaned2.set_position(self._prevpos)
        else:
            self.backlinks.hide()
            self.versionlist.hide()
            self._prevpos = self.view.hpaned2.get_position()
            self.view.hpaned2.set_position(self.view.hpaned2.allocation.width)

    def on_button_add__clicked(self, *args):
        dialog = ModalDialog("User Details")
        # prepare
        widgets = {}
        items = ["url","user", "password"]
        for i, item in enumerate(items):
            widgets[item] = gtk.Entry()
            if i == 2:
                widgets[item].set_visibility(False)
            hbox = gtk.HBox()
            hbox.pack_start(gtk.Label(item+': '))
            hbox.add(widgets[item])
            dialog.vbox.add(hbox)
        dialog.show_all()
        # run
        response = dialog.run()
        user = widgets['user'].get_text()
        password = widgets['password'].get_text()
        url = widgets['url'].get_text()
        dialog.destroy()
        if not response == gtk.RESPONSE_ACCEPT:
            return

        self.wiki = cfg.new(Dokuwiki, 
                    url=url,
                    user=user,
                    password=password)

        cfg.addChild(self.wiki)
        cfg.save()
        self.connect(url, user, password)

    def get_full_url(self, url, user, password):
      try:
        if user and password:
            split_url = url.split('://')
            proto = split_url[0]
            base_url = split_url[1]
            return proto + '://' + user + ':' + password + '@' + base_url
        return url
      except:
        traceback.print_exc()

    def connect(self, url, user, password):
        # following commented line is for gtkhtml (not used)
        #simplebrowser.currentUrl = self.view.url.get_text()
        # handle response
        self.post("Connecting to " + url)
        params = urlencode({'u':user, 'p':password})
        print self.get_full_url(url, user, password)
        fullurl = self.get_full_url(url, user, password) + "/lib/exe/xmlrpc.php?"+ params
        print "serverproxy1"
        self._rpc = ServerProxy(fullurl)
        print "serverproxy1"
        d = self.get_version()
        d.addCallback(self.connected)
        d.addErrback(self.error_connecting)

    def error_connecting(self, failure):
        self.post("Error connecting to " + self.wiki.url)
        print failure.getErrorMessage()

    def connected(self, version):
        print "connected1"
        self.view.version.set_text(version)
        print "connected1.5"
        self.get_pagelist()
        print "connected2"
        self.post("Connected")

    def on_delete_page__clicked(self, *args):
        dialog = ModalDialog("Are you sure?")
        response = dialog.run()
        if response == gtk.RESPONSE_ACCEPT:
            value = self._sections[self.wiki.current]
            sel = self.objectlist.remove(value)
            self._rpc.wiki.putPage(self.wiki.current, "", {})
            self.wiki.current = ''
            cfg.save()
        dialog.destroy()

    def on_new_page__clicked(self, *args):
        dialog = ModalDialog("Name for the new page")
        text_w = gtk.Entry()
        text_w.show()
        response = []
        dialog.vbox.add(text_w)
        response = dialog.run()
        if response == gtk.RESPONSE_ACCEPT:
            text = text_w.get_text()
            if text:
                self.wiki.current = text
                cfg.save()
                self.buffer.clear()
        dialog.destroy()

    def on_button_h1__clicked(self, *args):
        self.buffer.set_style('h1')

    def on_button_h2__clicked(self, *args):
        self.buffer.set_style('h2')

    def on_button_h3__clicked(self, *args):
        self.buffer.set_style('h3')

    def on_button_h4__clicked(self, *args):
        self.buffer.set_style('h4')

    def on_button_h5__clicked(self, *args):
        self.buffer.set_style('h5')

    def on_button_h6__clicked(self, *args):
        self.buffer.set_style('h6')

    def on_button_bold__clicked(self, *args):
        self.buffer.set_style('bold')

    def on_button_italic__clicked(self, *args):
        self.buffer.set_style('italic')

    def on_button_clear_style__clicked(self, *args):
        self.buffer.clear_style()

    def _pagePut(self, *args):
        if not self.wiki.current in self._sections:
            self.add_page({"id":self.wiki.current})
        self.get_htmlview(self.wiki.current)
        self.get_versions(self.wiki.current)
        self.post("Saved")

    def on_button_save__clicked(self, *args):
        """ Save button callback """
        dialog = ModalDialog("Commit message")
        entry = gtk.Entry()
        minor = gtk.CheckButton("Minor")
        dialog.vbox.add(gtk.Label("Your attention to detail\nis greatly appreciated"))
        dialog.vbox.add(entry)
        dialog.vbox.add(minor)
        dialog.show_all()
        response = dialog.run()
        if response == gtk.RESPONSE_ACCEPT:
            self.post("Saving...")
            text = self.buffer.process_text()
            self.throbber_icon.start()
            d = self.put_page(text, entry.get_text(), minor.get_active())
            d.addCallback(self._pagePut)
        dialog.destroy()

    # unused stuff
    def request_url(self, document, url, stream):
        f = simplebrowser.open_url(url)
        stream.write(f.read())

    def setup_htmlview_gtkhtml(self):
        # XXX not used now
        self.document = gtkhtml2.Document()
        self.document.connect('request_url', self.request_url)
        self.htmlview = gtkhtml2.View()
        self.htmlview.set_document(self.document)


if __name__ == "__main__":
    app = DokuwikiView()
    app.show()
    reactor.run()

