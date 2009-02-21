#!/usr/bin/env python
import gtk
import pango

from kiwi.ui.gadgets import quit_if_last
from kiwi.ui.delegates import GladeDelegate
from kiwi.ui.objectlist import ObjectList, Column, ObjectTree

from xmlrpclib import ServerProxy
from urllib import urlencode
    
#import gtksourceview2 as gtksourceview
import gtkmozembed
#import gtkhtml2
#import simplebrowser

dialog_buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT,
                  gtk.STOCK_OK, gtk.RESPONSE_ACCEPT)

class Section(object):
    def __init__(self, name):
        self.name = name

class Wrapper(object):
    def __init__(self, obj, id=None):
        self._obj = obj
        if id:
            self.name = id
    def __getattr__(self, name):
        try:
            return self._obj[name]
        except:
            raise AttributeError

# setup some style tags
table = gtk.TextTagTable()
for i,tag in enumerate(['h1','h2','h3','h4','h5','h6']):
    tag_h1 = gtk.TextTag(tag)
    tag_h1.set_property('size-points', 20-i*2)
    tag_h1.set_property('weight', 700)
    #tag_h1.set_property('foreground', 'pink')
    tag_h1.set_priority(10)
    table.add(tag_h1)

tag_inv = gtk.TextTag('invisible')
tag_inv.set_property('invisible', True)

tag_bold = gtk.TextTag('bold')
tag_bold.set_property('weight', 700)
table.add(tag_bold)

tag_bold = gtk.TextTag('italic')
tag_bold.set_property('style', pango.STYLE_ITALIC)
table.add(tag_bold)


