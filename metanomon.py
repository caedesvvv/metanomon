#!/usr/bin/env python
import user
import os
import gtk
import pango

from kiwi.ui.gadgets import quit_if_last
from kiwi.ui.delegates import GladeDelegate
from kiwi.ui.objectlist import ObjectList, Column, ObjectTree

from xmlrpclib import ServerProxy
from urllib import urlencode
    
import gtkmozembed
#import gtksourceview2 as gtksourceview
#import gtkhtml2
#import simplebrowser

from buffer import DokuwikiBuffer

from twisted.internet import gtk2reactor
gtk2reactor.install()
from twisted.internet import threads,reactor


from metamodel import SubscribableModel as Model
from metamodel import Property, Password
from metamodel.datasources.filesource import FileDataSource

dialog_buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT,
                  gtk.STOCK_OK, gtk.RESPONSE_ACCEPT)

class ModalDialog(gtk.Dialog):
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

# wrappers for kiwi treeview widgets
class Section(object):
    def __init__(self, name):
        self.name = name

class DictWrapper(object):
    def __init__(self, obj, id=None):
        self._obj = obj
        if id:
            self.name = id
    def __getattr__(self, name):
        try:
            return self._obj[name]
        except:
            raise AttributeError

# funtion to setup some simple style tags
def setup_tags(table):
    for i,tag in enumerate(['h1','h2','h3','h4','h5','h6']):
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
table = gtk.TextTagTable()
setup_tags(table)


# main application classes
class DokuwikiView(GladeDelegate):
    """
    A dokuwiki editor window
    """
    def __init__(self):
        GladeDelegate.__init__(self, gladefile="pydoku",
                          delete_handler=self.quit_if_last)
        self.setup_wikitree()
        self.setup_attachments()
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

    # general interface functions
    def post(self, text):
        id = self.view.statusbar.get_context_id("zap")
        self.view.statusbar.push(id, text)

    # setup functions
    def setup_side(self):
        columns = ['user', 'sum', 'type', 'version', 'ip']
        columns = [Column(s) for s in columns]
        self.versionlist = ObjectList(columns)

        self.view.side_vbox.pack_start(gtk.Label('Version Log:'), False, False)
        self.view.side_vbox.add(self.versionlist)

        self.view.side_vbox.pack_start(gtk.Label('BackLinks:'), False, False)
        self.backlinks = ObjectList([Column('name')])
        self.view.side_vbox.add(self.backlinks)

    def setup_attachments(self):
        columns = ['id', 'size', 'lastModified', 'writable', 'isimg', 'perms']
        columns = [Column(s) for s in columns]
        self.attachmentlist = ObjectList(columns)

        self.view.attachments_vbox.add(self.attachmentlist)

    def setup_wikitree(self):
        columns = ['name', 'id', 'lastModified', 'perms', 'size']
        columns = [Column(s) for s in columns]
        self.objectlist = ObjectTree(columns)

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
        self.editor = gtk.TextView(self.buffer)
        self.editor.set_left_margin(5)
        self.editor.set_right_margin(5)
        self.editor.set_wrap_mode(gtk.WRAP_WORD_CHAR)
        self.view.scrolledwindow1.add(self.editor)

    # dokuwiki operations
    def get_version(self):
        version = self._rpc.dokuwiki.getVersion()
        self.view.version.set_text(version)

    def get_pagelist(self):
        pages = self._rpc.wiki.getAllPages()
        self._sections = {}
        self.objectlist.clear()
        for page in pages:
            self.add_page(page)
        self.view.new_page.set_sensitive(True)
        self.view.delete_page.set_sensitive(True)

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
        self.callDeferred(pagename, self._getBackLinks, self._gotBackLinks)

    def _getVersions(self, pagename):
        return self._rpc.wiki.getPageVersions(pagename, 0)

    def _gotVersions(self, versionlist):
        versionlist = [DictWrapper(s) for s in versionlist]
        self.versionlist.add_list(versionlist)

    def get_versions(self, pagename):
        self.callDeferred(pagename, self._getVersions, self._gotVersions)

    def _getHtmlData(self, pagename):
        text = self._rpc.wiki.getPageHTML(pagename)
        return text

    def _gotHtmlData(self, text):
        if not self.htmlview.window: return
        self.htmlview.render_data(text, len(text), self.url.get_text(), 'text/html')
        self.htmlview.realize()
        self.htmlview.show()

    def callDeferred(self, pagename, get_func, got_func):
        d = threads.deferToThread(get_func, pagename)
        d.addCallback(got_func)

    def get_htmlview(self, pagename):
        self.callDeferred(pagename, self._getHtmlData, self._gotHtmlData)
        #d.addErrback(self.someError)

        # XXX following is for gtkhtml (not used)
        #self.document.clear()
        #self.document.open_stream('text/html')
        #self.document.write_stream(text)
        #self.document.close_stream()

    def _getEditText(self, pagename):
        return self._rpc.wiki.getPage(pagename)

    def _gotEditText(self, text):
        self.buffer.add_text(text)

    def get_edittext(self, pagename):
        self.callDeferred(pagename, self._getEditText, self._gotEditText)

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
        name = page["id"]
        path = name.split(":")
        prev = None
        for i,pathm in enumerate(path):
            if i == len(path)-1: # a page
                new = DictWrapper(page, pathm)
                self._sections[name] = new
                self.objectlist.append(prev, new, False)
            else: # a namespace
                part_path = ":".join(path[:i+1])
                if not part_path in self._sections:
                    new = Section(part_path)
                    self._sections[part_path] = new
                    self.objectlist.append(prev, new, False)
                else:
                    new = self._sections[part_path]
            prev = new

    # page selected callback
    def selected(self, widget, object):
        if not object: return
        if isinstance(object, Section):
            self.get_attachments(object.name)
        if not isinstance(object, DictWrapper): return
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

    def on_button_list__clicked(self, *args):
        self.post("Connecting...")
        dialog = ModalDialog("User Details")
        # prepare
        widgets = {}
        items = ["user", "password"]
        for i,item in enumerate(items):
            widgets[item] = gtk.Entry()
            if i == 1:
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
        dialog.destroy()
        if not response == gtk.RESPONSE_ACCEPT: return
        url = self.view.url.get_text()

        self.wiki = cfg.new(Dokuwiki, 
                    url=url,
                    user=user,
                    password=password)

        cfg.purgeChildren()
        cfg.addChild(self.wiki)
        cfg.save()
        self.connect(url, user, password)

    def connect(self, url, user, password):
        # following commented line is for gtkhtml (not used)
        #simplebrowser.currentUrl = self.view.url.get_text()
        # handle response
        params = urlencode({'u':user,'p':password})
        fullurl = self.view.url.get_text() + "/lib/exe/xmlrpc.php?"+ params
        self._rpc = ServerProxy(fullurl)
        self.get_version()
        self.get_pagelist()
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


    def setup_sourceview_gtksourceview(self):
        # XXX not used now
        self.buffer = gtksourceview.Buffer(table)
        self.editor = gtksourceview.View(self.buffer)
        if True:
            self.editor.set_show_line_numbers(True)
            lm = gtksourceview.LanguageManager()
            self.editor.set_indent_on_tab(True)
            self.editor.set_indent_width(4)
            self.editor.set_property("auto-indent", True)
            self.editor.set_property("highlight-current-line", True)
            self.editor.set_insert_spaces_instead_of_tabs(True)
            lang = lm.get_language("python")
            self.buffer.set_language(lang)
            self.buffer.set_highlight_syntax(True)


if __name__ == "__main__":
    app = DokuwikiView()
    app.show()
    reactor.run()

