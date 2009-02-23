#!/usr/bin/env python
import gtk
import gtksourceview

#class DokuwikiBuffer(gtk.TextBuffer):
class DokuwikiBuffer(gtksourceview.SourceBuffer):
    """
    A gtk text buffer with some wysiwyg properties
    for dokuwiki format.
    """
    def add_text(self, text):
        self.begin_not_undoable_action()
        self.clear()
        for line in text.split('\n'):
            self.add_line(line)
        self.end_not_undoable_action()

    def set_style(self, tag):
        start, end = self.get_selection_bounds()
        self.remove_all_tags(start, end)
        self.apply_tag_by_name(tag, start, end)

    def clear_style(self):
        start, end = self.get_selection_bounds()
        self.remove_all_tags(start, end)

    def clear(self):
        self.set_property('text', '')

    def process_text(self):
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
        text =  self.get_property("text")
        for idx, letter in enumerate(text):
            iter = self.get_iter_at_offset(idx)
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

    def add_fragment(self, line, stack):
        token,style = stack.pop()
        splitline = line.split(token)
        bold = False
        iter = self.get_end_iter()
        if len(splitline)>2:
            self.insert(iter, splitline[0])
            for fragment in splitline[1:]:
                iter = self.get_end_iter()
                bold = not bold
                if bold:
                    self.insert_with_tags_by_name(iter, fragment, style)
                else:
                    if len(stack):
                        self.add_fragment(fragment, stack)
                    else:
                        self.insert(iter, fragment)
        else:
            if len(stack):
                self.add_fragment(line, stack)
            else:
                self.insert(iter, line)

    def add_line(self, line):
        iter = self.get_end_iter()
        for idx in range(6):
            toks = '='*(idx+1)
            if line.startswith(toks+' '):
                line = line.replace(toks,'')
                line = line.strip()
                self.insert_with_tags_by_name(iter, line, 'h'+str(6-idx))
                self.insert(iter, '\n')
                return
        self.add_fragment(line+'\n', [("**","bold"),("//","italic")])