class DokuwikiView(GladeDelegate):
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

        self.attachmentlist.show()
        #self.attachmentlist.connect("selection-changed", self.attaselected)
        self.view.attachments_vbox.add(self.attachmentlist)

    def setup_wikitree(self):
        columns = ['name', 'id', 'lastModified', 'perms', 'size']
        columns = [Column(s) for s in columns]
        self.objectlist = ObjectTree(columns)

        self.objectlist.show()
        self.objectlist.connect("selection-changed", self.selected)
        self.view.vbox2.add(self.objectlist)

    def post(self, text):
        id = self.view.statusbar.get_context_id("zap")
        self.view.statusbar.push(id, text)

    def request_url(self, document, url, stream):
        f = simplebrowser.open_url(url)
        stream.write(f.read())

    def setup_htmlview_gtkhtml(self):
        # XXX not used now
        self.document = gtkhtml2.Document()
        self.document.connect('request_url', self.request_url)
        self.htmlview = gtkhtml2.View()
        self.htmlview.set_document(self.document)

    def setup_htmlview(self):
        self.htmlview = gtkmozembed.MozEmbed()
        self.view.html_scrolledwindow.add(self.htmlview)
        self.htmlview.realize()
        self.htmlview.show()

    def setup_sourceview(self):
        # sourceview
        self.buffer = gtk.TextBuffer(table)
        self.stdin = gtk.TextView(self.buffer)
        self.stdin.set_left_margin(5)
        self.stdin.set_right_margin(5)
        self.stdin.set_wrap_mode(gtk.WRAP_WORD_CHAR)
        self.view.scrolledwindow1.add(self.stdin)
        self.stdin.show()
        self.show_all()

    def setup_sourceview_gtksourceview(self):
        # XXX not used now
        self.buffer = gtksourceview.Buffer(table)
        self.stdin = gtksourceview.View(self.buffer)
        if True:
            self.stdin.set_show_line_numbers(True)
            lm = gtksourceview.LanguageManager()
            self.stdin.set_indent_on_tab(True)
            self.stdin.set_indent_width(4)
            self.stdin.set_property("auto-indent", True)
            self.stdin.set_property("highlight-current-line", True)
            self.stdin.set_insert_spaces_instead_of_tabs(True)
            lang = lm.get_language("python")
            self.buffer.set_language(lang)
            self.buffer.set_highlight_syntax(True)

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
        dialog = gtk.Dialog(title = "User Details",
                            flags = gtk.DIALOG_MODAL, 
                            buttons = dialog_buttons)
        text_user = gtk.Entry()
        text_pwd = gtk.Entry()
        text_pwd.set_visibility(False)
        hbox_user = gtk.HBox()
        hbox_pwd = gtk.HBox()
        hbox_user.pack_start(gtk.Label('user: '))
        hbox_pwd.pack_start(gtk.Label('password: '))
        hbox_user.add(text_user)
        hbox_pwd.add(text_pwd)
        dialog.vbox.add(hbox_user)
        dialog.vbox.add(hbox_pwd)
        dialog.show_all()
        response = dialog.run()
        user = text_user.get_text()
        password = text_pwd.get_text()
        dialog.destroy()
        if not response == gtk.RESPONSE_ACCEPT: return
        # following commented line is for gtkhtml (not used)
        #simplebrowser.currentUrl = self.view.url.get_text()
        params = urlencode({'u':user,'p':password})
        fullurl = self.view.url.get_text() + "/lib/exe/xmlrpc.php?"+ params
        self._rpc = ServerProxy(fullurl)
        version = self._rpc.dokuwiki.getVersion()
        self.view.version.set_text(version)
        pages = self._rpc.wiki.getAllPages()
        self._sections = {}
        self.objectlist.clear()
        for page in pages:
            self.add_page(page)
        self.view.new_page.set_sensitive(True)
        self.view.delete_page.set_sensitive(True)
        self.post("Page List Retrieved")

    def add_page(self, page):
        name = page["id"]
        path = name.split(":")
        prev = None
        for i,pathm in enumerate(path):
            # a page
            if i == len(path)-1:
                new = Wrapper(page, pathm)
                self._sections[name] = new
                self.objectlist.append(prev, new, False)
            # header
            else:
                part_path = ":".join(path[:i+1])
                if not part_path in self._sections:
                    self._sections[part_path] = Section(part_path)
                    new = self._sections[part_path]
                    self.objectlist.append(prev, new, False)
                else:
                    new = self._sections[part_path]
            prev = new
       

    def on_delete_page__clicked(self, *args):
        dialog = gtk.Dialog(title = "Are you sure?",
                            flags = gtk.DIALOG_MODAL, 
                            buttons = dialog_buttons)
        response = dialog.run()
        if response == gtk.RESPONSE_ACCEPT:
            value = self._sections[self.current]
            sel = self.objectlist.remove(value)
            self._rpc.wiki.putPage(self.current, "", {})
            self.current = None
        dialog.destroy()

    def on_new_page__clicked(self, *args):
        dialog = gtk.Dialog(title = "Name for the new page",
                            flags = gtk.DIALOG_MODAL, 
                            buttons = dialog_buttons)
        text_w = gtk.Entry()
        text_w.show()
        response = []
        dialog.vbox.add(text_w)
        response = dialog.run()
        if response == gtk.RESPONSE_ACCEPT:
            text = text_w.get_text()
            if text:
                self.current = text
        dialog.destroy()

    def process_text(self):
        buffer = self.stdin.get_buffer()
        mapping = {'h1': '======',
                   'h2': '=====',
                   'h3': '====',
                   'h4': '===',
                   'h5': '==',
                   'h6': '=',
                   'bold': '**',
                   'italic': '//',
                   }
        result_text = ""
        text =  buffer.get_property("text")
        for idx, letter in enumerate(text):
            iter = buffer.get_iter_at_offset(idx)
            if iter.begins_tag():
                tags = iter.get_toggled_tags(True)
                for tag in tags:
                    name = tag.get_property('name')
                    if name[0] == "h":
                        result_text += mapping.get(name, '') + ' '
                    else:
                        result_text += mapping.get(name, '')
            if iter.ends_tag():
                tags = iter.get_toggled_tags(False)
                for tag in tags:
                    name = tag.get_property('name')
                    if name[0] == "h":
                        result_text += ' ' + mapping.get(name, '')
                    else:
                        result_text += mapping.get(name, '')
            result_text+=letter
        return result_text

    def on_button_h1__clicked(self, *args):
        self.set_style('h1')

    def on_button_h2__clicked(self, *args):
        self.set_style('h2')

    def on_button_h3__clicked(self, *args):
        self.set_style('h3')

    def on_button_h4__clicked(self, *args):
        self.set_style('h4')

    def on_button_h5__clicked(self, *args):
        self.set_style('h5')

    def on_button_h6__clicked(self, *args):
        self.set_style('h6')

    def on_button_bold__clicked(self, *args):
        self.set_style('bold')

    def on_button_italic__clicked(self, *args):
        self.set_style('italic')

    def on_button_clear_style__clicked(self, *args):
        self.clear_style()

    def set_style(self, tag):
        buffer = self.stdin.get_buffer()
        start, end = buffer.get_selection_bounds()
        buffer.remove_all_tags(start, end)
        buffer.apply_tag_by_name(tag, start, end)

    def clear_style(self):
        buffer = self.stdin.get_buffer()
        start, end = buffer.get_selection_bounds()
        buffer.remove_all_tags(start, end)

    def on_button_save__clicked(self, *args):
        self.post("Saving...")
        dialog = gtk.Dialog(title = "Commit message",
                            flags = gtk.DIALOG_MODAL, 
                            buttons = dialog_buttons)
        entry = gtk.Entry()
        minor = gtk.CheckButton("Minor")
        dialog.vbox.add(gtk.Label("Your attention to detail\nIs greatly appreciated"))
        dialog.vbox.add(entry)
        dialog.vbox.add(minor)
        dialog.show_all()
        response = dialog.run()
        if response == gtk.RESPONSE_ACCEPT:
            text = self.process_text()
            pars = {}
            if entry.get_text():
                pars['sum'] = entry.get_text()
            if minor.get_active():
                pars['minor'] = minor.get_active()
            self._rpc.wiki.putPage(self.current, text, pars)
            if not self.current in self._sections:
                self.add_page({"id":self.current})
            self.getHtmlView()
            self.post("Saved")

        dialog.destroy()

    def get_attachments(self, ns):
        attachments = self._rpc.wiki.getAttachments(ns, {})
        attachments = [Wrapper(s) for s in attachments]
        self.attachmentlist.add_list(attachments)

    def get_backlinks(self, pagename):
        backlinks = self._rpc.wiki.getBackLinks(pagename)
        backlinks = [Section(s) for s in backlinks]
        self.backlinks.add_list(backlinks)

    def get_versions(self, pagename):
        versionlist = self._rpc.wiki.getPageVersions(pagename, 0)
        versionlist = [Wrapper(s) for s in versionlist]
        self.versionlist.add_list(versionlist)

    def selected(self, widget, object):
        if not object: return
        if isinstance(object, Section):
            self.get_attachments(object.name)
        if not isinstance(object, Wrapper): return
        text = self._rpc.wiki.getPage(object.id)
        self.current = object.id
        self.add_text(text)
        self.get_backlinks(object.id)
        self.get_versions(object.id)

    def add_text(self, text):
        buffer = self.stdin.get_buffer().set_property('text', '')
        for line in text.split('\n'):
            self.add_line(line)
        self.getHtmlView()

    def add_fragment(self, line, stack):
        buffer = self.stdin.get_buffer()
        token,style = stack.pop()
        splitline = line.split(token)
        bold = False
        iter = buffer.get_end_iter()
        if len(splitline)>2:
            buffer.insert(iter, splitline[0])
            for fragment in splitline[1:]:
                bold = not bold
                if bold:
                    buffer.insert_with_tags_by_name(iter, fragment, style)
                else:
                    if len(stack):
                        self.add_fragment(fragment, stack)
                    else:
                        buffer.insert(iter, fragment)
        else:
            if len(stack):
                self.add_fragment(line, stack)
            else:
                buffer.insert(iter, line)

    def add_line(self, line):
        buffer = self.stdin.get_buffer()
        iter = buffer.get_end_iter()
        for idx in range(6):
            toks = '='*(idx+1)
            if line.startswith(toks+' '):
                line = line.replace(toks,'')
                line = line.strip()
                buffer.insert_with_tags_by_name(iter, line, 'h'+str(6-idx))
                buffer.insert(iter, '\n')
                return
        self.add_fragment(line+'\n', [("**","bold"),("//","italic")])

    def getHtmlView(self):
        text = self._rpc.wiki.getPageHTML(self.current)
        self.htmlview.render_data(text, len(text), self.url.get_text(), 'text/html')
        # XXX following is for gtkhtml (not used)
        #self.document.clear()
        #self.document.open_stream('text/html')
        #self.document.write_stream(text)
        #self.document.close_stream()


if __name__ == "__main__":
    app = DokuwikiView()
    app.show()
    gtk.main()

